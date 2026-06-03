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
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

# ── 인천공항 지상교통 API ───────────────────────────────────────────
BUS_BASE  = "http://apis.data.go.kr/B551177/BusInformation"
OP_BUS    = "getBusInfo"
TAXI_BASE = "http://apis.data.go.kr/B551177/StatusOfTaxi"
OP_TAXI   = "getTaxiStatus"

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
    ("HND", "GMP"): 150, ("GMP", "HND"): 150,
    ("NRT", "GMP"): 155, ("GMP", "NRT"): 155,
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


@dataclass(frozen=True)
class AirportBusInfo:
    area: str
    busnumber: str
    busclass: str
    adultfare: str
    cpname: str
    routeinfo: str
    t1ridelo: str
    t2ridelo: str
    t1wdayt: str
    t1wt: str
    t2wdayt: str
    t2wt: str
    toawfirst: str
    toawlast: str
    t1endfirst: str
    t1endlast: str
    t2endfirst: str
    t2endlast: str


@dataclass(frozen=True)
class AirportTaxiStatus:
    terno: str
    updatetime: str
    seoultaxicnt: str
    seoulstandtime: str
    seoultaxistand: str
    incheontaxicnt: str
    incheonstandtime: str
    incheontaxistand: str
    gyenggitaxicnt: str
    gyenggistandtime: str
    gyenggitaxistand: str
    intercitytaxicnt: str
    intercitystandtime: str
    intercitytaxistand: str
    besttaxicnt: str
    beststandtime: str
    bestVantaxistand: str
    vantaxicnt: str
    vanstandtime: str


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


