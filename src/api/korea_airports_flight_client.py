"""한국공항공사(KAC) 항공편 API — 김포(GMP)·김해(PUS)·제주(CJU) 등.

인천(ICN)은 IncheonAirportClient(실시간)를 쓰고, KAC 공항은 정기 스케줄(갱신 지연)입니다.
  · 노선이 스냅샷/API에 있으면 → 운항기간(시작·종료일) 밖이어도 표시 (요일 우선)
  · 노선 자체가 없으면 → 0편 (ICN 경유 등으로 대체하지 않음)

데이터 소스 (KAC_FLIGHT_SOURCE=auto):
  1. [중지됨 2026-05] openapi.airport.co.kr — 항공기 운항정보 (probe 실패 시 자동 건너뜀)
  2. [현재] apis.data.go.kr/B551178/flight-status — 한국공항공사_실시간 항공기 운항정보 조회_GW
     /depart (출발편) · /arrival (도착편) — D-3~D+6, 일 5000 트래픽
     KAC_GW_BASE_URL 환경변수로 재정의 가능
  3. api.odcloud.kr — 국제선 항공기스케줄 스냅샷 (15003087) [최종 fallback]

인증키: PUBLIC_API_KEY (.env)
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any

import requests

from src.api.aviation_client import (
    FlightInfo,
    _AIRLINE_DISPLAY,
    _append_flight_unique,
    _hhmm,
    _parse_date,
    _ROUTE_DURATION_MIN,
)

logger = logging.getLogger(__name__)

# ── KAC GW (실시간 운항정보) ────────────────────────────────────────
_KAC_GW_BASE = "https://apis.data.go.kr/B551178/flight-status"

# ── odcloud (국제선 스냅샷 CSV) ─────────────────────────────────────
_ODCLOUD_BASE = "https://api.odcloud.kr/api"
_DATASET_ID = "15003087"
_DEFAULT_UDDI = "b6b81e88-9a4a-4f03-a1b9-871dc2adc389"

# ── openapi.airport.co.kr (항공기 운항정보) ─────────────────────────
_AIRPORT_API_BASE = "https://openapi.airport.co.kr/service/rest"
_SCHEDULE_BASE = f"{_AIRPORT_API_BASE}/FlightScheduleList"
_OP_INTL = "getIflightScheduleList"
_OP_DOM = "getDflightScheduleList"
_PROBE_OP = "AirportCodeList/getAirportCodeList"

_KOREA_HUB_IATA = frozenset({"GMP", "PUS", "CJU"})
_KOREA_AIRPORTS = _KOREA_HUB_IATA | {"ICN", "TAE", "CJJ", "KWJ", "MWX"}

_AIRPORT_NAME: dict[str, str] = {
    "ICN": "인천국제공항",
    "GMP": "김포국제공항",
    "PUS": "김해국제공항",
    "CJU": "제주국제공항",
    "NRT": "成田国際空港",
    "HND": "羽田空港",
    "KIX": "関西国際空港",
    "FUK": "福岡空港",
    "NGO": "中部国際空港",
    "CTS": "新千歳空港",
    "OKA": "那覇空港",
}

_WEEKDAY_MAP = {
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
    "月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6,
}

_INTL_WEEK_FIELDS = [
    ("internationalMon", "월"),
    ("internationalTue", "화"),
    ("internationalWed", "수"),
    ("internationalThu", "목"),
    ("internationalFri", "금"),
    ("internationalSat", "토"),
    ("internationalSun", "일"),
]
_DOM_WEEK_FIELDS = [
    ("domesticMon", "월"),
    ("domesticTue", "화"),
    ("domesticWed", "수"),
    ("domesticThu", "목"),
    ("domesticFri", "금"),
    ("domesticSat", "토"),
    ("domesticSun", "일"),
]

# KAC GW API가 반환하는 영문 공항명 → IATA (arrAirportEng / depAirportEng 필드)
_ENG_NAME_TO_IATA: dict[str, str] = {
    "INCHEON": "ICN", "GIMPO": "GMP", "GIMHAE": "PUS", "BUSAN": "PUS",
    "JEJU": "CJU", "DAEGU": "TAE", "CHEONGJU": "CJJ", "GWANGJU": "KWJ", "MUAN": "MWX",
    "NARITA": "NRT", "TOKYO/NARITA": "NRT",
    "HANEDA": "HND", "TOKYO/HANEDA": "HND",
    "KANSAI": "KIX", "OSAKA": "KIX", "OSAKA/KANSAI": "KIX",
    "ITAMI": "ITM", "OSAKA/ITAMI": "ITM",
    "FUKUOKA": "FUK",
    "NAGOYA": "NGO", "CHUBU": "NGO", "NAGOYA/CHUBU": "NGO",
    "CHITOSE": "CTS", "SAPPORO": "CTS", "NEW CHITOSE": "CTS",
    "NAHA": "OKA", "OKINAWA": "OKA",
    "HIROSHIMA": "HIJ", "SENDAI": "SDJ", "KAGOSHIMA": "KOJ",
    "TAKAMATSU": "TAK", "MATSUYAMA": "MYJ",
}


def _eng_to_iata(name: str) -> str:
    """영문 공항명 → IATA. 매핑 없으면 빈 문자열."""
    upper = (name or "").strip().upper()
    if upper in _ENG_NAME_TO_IATA:
        return _ENG_NAME_TO_IATA[upper]
    for key, iata in _ENG_NAME_TO_IATA.items():
        if key in upper:
            return iata
    return ""


def _item_iata(item: dict, side: str, fallback: str = "") -> str:
    """item에서 출발(dep) 또는 도착(arr) IATA 코드 추출.

    KAC GW API는 *AirportId 대신 *AirportEng(영문명)을 반환한다.
    """
    prefix = side  # "dep" or "arr"
    # KAC GW 신규 필드명 우선 (arrvAirportCode / depAirportCode)
    kac_gw_key = "arrvAirportCode" if prefix == "arr" else "depAirportCode"
    direct = (
        item.get(kac_gw_key) or
        item.get(f"{prefix}AirportId") or
        item.get("sch" + ("Dept" if prefix == "dep" else "Arrv") + "CityCode") or
        item.get(f"{prefix}CityCode") or ""
    ).upper()
    if direct and len(direct) == 3 and direct.isalpha():
        return direct
    eng = item.get(f"{prefix}AirportEng") or item.get(f"{prefix}Airport") or ""
    return _eng_to_iata(eng) or fallback.upper()


_snapshot_cache: dict[str, list[dict]] = {}
_airport_probe_cache: bool | None = None


def _service_key() -> str | None:
    return (
        os.getenv("PUBLIC_API_KEY")
        or os.getenv("AIRPORT_API_KEY")      # 구 키명 호환
        or os.getenv("ODCLOUD_SERVICE_KEY")  # 구 키명 호환
    )


def _kac_gw_base_url() -> str:
    """한국공항공사_실시간 항공기 운항정보 조회_GW 엔드포인트.

    기본값: _KAC_GW_BASE (apis.data.go.kr/B551178/flight-status).
    .env에 KAC_GW_BASE_URL= 로 재정의 가능.
    """
    return (os.getenv("KAC_GW_BASE_URL") or _KAC_GW_BASE).rstrip("/")


def _flight_source_mode() -> str:
    return (os.getenv("KAC_FLIGHT_SOURCE") or "auto").strip().lower()


def uses_korea_regional_airport(dep_iata: str | None, arr_iata: str | None) -> bool:
    dep = (dep_iata or "").upper()
    arr = (arr_iata or "").upper()
    return dep in _KOREA_HUB_IATA or arr in _KOREA_HUB_IATA


def probe_odcloud_key(service_key: str | None = None) -> tuple[bool, str]:
    key = (service_key or _service_key() or "").strip()
    if not key:
        return False, "API 키 없음"
    uddi = os.getenv("ODCLOUD_KAC_UDDI", _DEFAULT_UDDI).strip()
    url = f"{_ODCLOUD_BASE}/{_DATASET_ID}/v1/uddi:{uddi}"
    try:
        r = requests.get(
            url, params={"serviceKey": key, "page": 1, "perPage": 1}, timeout=20
        )
        r.raise_for_status()
        total = r.json().get("totalCount")
        if total is not None:
            return True, f"totalCount={total}"
        return False, r.text[:120]
    except Exception as exc:
        return False, str(exc)[:120]


def probe_airport_co_kr_key(service_key: str | None = None) -> tuple[bool, str]:
    """openapi.airport.co.kr (항공기 운항정보) 활용신청 연동 여부."""
    global _airport_probe_cache
    key = (service_key or _service_key() or "").strip()
    if not key:
        return False, "API 키 없음"
    if _airport_probe_cache is not None:
        return _airport_probe_cache, "OK (cached)" if _airport_probe_cache else "FAIL (cached)"
    url = f"{_AIRPORT_API_BASE}/{_PROBE_OP}"
    try:
        r = requests.get(
            url,
            params={"serviceKey": key, "pageNo": "1", "numOfRows": "1"},
            timeout=15,
        )
        r.raise_for_status()
        code, msg = _parse_header(r.content, r.headers.get("content-type", ""))
        ok = code == "00"
        _airport_probe_cache = ok
        return ok, msg or code or "unknown"
    except Exception as exc:
        _airport_probe_cache = False
        return False, str(exc)[:120]


def _parse_header(content: bytes, content_type: str) -> tuple[str | None, str | None]:
    if "json" in (content_type or "").lower():
        try:
            import json

            h = json.loads(content).get("response", {}).get("header", {})
            return h.get("resultCode"), h.get("resultMsg")
        except Exception:
            pass
    try:
        root = ET.fromstring(content)
        return root.findtext(".//resultCode"), root.findtext(".//resultMsg")
    except ET.ParseError:
        return None, None


def _extract_items(payload: dict) -> list[dict]:
    body = payload.get("response", {}).get("body") or {}
    items = body.get("items")
    if not items:
        return []
    if isinstance(items, list):
        return items
    item = items.get("item")
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def _payload_from_bytes(content: bytes, content_type: str) -> dict:
    if "json" in (content_type or "").lower():
        import json

        return json.loads(content)
    root = ET.fromstring(content)
    items: list[dict] = []
    for el in root.findall(".//item"):
        items.append({child.tag: (child.text or "").strip() for child in el})
    total = root.findtext(".//totalCount") or "0"
    return {
        "response": {
            "header": {
                "resultCode": root.findtext(".//resultCode"),
                "resultMsg": root.findtext(".//resultMsg"),
            },
            "body": {"items": {"item": items}, "totalCount": int(total)},
        }
    }


def _is_domestic_route(dep: str, arr: str) -> bool:
    return dep in _KOREA_AIRPORTS and arr in _KOREA_AIRPORTS


class KoreaAirportsFlightClient:
    def __init__(self, service_key: str | None = None, timeout: int = 60):
        self.service_key = (service_key or _service_key() or "").strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.service_key)

    def search_flights(
        self,
        dep_iata: str | None,
        arr_iata: str | None,
        flight_date: str | None = None,
        limit: int = 500,
    ) -> tuple[list[FlightInfo], str | None, str]:
        if not self.service_key:
            raise ValueError("PUBLIC_API_KEY가 설정되지 않았습니다.")
        dep = (dep_iata or "").upper()
        arr = (arr_iata or "").upper()
        if not dep or not arr:
            raise ValueError("출발·도착 공항 IATA가 필요합니다.")

        mode = _flight_source_mode()
        if mode in ("airport", "airport_co_kr", "openapi"):
            flights, warn = self._search_airport_co_kr(dep, arr, flight_date, limit)
            if flights:
                return flights, warn, "airport_co_kr"
            if mode != "auto":
                raise ValueError(
                    f"openapi.airport.co.kr 조회 실패 ({dep}→{arr}). "
                    "마이페이지에서 「항공기 운항정보」 승인·일반 인증키를 확인하세요."
                )

        if mode == "auto":
            ok, _ = probe_airport_co_kr_key(self.service_key)
            if ok:
                flights, warn = self._search_airport_co_kr(dep, arr, flight_date, limit)
                if flights:
                    return flights, warn, "airport_co_kr"

        # 2. KAC GW (apis.data.go.kr/B551178/flight-status) — 실시간
        if mode in ("auto", "kac_gw"):
            try:
                flights, warn = self._search_kac_gw(dep, arr, flight_date, limit)
                if flights:
                    return flights, warn, "kac_gw"
            except Exception as exc:
                logger.warning("kac_gw 조회 실패 (%s→%s): %s", dep, arr, exc)

        # 3. odcloud 스냅샷 (최종 fallback)
        flights, warn = self._search_odcloud(dep, arr, flight_date, limit)
        return flights, warn, "odcloud"

    # ── KAC GW (apis.data.go.kr/B551178/flight-status) ─────────────

    def _search_kac_gw(
        self,
        dep: str,
        arr: str,
        flight_date: str | None,
        limit: int,
    ) -> tuple[list[FlightInfo], str | None]:
        """한국공항공사_실시간 항공기 운항정보 조회_GW.

        /depart 로 dep 출발 전체 조회 후 arr 도착지 필터.
        결과 없으면 /arrival 로 arr 도착 전체 조회 후 dep 출발지 필터.
        """
        base = _kac_gw_base_url()
        target = _parse_date(flight_date)
        sch_date = target.strftime("%Y%m%d") if target else date.today().strftime("%Y%m%d")

        results: list[FlightInfo] = []

        depart_items = self._fetch_kac_gw_pages(
            f"{base}/depart",
            {"schDate": sch_date, "schDeptCityCode": dep},
            limit * 5,
        )
        depart_items = [
            it for it in depart_items
            if _item_iata(it, "arr", arr) == arr
        ]
        for item in depart_items:
            fl = self._normalize_kac_gw_depart(item, dep, arr)
            _append_flight_unique(results, fl)
            if len(results) >= limit:
                break

        if not results:
            arrival_items = self._fetch_kac_gw_pages(
                f"{base}/arrival",
                {"schDate": sch_date, "schArrvCityCode": arr},
                limit * 5,
            )
            arrival_items = [
                it for it in arrival_items
                if _item_iata(it, "dep", dep) == dep
            ]
            for item in arrival_items:
                fl = self._normalize_kac_gw_arrival(item, dep, arr)
                _append_flight_unique(results, fl)
                if len(results) >= limit:
                    break

        results.sort(key=lambda f: f.dep_scheduled or f.arr_scheduled or "99:99")
        logger.info("kac_gw %s→%s date=%s → %d편", dep, arr, flight_date, len(results))
        return results, None

    def _fetch_kac_gw_pages(
        self,
        url: str,
        extra: dict[str, Any],
        limit: int,
    ) -> list[dict]:
        out: list[dict] = []
        page = 1
        while len(out) < limit:
            params = {
                "serviceKey": self.service_key,
                "pageNo": str(page),
                "numOfRows": "100",
                "_type": "json",
                **extra,
            }
            try:
                r = requests.get(url, params=params, timeout=self.timeout)
                r.raise_for_status()
                payload = _payload_from_bytes(r.content, r.headers.get("content-type", ""))
            except Exception as exc:
                logger.warning("kac_gw %s page %d: %s", url.split("/")[-1], page, exc)
                break
            code = (payload.get("response", {}).get("header") or {}).get("resultCode")
            if code and code != "00":
                msg = (payload.get("response", {}).get("header") or {}).get("resultMsg")
                logger.warning("kac_gw %s → code=%s %s", url.split("/")[-1], code, msg)
                break
            batch = _extract_items(payload)
            if not batch:
                break
            out.extend(batch)
            total = (payload.get("response", {}).get("body") or {}).get("totalCount")
            if total is not None and len(out) >= int(total):
                break
            if len(batch) < 100:
                break
            page += 1
        return out

    @staticmethod
    def _kac_gw_status(item: dict) -> str:
        remark = (
            item.get("rmkKor") or item.get("remark") or item.get("remarksEng") or
            item.get("remarkKor") or item.get("운항상태") or ""
        ).strip()
        if not remark:
            return "scheduled"
        if "지연" in remark or "delay" in remark:
            return "delayed"
        if "결항" in remark or "cancel" in remark:
            return "cancelled"
        lower = remark.lower()
        if "지연" in remark or "delay" in lower:
            return "delayed"
        if "결항" in remark or "cancel" in lower:
            return "cancelled"
        if "출발" in remark or "depart" in lower or "active" in lower:
            return "active"
        if "도착" in remark or "arrived" in lower or "landed" in lower:
            return "landed"
        return "scheduled"

    def _normalize_kac_gw_depart(self, item: dict, dep: str, arr: str) -> FlightInfo:
        flight_id = (
            item.get("flightid") or item.get("flightId") or
            item.get("편명") or item.get("항공편명") or ""
        ).strip().upper()
        airline_code = "".join(c for c in flight_id if c.isalpha())[:2]
        airline_name = (
            _AIRLINE_DISPLAY.get(airline_code)
            or item.get("airlineKorean") or item.get("airline") or item.get("항공사") or ""
        )
        dep_time = self._time_hhmm(
            item.get("estimateddatetime") or item.get("scheduledatetime") or
            item.get("depPlandTime") or item.get("scheduleDateTime") or
            item.get("depSchdDateTime") or item.get("출발예정시간") or ""
        )
        arr_airport_id = _item_iata(item, "arr", arr)
        arr_time = self._time_hhmm(
            item.get("arrPlandTime") or item.get("arrSchdDateTime") or
            item.get("도착예정시간") or ""
        )
        if not arr_time and dep_time:
            dur = _ROUTE_DURATION_MIN.get((dep, arr_airport_id), 90)
            try:
                total = int(dep_time[:2]) * 60 + int(dep_time[3:5]) + dur
                arr_time = f"{(total // 60) % 24:02d}:{total % 60:02d}"
            except (ValueError, IndexError):
                arr_time = dep_time
        dep_airport_id = _item_iata(item, "dep", dep)
        return FlightInfo(
            flight_iata=flight_id,
            flight_number="".join(c for c in flight_id if c.isdigit()),
            airline_name=airline_name,
            airline_iata=airline_code,
            status=self._kac_gw_status(item),
            dep_airport=_AIRPORT_NAME.get(dep_airport_id, dep_airport_id),
            dep_iata=dep_airport_id,
            dep_terminal=item.get("terminal") or item.get("터미널") or None,
            dep_gate=item.get("gate") or None,
            dep_scheduled=dep_time,
            dep_delay=None,
            arr_airport=_AIRPORT_NAME.get(arr_airport_id, arr_airport_id),
            arr_iata=arr_airport_id,
            arr_terminal=None,
            arr_gate=None,
            arr_scheduled=arr_time,
            arr_delay=None,
            codeshared_iata=None,
        )

    def _normalize_kac_gw_arrival(self, item: dict, dep: str, arr: str) -> FlightInfo:
        flight_id = (
            item.get("flightid") or item.get("flightId") or
            item.get("편명") or item.get("항공편명") or ""
        ).strip().upper()
        airline_code = "".join(c for c in flight_id if c.isalpha())[:2]
        airline_name = (
            _AIRLINE_DISPLAY.get(airline_code)
            or item.get("airlineKorean") or item.get("airline") or item.get("항공사") or ""
        )
        arr_time = self._time_hhmm(
            item.get("estimateddatetime") or item.get("scheduledatetime") or
            item.get("arrPlandTime") or item.get("scheduleDateTime") or
            item.get("arrSchdDateTime") or item.get("도착예정시간") or ""
        )
        dep_airport_id = _item_iata(item, "dep", dep)
        arr_airport_id = _item_iata(item, "arr", arr)
        dep_time = self._time_hhmm(
            item.get("depPlandTime") or item.get("depSchdDateTime") or
            item.get("출발예정시간") or ""
        )
        if not dep_time and arr_time:
            dur = _ROUTE_DURATION_MIN.get((dep_airport_id, arr_airport_id), 90)
            try:
                total = int(arr_time[:2]) * 60 + int(arr_time[3:5]) - dur
                dep_time = f"{(total // 60) % 24:02d}:{total % 60:02d}"
            except (ValueError, IndexError):
                dep_time = arr_time
        return FlightInfo(
            flight_iata=flight_id,
            flight_number="".join(c for c in flight_id if c.isdigit()),
            airline_name=airline_name,
            airline_iata=airline_code,
            status=self._kac_gw_status(item),
            dep_airport=_AIRPORT_NAME.get(dep_airport_id, dep_airport_id),
            dep_iata=dep_airport_id,
            dep_terminal=None,
            dep_gate=None,
            dep_scheduled=dep_time,
            dep_delay=None,
            arr_airport=_AIRPORT_NAME.get(arr_airport_id, arr_airport_id),
            arr_iata=arr_airport_id,
            arr_terminal=item.get("terminal") or item.get("터미널") or None,
            arr_gate=item.get("gate") or None,
            arr_scheduled=arr_time,
            arr_delay=None,
            codeshared_iata=None,
        )

    # ── openapi.airport.co.kr ─────────────────────────────────────

    def _search_airport_co_kr(
        self,
        dep: str,
        arr: str,
        flight_date: str | None,
        limit: int,
    ) -> tuple[list[FlightInfo], str | None]:
        target = _parse_date(flight_date)
        sch_date = target.strftime("%Y%m%d") if target else date.today().strftime("%Y%m%d")
        op = _OP_DOM if _is_domestic_route(dep, arr) else _OP_INTL
        params: dict[str, Any] = {
            "schDate": sch_date,
            "schDeptCityCode": dep,
            "schArrvCityCode": arr,
        }
        raw_items = self._fetch_schedule_pages(op, params, limit * 3)
        if not raw_items:
            return [], None

        domestic = op == _OP_DOM
        items = self._filter_kac_by_weekday(
            raw_items,
            target,
            lambda it: self._airport_weekday_only(it, target, domestic=domestic),
        )

        results: list[FlightInfo] = []
        for item in items:
            fl = (
                self._normalize_domestic(item, dep, arr)
                if domestic
                else self._normalize_international(item, dep, arr)
            )
            _append_flight_unique(results, fl)
            if len(results) >= limit:
                break

        results.sort(key=lambda f: f.dep_scheduled or f.arr_scheduled or "99:99")
        logger.info(
            "airport.co.kr %s %s→%s date=%s → %d편",
            op, dep, arr, flight_date, len(results),
        )
        return results, None

    def _fetch_schedule_pages(
        self, operation: str, extra: dict[str, Any], limit: int
    ) -> list[dict]:
        url = f"{_SCHEDULE_BASE}/{operation}"
        out: list[dict] = []
        page = 1
        while len(out) < limit:
            params = {
                "serviceKey": self.service_key,
                "pageNo": str(page),
                "numOfRows": "100",
                "_type": "json",
                **extra,
            }
            try:
                r = requests.get(url, params=params, timeout=self.timeout)
                r.raise_for_status()
                payload = _payload_from_bytes(r.content, r.headers.get("content-type", ""))
            except Exception as exc:
                logger.warning("airport.co.kr %s page %d: %s", operation, page, exc)
                break
            code = (payload.get("response", {}).get("header") or {}).get("resultCode")
            if code != "00":
                msg = (payload.get("response", {}).get("header") or {}).get("resultMsg")
                logger.warning("airport.co.kr %s → %s %s", operation, code, msg)
                break
            batch = _extract_items(payload)
            if not batch:
                break
            out.extend(batch)
            total = (payload.get("response", {}).get("body") or {}).get("totalCount")
            if total is not None and len(out) >= int(total):
                break
            if len(batch) < 100:
                break
            page += 1
        return out

    @staticmethod
    def _airport_weekday_only(item: dict, target: date, *, domestic: bool) -> bool:
        """KAC: API 운항기간은 무시, 선택일 요일만 참고."""
        fields = _DOM_WEEK_FIELDS if domestic else _INTL_WEEK_FIELDS
        any_day = False
        for field, _ in fields:
            v = (item.get(field) or "").strip().upper()
            if v in ("Y", "YES", "1", "운항"):
                any_day = True
                break
        if not any_day:
            return True
        wd = target.weekday()
        for field, label in fields:
            v = (item.get(field) or "").strip().upper()
            if v in ("Y", "YES", "1", "운항") and _WEEKDAY_MAP.get(label) == wd:
                return True
        return False

    @staticmethod
    def _time_hhmm(raw: Any) -> str:
        s = str(raw or "").strip()
        if not s:
            return ""
        if ":" in s:
            parts = s.split(":")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        return _hhmm(s)

    def _normalize_international(self, item: dict, dep: str, arr: str) -> FlightInfo:
        flight_id = (item.get("internationalNum") or "").strip().upper()
        airline_iata_val = "".join(c for c in flight_id if c.isalpha())[:2]
        airline_name = (
            _AIRLINE_DISPLAY.get(airline_iata_val)
            or (item.get("airlineKorean") or item.get("airlineEnglish") or "")
        )
        dep_time = self._time_hhmm(item.get("internationalTime"))
        arr_time = ""
        dur = _ROUTE_DURATION_MIN.get((dep, arr), 90)
        try:
            total = int(dep_time[:2]) * 60 + int(dep_time[3:5]) + dur
            arr_time = f"{(total // 60) % 24:02d}:{total % 60:02d}"
        except (ValueError, IndexError):
            arr_time = dep_time
        days = "".join(l for f, l in _INTL_WEEK_FIELDS if (item.get(f) or "").upper() in ("Y", "1"))
        return FlightInfo(
            flight_iata=flight_id,
            flight_number="".join(c for c in flight_id if c.isdigit()),
            airline_name=airline_name,
            airline_iata=airline_iata_val,
            status="scheduled",
            dep_airport=_AIRPORT_NAME.get(dep, dep),
            dep_iata=dep,
            dep_terminal=None,
            dep_gate=None,
            dep_scheduled=dep_time,
            dep_delay=None,
            arr_airport=_AIRPORT_NAME.get(arr, arr),
            arr_iata=arr,
            arr_terminal=None,
            arr_gate=None,
            arr_scheduled=arr_time,
            arr_delay=None,
            codeshared_iata=None,
            schedule_start=(item.get("internationalStdate") or "")[:10].replace("-", ""),
            schedule_end=(item.get("internationalEddate") or "")[:10].replace("-", ""),
            operating_days=days,
        )

    def _normalize_domestic(self, item: dict, dep: str, arr: str) -> FlightInfo:
        flight_id = (item.get("domesticNum") or "").strip().upper()
        airline_iata_val = "".join(c for c in flight_id if c.isalpha())[:2]
        airline_name = (
            _AIRLINE_DISPLAY.get(airline_iata_val)
            or (item.get("airlineKorean") or item.get("airlineEnglish") or "")
        )
        dep_time = self._time_hhmm(item.get("domesticStartTime"))
        arr_time = self._time_hhmm(item.get("domesticArrivalTime")) or dep_time
        days = "".join(l for f, l in _DOM_WEEK_FIELDS if (item.get(f) or "").upper() in ("Y", "1"))
        return FlightInfo(
            flight_iata=flight_id,
            flight_number="".join(c for c in flight_id if c.isdigit()),
            airline_name=airline_name,
            airline_iata=airline_iata_val,
            status="scheduled",
            dep_airport=_AIRPORT_NAME.get(dep, item.get("startcity") or dep),
            dep_iata=(item.get("startcityCode") or dep).upper(),
            dep_terminal=None,
            dep_gate=None,
            dep_scheduled=dep_time,
            dep_delay=None,
            arr_airport=_AIRPORT_NAME.get(arr, item.get("arrivalcity") or arr),
            arr_iata=(item.get("arrivalcityCode") or arr).upper(),
            arr_terminal=None,
            arr_gate=None,
            arr_scheduled=arr_time,
            arr_delay=None,
            codeshared_iata=None,
            schedule_start=(item.get("domesticStdate") or "")[:10].replace("-", ""),
            schedule_end=(item.get("domesticEddate") or "")[:10].replace("-", ""),
            operating_days=days,
        )

    # ── odcloud 스냅샷 ────────────────────────────────────────────

    def _search_odcloud(
        self,
        dep: str,
        arr: str,
        flight_date: str | None,
        limit: int,
    ) -> tuple[list[FlightInfo], str | None]:
        target = _parse_date(flight_date)
        uddi = os.getenv("ODCLOUD_KAC_UDDI", _DEFAULT_UDDI).strip()
        rows = self._load_snapshot(uddi)
        route_all = [r for r in rows if self._row_matches_route(r, dep, arr)]
        if not route_all:
            logger.info("odcloud %s→%s — 노선 없음 (KAC 스냅샷)", dep, arr)
            return [], None

        matched = self._filter_odcloud_rows(route_all, target)

        results: list[FlightInfo] = []
        for row in matched:
            fl = self._normalize_odcloud_row(row, dep, arr)
            _append_flight_unique(results, fl)
            if len(results) >= limit:
                break

        results.sort(key=lambda f: f.dep_scheduled or f.arr_scheduled or "99:99")
        logger.info("odcloud %s→%s date=%s → %d편", dep, arr, flight_date, len(results))
        return results, None

    def _load_snapshot(self, uddi: str) -> list[dict]:
        if uddi in _snapshot_cache:
            return _snapshot_cache[uddi]
        max_pages = int(os.getenv("ODCLOUD_KAC_MAX_PAGES", "55"))
        per_page = 1000
        url = f"{_ODCLOUD_BASE}/{_DATASET_ID}/v1/uddi:{uddi}"
        all_rows: list[dict] = []
        for page in range(1, max_pages + 1):
            try:
                r = requests.get(
                    url,
                    params={
                        "serviceKey": self.service_key,
                        "page": page,
                        "perPage": per_page,
                    },
                    timeout=self.timeout,
                )
                r.raise_for_status()
                payload = r.json()
            except Exception as exc:
                logger.warning("odcloud page %d failed: %s", page, exc)
                break
            batch = payload.get("data") or []
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < per_page:
                break
        _snapshot_cache[uddi] = all_rows
        logger.info("odcloud snapshot uddi=%s rows=%d", uddi[:8], len(all_rows))
        return all_rows

    @staticmethod
    def _filter_kac_by_weekday(
        rows: list[Any],
        target: date | None,
        weekday_fn,
    ) -> list[Any]:
        """KAC 노선: 기간 필터 없음. 노선 있으면 요일 맞는 편 우선, 없으면 노선 전체."""
        if not rows:
            return []
        if not target:
            return rows
        by_weekday = [r for r in rows if weekday_fn(r)]
        return by_weekday if by_weekday else rows

    @staticmethod
    def _filter_odcloud_rows(route_all: list[dict], target: date | None) -> list[dict]:
        if not route_all:
            return []
        return KoreaAirportsFlightClient._filter_kac_by_weekday(
            route_all,
            target,
            lambda row: KoreaAirportsFlightClient._row_operates_weekday(row, target),
        )

    @staticmethod
    def _row_matches_route(row: dict, dep: str, arr: str) -> bool:
        r_dep = (row.get("출발공항") or "").strip().upper()
        r_arr = (row.get("도착공항") or "").strip().upper()
        return r_dep == dep and r_arr == arr

    @staticmethod
    def _row_operates_weekday(row: dict, target: date) -> bool:
        days = row.get("운항요일") or ""
        if not days:
            return True
        wd = target.weekday()
        return any(_WEEKDAY_MAP.get(ch) == wd for ch in str(days))

    def _normalize_odcloud_row(self, row: dict, dep: str, arr: str) -> FlightInfo:
        flight_id = (row.get("운항편명") or "").strip().upper()
        airline_iata_val = "".join(c for c in flight_id if c.isalpha())[:2]
        airline_name = _AIRLINE_DISPLAY.get(airline_iata_val) or (row.get("항공사") or "")
        dep_time = self._time_hhmm(row.get("출발시간"))
        arr_time = self._time_hhmm(row.get("도착시간"))
        if not arr_time:
            dur = _ROUTE_DURATION_MIN.get((dep, arr), 90)
            try:
                total = int(dep_time[:2]) * 60 + int(dep_time[3:5]) + dur
                arr_time = f"{(total // 60) % 24:02d}:{total % 60:02d}"
            except (ValueError, IndexError):
                arr_time = dep_time

        return FlightInfo(
            flight_iata=flight_id,
            flight_number="".join(c for c in flight_id if c.isdigit()),
            airline_name=airline_name,
            airline_iata=airline_iata_val,
            status="scheduled",
            dep_airport=_AIRPORT_NAME.get(dep, dep),
            dep_iata=dep,
            dep_terminal=None,
            dep_gate=None,
            dep_scheduled=dep_time,
            dep_delay=None,
            arr_airport=_AIRPORT_NAME.get(arr, arr),
            arr_iata=arr,
            arr_terminal=None,
            arr_gate=None,
            arr_scheduled=arr_time,
            arr_delay=None,
            codeshared_iata=None,
            schedule_start=(row.get("시작일자") or "").replace("-", ""),
            schedule_end=(row.get("종료일자") or "").replace("-", ""),
            operating_days=str(row.get("운항요일") or ""),
        )
