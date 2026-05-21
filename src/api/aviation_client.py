"""인천국제공항공사 항공편 API 클라이언트.

서비스 1 — 정기편 스케줄 (미래 날짜):
  https://apis.data.go.kr/B551177/StatusOfPaxFltSched
  응답: flightid, airline, st(HHmm), airportcode, airport,
        firstdate, lastdate, monday~sunday, codeshare, masterflightid

서비스 2 — 실시간 운항현황 (오늘/당일):
  http://apis.data.go.kr/B551177/StatusOfPassengerFlightsOdp
  응답: flightId, airline, scheduleDateTime(HHmm), estimatedDateTime(HHmm),
        airportCode, airport, gatenumber, terminalId, remark,
        codeshare, masterflightid

날짜 자동 선택: 오늘 이하 → 실시간 API / 미래 → 정기편 API
출발지 시각: 노선별 비행시간(_ROUTE_DURATION_MIN)으로 추정 (JST=KST, 시차 없음)
키: INCHEONTRANSPORT_API_KEY (.env)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

ICN_IATA  = "ICN"
PAGE_SIZE = 1000

# ── 정기편 스케줄 API ───────────────────────────────────────────────
SCHED_BASE   = "https://apis.data.go.kr/B551177/StatusOfPaxFltSched"
OP_SCHED_ARR = "getPaxFltSchedArrivalsDeOdp"
OP_SCHED_DEP = "getPaxFltSchedDeparturesDeOdp"

# ── 실시간 운항현황 API ─────────────────────────────────────────────
RT_BASE   = "http://apis.data.go.kr/B551177/StatusOfPassengerFlightsOdp"
OP_RT_ARR = "getPassengerArrivalsOdp"
OP_RT_DEP = "getPassengerDeparturesOdp"

_WEEKDAY_FIELDS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WEEKDAY_KO     = ["월",     "화",       "수",         "목",        "금",      "토",        "일"]

# ── 노선별 비행시간 추정 (분) — Japan ↔ ICN ─────────────────────────
_ROUTE_DURATION_MIN: dict[tuple[str, str], int] = {
    ("NRT", "ICN"): 150, ("ICN", "NRT"): 150,
    ("HND", "ICN"): 145, ("ICN", "HND"): 145,
    ("KIX", "ICN"): 95,  ("ICN", "KIX"): 95,
    ("ITM", "ICN"): 95,  ("ICN", "ITM"): 95,
    ("FUK", "ICN"): 80,  ("ICN", "FUK"): 80,
    ("CTS", "ICN"): 175, ("ICN", "CTS"): 175,
    ("OKA", "ICN"): 155, ("ICN", "OKA"): 155,
    ("NGO", "ICN"): 120, ("ICN", "NGO"): 120,
    ("HIJ", "ICN"): 125, ("ICN", "HIJ"): 125,
    ("SDJ", "ICN"): 160, ("ICN", "SDJ"): 160,
    ("KOJ", "ICN"): 135, ("ICN", "KOJ"): 135,
    ("TAK", "ICN"): 110, ("ICN", "TAK"): 110,
    ("MYJ", "ICN"): 110, ("ICN", "MYJ"): 110,
}

# IATA 코드 → 브랜드 표시명 (API가 한국어명을 반환할 때 대체)
_AIRLINE_DISPLAY: dict[str, str] = {
    "NH": "ANA",
    "JL": "JAL",
    "MM": "Peach",
    "ZG": "ZIPAIR",
    "7G": "StarFlyer",
    "GK": "Jetstar Japan",
    "BC": "Skymark",
}

_REMARK_STATUS: dict[str, str] = {
    "도착":    "landed",
    "출발":    "active",
    "탑승":    "active",
    "출발준비": "active",
    "지연":    "active",
    "결항":    "cancelled",
    "예정":    "scheduled",
}

# 한·일 도시/공항명 → IATA 코드
AIRPORT_ALIASES: dict[str, str] = {
    "인천": "ICN", "인천공항": "ICN", "인천국제공항": "ICN",
    "김포": "GMP", "김포공항": "GMP",
    "부산": "PUS", "김해": "PUS", "김해공항": "PUS",
    "제주": "CJU", "제주공항": "CJU",
    "대구": "TAE", "청주": "CJJ",
    "광주": "KWJ", "무안": "MWX",
    "서울": "ICN",
    "나리타": "NRT", "나리타공항": "NRT", "成田": "NRT", "成田空港": "NRT",
    "하네다": "HND", "하네다공항": "HND", "羽田": "HND", "羽田空港": "HND",
    "도쿄": "NRT", "東京": "NRT",
    "오사카": "KIX", "간사이": "KIX", "関西": "KIX", "大阪": "KIX",
    "이타미": "ITM",
    "후쿠오카": "FUK", "福岡": "FUK",
    "나고야": "NGO", "中部": "NGO", "名古屋": "NGO",
    "삿포로": "CTS", "치토세": "CTS", "新千歳": "CTS", "札幌": "CTS",
    "오키나와": "OKA", "나하": "OKA", "那覇": "OKA", "沖縄": "OKA",
    "히로시마": "HIJ", "広島": "HIJ",
    "仙台": "SDJ", "센다이": "SDJ",
    "高松": "TAK", "松山": "MYJ",
    "鹿児島": "KOJ", "가고시마": "KOJ",
}


def resolve_iata(name: str) -> str | None:
    name = name.strip()
    upper = name.upper()
    if len(upper) == 3 and upper.isalpha():
        return upper
    return AIRPORT_ALIASES.get(name)


@dataclass(frozen=True)
class FlightInfo:
    flight_iata: str
    flight_number: str
    airline_name: str
    airline_iata: str
    status: str
    dep_airport: str
    dep_iata: str
    dep_terminal: str | None
    dep_gate: str | None
    dep_scheduled: str | None   # "HH:MM" (추정 포함)
    dep_delay: int | None       # 분
    arr_airport: str
    arr_iata: str
    arr_terminal: str | None
    arr_gate: str | None
    arr_scheduled: str | None   # "HH:MM" (추정 포함)
    arr_delay: int | None       # 분
    codeshared_iata: str | None = None
    schedule_start: str | None = None
    schedule_end: str | None = None
    operating_days: str = ""


@dataclass(frozen=True)
class AirportInfo:
    name: str
    iata: str
    icao: str | None
    country_name: str | None
    city_iata: str | None
    timezone: str | None
    latitude: float | None
    longitude: float | None


# ── 유틸리티 ───────────────────────────────────────────────────────

def _days_str(item: dict) -> str:
    return "".join(
        _WEEKDAY_KO[i]
        for i, field in enumerate(_WEEKDAY_FIELDS)
        if (item.get(field) or "").upper() == "Y"
    )


def _operates_on(item: dict, target: date) -> bool:
    s = item.get("firstdate") or ""
    e = item.get("lastdate") or ""
    try:
        if s and target < datetime.strptime(s, "%Y%m%d").date():
            return False
        if e and target > datetime.strptime(e, "%Y%m%d").date():
            return False
    except ValueError:
        pass
    return (item.get(_WEEKDAY_FIELDS[target.weekday()]) or "").upper() == "Y"


def _hhmm(raw: str) -> str:
    """HHmm 또는 YYYYMMDDHHmm → 'HH:MM'."""
    s = str(raw or "").strip()
    if len(s) == 12:   # YYYYMMDDHHmm
        return f"{s[8:10]}:{s[10:12]}"
    s = s.zfill(4)
    return f"{s[:2]}:{s[2:4]}" if len(s) >= 4 else s


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _hhmm_to_min(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def _calc_delay(scheduled: str, estimated: str) -> int | None:
    """estimated - scheduled (분). 자정 경계 보정."""
    if not scheduled or not estimated or scheduled == estimated:
        return None
    try:
        d = _hhmm_to_min(estimated) - _hhmm_to_min(scheduled)
        if d < -720: d += 1440
        if d >  720: d -= 1440
        return d if d != 0 else None
    except (ValueError, IndexError):
        return None


def _estimate_other_side(known: str, dep_code: str, arr_code: str, *, known_is_arr: bool) -> str | None:
    """비행시간으로 반대쪽 시각 추정. JST=KST라 시차 보정 불필요."""
    if not known:
        return None
    dur = _ROUTE_DURATION_MIN.get((dep_code.upper(), arr_code.upper()))
    if not dur:
        return None
    try:
        total = _hhmm_to_min(known)
        total = (total - dur if known_is_arr else total + dur) % 1440
        return f"{total // 60:02d}:{total % 60:02d}"
    except (ValueError, IndexError):
        return None


def _flight_dedupe_key(f: FlightInfo) -> tuple:
    return (
        f.flight_iata.upper(),
        f.dep_scheduled or "",
        f.arr_scheduled or "",
        (f.codeshared_iata or "").upper(),
    )


def _append_flight_unique(results: list[FlightInfo], flight: FlightInfo) -> bool:
    """동일 API 행이 반복될 때 목록에 한 번만 추가."""
    key = _flight_dedupe_key(flight)
    for existing in results:
        if _flight_dedupe_key(existing) == key:
            if flight.codeshared_iata and not existing.codeshared_iata:
                idx = results.index(existing)
                results[idx] = flight
            return False
    results.append(flight)
    return True


class IncheonAirportClient:
    """인천공항 항공편 API 클라이언트.

    오늘 이전·당일: 실시간 운항현황 API (게이트·지연 정보 포함)
    미래 날짜:      정기편 스케줄 API
    출발지 시각:    비행시간 추정으로 보완 (Japan 노선 한정)
    """

    def __init__(self, service_key: str | None = None, timeout: int = 15):
        self.service_key = (
            service_key
            or os.getenv("INCHEONTRANSPORT_API_KEY")
            or os.getenv("INCHEONAIRPORT_API_KEY")
        )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.service_key)

    def search_flights(
        self,
        dep_iata: str | None = None,
        arr_iata: str | None = None,
        flight_iata: str | None = None,
        flight_date: str | None = None,
        airline_iata: str | None = None,
        limit: int = 5,
    ) -> list[FlightInfo]:
        """ICN 연관 항공편 조회. 날짜 기준으로 실시간/정기편 API 자동 선택."""
        if not self.service_key:
            raise ValueError("INCHEONTRANSPORT_API_KEY가 설정되지 않았습니다.")

        target_date = _parse_date(flight_date)
        today = date.today()

        if target_date is None or target_date <= today:
            return self._search_realtime(
                dep_iata, arr_iata, flight_iata,
                target_date or today, airline_iata, limit,
            )
        else:
            return self._search_scheduled(
                dep_iata, arr_iata, flight_iata, flight_date, airline_iata, limit,
            )

    def get_airport_info(self, iata_code: str) -> AirportInfo | None:
        logger.info("get_airport_info(%s): 미지원", iata_code)
        return None

    # ── 실시간 운항현황 API ────────────────────────────────────────

    def _search_realtime(
        self,
        dep_iata: str | None, arr_iata: str | None,
        flight_iata: str | None, query_date: date,
        airline_iata: str | None, limit: int,
    ) -> list[FlightInfo]:
        other_iata, is_arrivals = self._resolve_op(dep_iata, arr_iata)
        operation = OP_RT_ARR if is_arrivals else OP_RT_DEP
        sch_date  = query_date.strftime("%Y%m%d")

        results: list[FlightInfo] = []
        page = 1
        while len(results) < limit:
            items = self._fetch_rt_page(operation, sch_date, page)
            if not items:
                break
            for item in items:
                if not item:
                    continue
                if other_iata and (item.get("airportCode") or "").upper() != other_iata.upper():
                    continue
                fid = (item.get("flightId") or "").upper()
                if flight_iata and fid != flight_iata.upper():
                    continue
                if airline_iata and not fid.startswith(airline_iata.upper()):
                    continue
                fl = self._normalize_realtime(item, dep_iata or "", arr_iata or "", is_arrivals)
                _append_flight_unique(results, fl)
                if len(results) >= limit:
                    break
            if len(items) < PAGE_SIZE:
                break
            page += 1

        logger.info(
            "ICN realtime %s %s→%s → %d편 (date=%s)",
            operation, dep_iata, arr_iata, len(results), sch_date,
        )
        return results

    def _fetch_rt_page(self, operation: str, sch_date: str, page: int) -> list[dict]:
        url = f"{RT_BASE}/{operation}"
        params: dict[str, Any] = {
            "serviceKey": self.service_key,
            "numOfRows": str(PAGE_SIZE),
            "pageNo": str(page),
            "type": "json",
            "schDate": sch_date,
        }
        try:
            r = requests.get(url, params=params, timeout=self.timeout, verify=False)
            logger.info("ICN RT HTTP %d — op=%s date=%s page=%d", r.status_code, operation, sch_date, page)
            if not r.ok:
                logger.warning("ICN RT error: %s", r.text[:300])
                return []
            items = r.json()["response"]["body"].get("items") or []
            if isinstance(items, dict):
                items = [items]
            return items
        except Exception as exc:
            logger.warning("ICN RT 요청 실패 (op=%s): %s", operation, exc)
            return []

    def _normalize_realtime(
        self, item: dict, dep_iata: str, arr_iata: str, is_arrivals: bool
    ) -> FlightInfo:
        flight_id        = item.get("flightId") or ""
        airline_iata_val = "".join(c for c in flight_id if c.isalpha())[:2]
        airline_name     = _AIRLINE_DISPLAY.get(airline_iata_val) or item.get("airline") or ""

        sched_hhmm   = _hhmm(item.get("scheduleDateTime") or "")
        est_hhmm     = _hhmm(item.get("estimatedDateTime") or "")
        primary_time = est_hhmm or sched_hhmm

        other_code   = (item.get("airportCode") or "").upper()
        other_airport = item.get("airport") or ""
        gate         = item.get("gatenumber") or None
        terminal     = item.get("terminalId") or None
        remark       = item.get("remark") or ""
        status       = _REMARK_STATUS.get(remark.strip(), "scheduled")
        raw_master = (item.get("masterflightid") or "").strip().upper()
        codeshare_master = raw_master or None

        if is_arrivals:   # ???→ICN  scheduleDateTime = ICN 도착 시각
            dep_code = other_code or dep_iata.upper()
            arr_code = ICN_IATA
            dep_ap, arr_ap = other_airport, "인천국제공항"
            arr_sched  = primary_time
            dep_sched  = _estimate_other_side(primary_time, dep_code, arr_code, known_is_arr=True)
            dep_delay, arr_delay     = None, _calc_delay(sched_hhmm, est_hhmm)
            dep_gate, arr_gate       = None, gate
            dep_terminal, arr_terminal = None, terminal
        else:             # ICN→???  scheduleDateTime = ICN 출발 시각
            dep_code = ICN_IATA
            arr_code = other_code or arr_iata.upper()
            dep_ap, arr_ap = "인천국제공항", other_airport
            dep_sched  = primary_time
            arr_sched  = _estimate_other_side(primary_time, dep_code, arr_code, known_is_arr=False)
            dep_delay, arr_delay     = _calc_delay(sched_hhmm, est_hhmm), None
            dep_gate, arr_gate       = gate, None
            dep_terminal, arr_terminal = terminal, None

        return FlightInfo(
            flight_iata=flight_id,
            flight_number="".join(c for c in flight_id if c.isdigit()),
            airline_name=airline_name,
            airline_iata=airline_iata_val,
            status=status,
            dep_airport=dep_ap,
            dep_iata=dep_code,
            dep_terminal=dep_terminal,
            dep_gate=dep_gate,
            dep_scheduled=dep_sched,
            dep_delay=dep_delay,
            arr_airport=arr_ap,
            arr_iata=arr_code,
            arr_terminal=arr_terminal,
            arr_gate=arr_gate,
            arr_scheduled=arr_sched,
            arr_delay=arr_delay,
            codeshared_iata=codeshare_master,
        )

    # ── 정기편 스케줄 API ──────────────────────────────────────────

    def _search_scheduled(
        self,
        dep_iata: str | None, arr_iata: str | None,
        flight_iata: str | None, flight_date: str | None,
        airline_iata: str | None, limit: int,
    ) -> list[FlightInfo]:
        other_iata, is_arrivals = self._resolve_op(dep_iata, arr_iata)
        if not other_iata:
            raise ValueError(f"ICN 연관 노선만 조회 가능합니다. dep={dep_iata} arr={arr_iata}")
        operation   = OP_SCHED_ARR if is_arrivals else OP_SCHED_DEP
        target_date = _parse_date(flight_date)

        results: list[FlightInfo] = []
        page = 1
        while len(results) < limit:
            items = self._fetch_sched_page(operation, page)
            if not items:
                break
            for item in items:
                if not item:
                    continue
                if (item.get("airportcode") or "").upper() != other_iata.upper():
                    continue
                if flight_iata and (item.get("flightid") or "").upper() != flight_iata.upper():
                    continue
                if airline_iata:
                    fid = (item.get("flightid") or "").upper()
                    if not fid.startswith(airline_iata.upper()):
                        continue
                if target_date and not _operates_on(item, target_date):
                    continue
                fl = self._normalize_scheduled(item, dep_iata or "", arr_iata or "", is_arrivals)
                _append_flight_unique(results, fl)
                if len(results) >= limit:
                    break
            if len(items) < PAGE_SIZE:
                break
            page += 1

        logger.info(
            "ICN sched %s %s→%s → %d편 (date=%s airline=%s page=%d)",
            operation, dep_iata, arr_iata, len(results), flight_date, airline_iata, page,
        )
        return results

    def _fetch_sched_page(self, operation: str, page: int) -> list[dict]:
        url = f"{SCHED_BASE}/{operation}"
        params: dict[str, Any] = {
            "serviceKey": self.service_key,
            "numOfRows": str(PAGE_SIZE),
            "pageNo": str(page),
            "type": "json",
        }
        try:
            r = requests.get(url, params=params, timeout=self.timeout, verify=False)
            logger.info("ICN sched HTTP %d — op=%s page=%d", r.status_code, operation, page)
            if not r.ok:
                logger.warning("ICN sched error: %s", r.text[:300])
                return []
            items = r.json()["response"]["body"].get("items") or []
            if isinstance(items, dict):
                items = [items]
            return items
        except Exception as exc:
            logger.warning("ICN sched 요청 실패 (op=%s page=%d): %s", operation, page, exc)
            return []

    def _normalize_scheduled(
        self, item: dict, dep_iata: str, arr_iata: str, is_arrivals: bool
    ) -> FlightInfo:
        flight_id        = item.get("flightid") or ""
        airline_iata_val = "".join(c for c in flight_id if c.isalpha())[:2]
        airline_name     = _AIRLINE_DISPLAY.get(airline_iata_val) or item.get("airline") or ""
        scheduled_time   = _hhmm(item.get("st") or "")

        other_airport = item.get("airport") or ""
        other_code    = (item.get("airportcode") or "").upper()
        raw_master = (item.get("masterflightid") or "").strip().upper()
        codeshare_master = raw_master or None

        if is_arrivals:   # ???→ICN  st = ICN 도착 시각
            dep_code = other_code or dep_iata.upper()
            arr_code = ICN_IATA
            dep_ap, arr_ap = other_airport, "인천국제공항"
            arr_sched = scheduled_time
            dep_sched = _estimate_other_side(scheduled_time, dep_code, arr_code, known_is_arr=True)
        else:             # ICN→???  st = ICN 출발 시각
            dep_code = ICN_IATA
            arr_code = other_code or arr_iata.upper()
            dep_ap, arr_ap = "인천국제공항", other_airport
            dep_sched = scheduled_time
            arr_sched = _estimate_other_side(scheduled_time, dep_code, arr_code, known_is_arr=False)

        return FlightInfo(
            flight_iata=flight_id,
            flight_number="".join(c for c in flight_id if c.isdigit()),
            airline_name=airline_name,
            airline_iata=airline_iata_val,
            status="scheduled",
            dep_airport=dep_ap,
            dep_iata=dep_code,
            dep_terminal=None,
            dep_gate=None,
            dep_scheduled=dep_sched,
            dep_delay=None,
            arr_airport=arr_ap,
            arr_iata=arr_code,
            arr_terminal=None,
            arr_gate=None,
            arr_scheduled=arr_sched,
            arr_delay=None,
            codeshared_iata=codeshare_master,
            schedule_start=item.get("firstdate"),
            schedule_end=item.get("lastdate"),
            operating_days=_days_str(item),
        )

    # ── 공통 헬퍼 ─────────────────────────────────────────────────

    def _resolve_op(
        self, dep_iata: str | None, arr_iata: str | None
    ) -> tuple[str, bool]:
        """(other_airport_iata, is_arrivals) 결정."""
        dep = (dep_iata or "").upper()
        arr = (arr_iata or "").upper()
        if dep and arr:
            if arr == ICN_IATA: return dep, True
            if dep == ICN_IATA: return arr, False
            return dep, True
        if dep: return ("", False) if dep == ICN_IATA else (dep, True)
        if arr: return ("", True)  if arr == ICN_IATA else (arr, False)
        return "", True


# router.py 호환
AviationClient = IncheonAirportClient


def _safe_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None
