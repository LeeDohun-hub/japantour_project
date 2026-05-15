"""AviationStack API client for flight schedule, status, and airport info."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

AVIATION_BASE_URL = "http://api.aviationstack.com/v1"

# Korean/Japanese city or airport name → IATA code
AIRPORT_ALIASES: dict[str, str] = {
    # Korea
    "인천": "ICN", "인천공항": "ICN", "인천국제공항": "ICN",
    "김포": "GMP", "김포공항": "GMP",
    "부산": "PUS", "김해": "PUS", "김해공항": "PUS",
    "제주": "CJU", "제주공항": "CJU",
    "대구": "TAE", "청주": "CJJ",
    "광주": "KWJ", "무안": "MWX",
    "서울": "ICN",
    # Japan
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
    "高松": "TAK",
    "松山": "MYJ",
    "鹿児島": "KOJ", "가고시마": "KOJ",
}


def resolve_iata(name: str) -> str | None:
    """Convert city/airport name to IATA code. Returns None if not found."""
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
    status: str        # scheduled | active | landed | cancelled | incident | diverted
    dep_airport: str
    dep_iata: str
    dep_terminal: str | None
    dep_gate: str | None
    dep_scheduled: str | None   # ISO 8601 string
    dep_delay: int | None       # minutes, None if no delay
    arr_airport: str
    arr_iata: str
    arr_terminal: str | None
    arr_gate: str | None
    arr_scheduled: str | None
    arr_delay: int | None
    codeshared_iata: str | None = None


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


class AviationClient:
    """Wrapper for AviationStack REST API (free plan: HTTP only, 100 req/month)."""

    def __init__(self, access_key: str | None = None, timeout: int = 12):
        self.access_key = access_key or os.getenv("AVIATIONSTACK_API_KEY")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key)

    def search_flights(
        self,
        dep_iata: str | None = None,
        arr_iata: str | None = None,
        flight_iata: str | None = None,
        flight_date: str | None = None,
        limit: int = 5,
    ) -> list[FlightInfo]:
        """노선 스케줄 또는 항공편 상태 조회."""
        if not self.access_key:
            raise ValueError("AviationStack API key is not configured.")

        params: dict[str, Any] = {
            "access_key": self.access_key,
            "limit": max(1, min(limit, 10)),
        }
        if dep_iata:
            params["dep_iata"] = dep_iata.upper()
        if arr_iata:
            params["arr_iata"] = arr_iata.upper()
        if flight_iata:
            params["flight_iata"] = flight_iata.upper()
        if flight_date:
            params["flight_date"] = flight_date

        safe_params = {k: v for k, v in params.items() if k != "access_key"}
        response = requests.get(
            f"{AVIATION_BASE_URL}/flights",
            params=params,
            timeout=self.timeout,
        )
        logger.info("AviationStack flights HTTP %d — params=%r", response.status_code, safe_params)
        if not response.ok:
            logger.warning("AviationStack error body: %s", response.text[:400])
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise ValueError(f"AviationStack error: {data['error']}")
        return [self._normalize_flight(f) for f in (data.get("data") or [])]

    def get_airport_info(self, iata_code: str) -> AirportInfo | None:
        """공항 정보 조회."""
        if not self.access_key:
            raise ValueError("AviationStack API key is not configured.")

        response = requests.get(
            f"{AVIATION_BASE_URL}/airports",
            params={"access_key": self.access_key, "iata_code": iata_code.upper()},
            timeout=self.timeout,
        )
        logger.info("AviationStack airports HTTP %d — iata=%s", response.status_code, iata_code)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise ValueError(f"AviationStack error: {data['error']}")
        airports = data.get("data") or []
        if not airports:
            return None
        return self._normalize_airport(airports[0])

    def _normalize_flight(self, f: dict) -> FlightInfo:
        dep = f.get("departure") or {}
        arr = f.get("arrival") or {}
        airline = f.get("airline") or {}
        flight = f.get("flight") or {}
        codeshared = f.get("codeshared") or {}
        return FlightInfo(
            flight_iata=flight.get("iata") or "",
            flight_number=flight.get("number") or "",
            airline_name=airline.get("name") or "",
            airline_iata=airline.get("iata") or "",
            status=f.get("flight_status") or "unknown",
            dep_airport=dep.get("airport") or "",
            dep_iata=dep.get("iata") or "",
            dep_terminal=dep.get("terminal"),
            dep_gate=dep.get("gate"),
            dep_scheduled=dep.get("scheduled"),
            dep_delay=_safe_int(dep.get("delay")),
            arr_airport=arr.get("airport") or "",
            arr_iata=arr.get("iata") or "",
            arr_terminal=arr.get("terminal"),
            arr_gate=arr.get("gate"),
            arr_scheduled=arr.get("scheduled"),
            arr_delay=_safe_int(arr.get("delay")),
            codeshared_iata=(codeshared.get("flight_iata") if codeshared else None),
        )

    def _normalize_airport(self, a: dict) -> AirportInfo:
        return AirportInfo(
            name=a.get("airport_name") or a.get("name") or "",
            iata=a.get("iata_code") or "",
            icao=a.get("icao_code"),
            country_name=a.get("country_name"),
            city_iata=a.get("city_iata_code"),
            timezone=a.get("timezone"),
            latitude=_safe_float(a.get("latitude")),
            longitude=_safe_float(a.get("longitude")),
        )


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
