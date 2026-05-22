#!/usr/bin/env python3
"""한국공항공사 항공편 API 연결 확인 (openapi.airport.co.kr + odcloud)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> None:
    dep = sys.argv[1] if len(sys.argv) > 1 else "HND"
    arr = sys.argv[2] if len(sys.argv) > 2 else "GMP"
    date = sys.argv[3] if len(sys.argv) > 3 else "2026-06-26"

    from src.api.korea_airports_flight_client import (
        probe_airport_co_kr_key,
        probe_odcloud_key,
    )
    from src.api.aviation_client import search_route_flights

    ok_a, msg_a = probe_airport_co_kr_key()
    print(f"openapi.airport.co.kr (15000126): {'OK' if ok_a else 'FAIL'} - {msg_a}")

    ok_o, msg_o = probe_odcloud_key()
    print(f"api.odcloud.kr (15003087): {'OK' if ok_o else 'FAIL'} - {msg_o}")

    flights, warning, source = search_route_flights(dep, arr, date, limit=10)
    print(f"route {dep}->{arr} {date}: {len(flights)} flights (source={source})")
    if warning:
        print("warning:", warning)
    for f in flights[:5]:
        print(f"  {f.flight_iata} {f.dep_iata} {f.dep_scheduled} -> {f.arr_iata} {f.arr_scheduled}")


if __name__ == "__main__":
    main()
