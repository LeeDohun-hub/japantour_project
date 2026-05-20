#!/usr/bin/env python3
"""전국공연행사정보표준데이터 API 연결 테스트.

실행:
  python scripts/probe_gyeonggi.py

결과는 data/cache/gyeonggi_probe.json 에도 저장됩니다.
필요 키: INCHEONTRANSPORT_API_KEY (.env)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.api.gyeonggi_events_client import GyeonggiEventsClient  # noqa: E402


def main() -> int:
    client = GyeonggiEventsClient()
    report = client.probe()
    out = ROOT / "data" / "cache" / "gyeonggi_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("ok"):
        print(f"\n✓ API 연결 성공 — {report['row_count']}건 확인")
    else:
        print(f"\n✗ API 연결 실패: {report.get('error')}")
        print("  → INCHEONTRANSPORT_API_KEY 값과 data.go.kr 서비스 신청 여부를 확인하세요.")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
