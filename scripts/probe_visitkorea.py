#!/usr/bin/env python3
"""한국관광공사 TourAPI (JpnService2) 프로브 — searchFestival2 / searchStay2.

Usage (repo root):
  python scripts/probe_visitkorea.py

Requires INCHEONTRANSPORT_API_KEY in .env (data.go.kr 공통 인증키).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.api.visitkorea_client import VisitKoreaClient  # noqa: E402


def main() -> int:
    client = VisitKoreaClient()
    if not client.is_configured:
        print("ERROR: INCHEONTRANSPORT_API_KEY not set in .env")
        return 1

    report = client.probe()
    out_path = ROOT / "data" / "cache" / "visitkorea_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Windows console (cp932) safe summary
    fest = report.get("searchFestival2") or {}
    stay = report.get("searchStay2") or {}
    print(f"configured: {report.get('configured')}")
    print(
        f"searchFestival2: code={fest.get('result_code')} total={fest.get('total_count')} "
        f"samples={fest.get('sample_count')}"
    )
    def _safe(s: str) -> str:
        return (s or "")[:60].encode("ascii", errors="replace").decode("ascii")

    if fest.get("samples"):
        print(f"  first title: {_safe(fest['samples'][0].get('title', ''))}")
    print(
        f"searchStay2: code={stay.get('result_code')} total={stay.get('total_count')} "
        f"samples={stay.get('sample_count')}"
    )
    if stay.get("samples"):
        print(f"  first title: {_safe(stay['samples'][0].get('title', ''))}")
    print(f"\n(full JSON -> {out_path})")

    fest = report.get("searchFestival2") or {}
    stay = report.get("searchStay2") or {}
    ok_codes = {"00", "0000"}

    fest_ok = fest.get("result_code") in ok_codes and fest.get("sample_count", 0) > 0
    stay_ok = stay.get("result_code") in ok_codes and stay.get("sample_count", 0) > 0

    if fest.get("error") or stay.get("error"):
        return 2
    if not fest_ok and not stay_ok:
        print("\nWARN: both endpoints returned no items or non-OK resultCode - check API approval / key.")
        return 3
    if not fest_ok:
        print("\nWARN: searchFestival2 had no samples (may be off-season or area filter).")
    if not stay_ok:
        print("\nWARN: searchStay2 had no samples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
