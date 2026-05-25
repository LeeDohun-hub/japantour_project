"""Postgres 연결 및 pgvector(vector) 확장 확인."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", encoding="utf-8")


def main() -> int:
    try:
        import psycopg
    except ImportError:
        print("psycopg 미설치: pip install psycopg[binary]")
        return 1

    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "japantour")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")

    print(f"연결 시도: {user}@{host}:{port}/{db}")
    try:
        conn = psycopg.connect(
            host=host,
            port=int(port),
            dbname=db,
            user=user,
            password=password,
            connect_timeout=8,
        )
    except Exception as exc:
        print(f"연결 실패: {exc}")
        print("→ docker compose up -d 또는 scripts\\dev-up.ps1 실행")
        return 1

    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        has_vector = cur.fetchone()[0]
    conn.close()

    if has_vector:
        print("OK: pgvector(vector) 확장 사용 가능")
        return 0

    print("실패: vector 확장 없음 (Windows 기본 Postgres 등)")
    print("→ docker compose up -d 로 japantour-pg 사용 (scripts\\dev-up.ps1)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