def _extract_items(payload: dict) -> list[dict]:
    """data.go.kr 응답의 items/list/items.item 형태를 모두 평탄화."""
    body = ((payload or {}).get("response") or {}).get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict) and "item" in items:
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    return [x for x in items if isinstance(x, dict)]


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

    def search_airport_buses(
        self,
        area_codes: list[int] | None = None,
        *,
        limit: int = 20,
    ) -> list[AirportBusInfo]:
        """인천공항 공항버스 정보. area: 1서울 2경기 3인천 4강원 5충청 6경상 7전라."""
        if not self.service_key:
            raise ValueError("INCHEONTRANSPORT_API_KEY가 설정되지 않았습니다.")
        codes = area_codes or [1]
        out: list[AirportBusInfo] = []
        seen: set[str] = set()
        for area in codes:
            page = 1
            while len(out) < limit:
                items = self._fetch_bus_page(area, page)
                if not items:
                    break
                for item in items:
                    bus = self._normalize_bus(item)
                    key = f"{bus.area}|{bus.busnumber}|{bus.routeinfo}"
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(bus)
                    if len(out) >= limit:
                        break
                if len(items) < PAGE_SIZE:
                    break
                page += 1
        logger.info("ICN bus areas=%s → %d routes", codes, len(out))
        return out

    def get_taxi_status(
        self,
        terminals: list[str] | None = None,
    ) -> list[AirportTaxiStatus]:
        """인천공항 터미널별 택시 출차/대기 정보. P01=T1, P03=T2."""
        if not self.service_key:
            raise ValueError("INCHEONTRANSPORT_API_KEY가 설정되지 않았습니다.")
        ternos = terminals or ["P01", "P03"]
        out: list[AirportTaxiStatus] = []
        seen: set[str] = set()
        for terno in ternos:
            for item in self._fetch_taxi_page(terno):
                status = self._normalize_taxi(item)
                key = f"{status.terno}|{status.updatetime}|{status.seoultaxistand}|{status.incheontaxistand}"
                if key in seen:
                    continue
                seen.add(key)
                out.append(status)
        logger.info("ICN taxi terminals=%s → %d rows", ternos, len(out))
        return out

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
            return _extract_items(r.json())
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
            return _extract_items(r.json())
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

    # ── 지상교통 API ───────────────────────────────────────────────

    def _fetch_bus_page(self, area: int, page: int) -> list[dict]:
        url = f"{BUS_BASE}/{OP_BUS}"
        params: dict[str, Any] = {
            "serviceKey": self.service_key,
            "numOfRows": str(PAGE_SIZE),
            "pageNo": str(page),
            "area": str(area),
            "type": "json",
        }
        try:
            r = requests.get(url, params=params, timeout=self.timeout, verify=False)
            logger.info("ICN bus HTTP %d — area=%s page=%d", r.status_code, area, page)
            if not r.ok:
                logger.warning("ICN bus error: %s", r.text[:300])
                return []
            return _extract_items(r.json())
        except Exception as exc:
            logger.warning("ICN bus 요청 실패 (area=%s page=%d): %s", area, page, exc)
            return []

    def _fetch_taxi_page(self, terno: str) -> list[dict]:
        url = f"{TAXI_BASE}/{OP_TAXI}"
        params: dict[str, Any] = {
            "serviceKey": self.service_key,
            "numOfRows": "20",
            "pageNo": "1",
            "terno": terno,
            "type": "json",
        }
        try:
            r = requests.get(url, params=params, timeout=self.timeout, verify=False)
            logger.info("ICN taxi HTTP %d — terno=%s", r.status_code, terno)
            if not r.ok:
                logger.warning("ICN taxi error: %s", r.text[:300])
                return []
            return _extract_items(r.json())
        except Exception as exc:
            logger.warning("ICN taxi 요청 실패 (terno=%s): %s", terno, exc)
            return []

    def _normalize_bus(self, item: dict) -> AirportBusInfo:
        def g(k: str) -> str:
            return str(item.get(k) or "").strip()

        return AirportBusInfo(
            area=g("area"),
            busnumber=g("busnumber"),
            busclass=g("busclass"),
            adultfare=g("adultfare"),
            cpname=g("cpname"),
            routeinfo=g("routeinfo"),
            t1ridelo=g("t1ridelo"),
            t2ridelo=g("t2ridelo"),
            t1wdayt=g("t1wdayt"),
            t1wt=g("t1wt"),
            t2wdayt=g("t2wdayt"),
            t2wt=g("t2wt"),
            toawfirst=g("toawfirst"),
            toawlast=g("toawlast"),
            t1endfirst=g("t1endfirst"),
            t1endlast=g("t1endlast"),
            t2endfirst=g("t2endfirst"),
            t2endlast=g("t2endlast"),
        )

    def _normalize_taxi(self, item: dict) -> AirportTaxiStatus:
        def g(k: str) -> str:
            return str(item.get(k) or "").strip()

        return AirportTaxiStatus(
            terno=g("terno"),
            updatetime=g("updatetime"),
            seoultaxicnt=g("seoultaxicnt"),
            seoulstandtime=g("seoulstandtime"),
            seoultaxistand=g("seoultaxistand"),
            incheontaxicnt=g("incheontaxicnt"),
            incheonstandtime=g("incheonstandtime"),
            incheontaxistand=g("incheontaxistand"),
            gyenggitaxicnt=g("gyenggitaxicnt"),
            gyenggistandtime=g("gyenggistandtime"),
            gyenggitaxistand=g("gyenggitaxistand"),
            intercitytaxicnt=g("intercitytaxicnt"),
            intercitystandtime=g("intercitystandtime"),
            intercitytaxistand=g("intercitytaxistand"),
            besttaxicnt=g("besttaxicnt"),
            beststandtime=g("beststandtime"),
            bestVantaxistand=g("bestVantaxistand"),
            vantaxicnt=g("vantaxicnt"),
            vanstandtime=g("vanstandtime"),
        )

    # ── 공통 헬퍼 ─────────────────────────────────────────────────

    def _resolve_op(
        self, dep_iata: str | None, arr_iata: str | None
    ) -> tuple[str, bool]:
        """(other_airport_iata, is_arrivals) 결정."""
        dep = (dep_iata or "").upper()
        arr = (arr_iata or "").upper()
        if dep and arr:
            if arr == ICN_IATA:
                return dep, True
            if dep == ICN_IATA:
                return arr, False
            raise ValueError(
                f"인천공항 API는 ICN 연관 노선만 지원합니다 (요청: {dep}→{arr}). "
                "김포·김해·제주 등은 한국공항공사(odcloud) API를 사용하세요."
            )
        if dep: return ("", False) if dep == ICN_IATA else (dep, True)
        if arr: return ("", True)  if arr == ICN_IATA else (arr, False)
        return "", True


# router.py 호환
AviationClient = IncheonAirportClient


def search_route_flights(
    dep_iata: str,
    arr_iata: str,
    flight_date: str | None = None,
    limit: int = 500,
) -> tuple[list[FlightInfo], str | None, str]:
    """노선별 항공편 조회. (flights, warning, source)."""
    dep = (dep_iata or "").upper()
    arr = (arr_iata or "").upper()
    if not dep or not arr:
        raise ValueError("dep·arr IATA가 필요합니다.")

    from src.api.korea_airports_flight_client import (
        KoreaAirportsFlightClient,
        uses_korea_regional_airport,
    )

    if uses_korea_regional_airport(dep, arr):
        kac = KoreaAirportsFlightClient()
        if not kac.is_configured:
            raise ValueError("INCHEONTRANSPORT_API_KEY가 설정되지 않았습니다.")
        try:
            return kac.search_flights(dep, arr, flight_date, limit=limit)
        except Exception as exc:
            logger.warning("KAC %s→%s failed: %s", dep, arr, exc)
            return [], None, "odcloud"

    icn = IncheonAirportClient()
    if not icn.is_configured:
        raise ValueError("INCHEONTRANSPORT_API_KEY가 설정되지 않았습니다.")
    flights = icn.search_flights(
        dep_iata=dep, arr_iata=arr, flight_date=flight_date, limit=limit
    )
    return flights, None, "icn"


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
