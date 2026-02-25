"""Japan Tour Project - 여행 지식 데이터 전처리 스크립트.

data/raw/tour_knowledge.csv 를 읽어서
data/processed/tour_knowledge.jsonl 로 저장합니다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

INPUT_CSV = RAW_DIR / "tour_knowledge.csv"
OUTPUT_JSONL = PROCESSED_DIR / "tour_knowledge.jsonl"


REQUIRED_COLUMNS = ["question_ja", "answer_ja"]
OPTIONAL_COLUMNS = ["id", "category", "area", "answer_ko"]


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(
            f"원본 파일이 없습니다: {INPUT_CSV}\n"
            "먼저 data/raw/tour_knowledge.csv 를 준비해 주세요."
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Loading CSV: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)
    print(f"[INFO] Raw rows: {len(df)}")

    # 필수 컬럼 존재 여부 확인
    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        raise ValueError(
            f"필수 컬럼이 누락되었습니다: {missing_required}\n"
            f"현재 CSV 컬럼: {list(df.columns)}"
        )

    # 필요 컬럼만 유지 (없으면 자동으로 무시)
    keep_cols = [c for c in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if c in df.columns]
    df = df[keep_cols].copy()

    # 문자열 컬럼 정리: 앞뒤 공백 제거
    for col in keep_cols:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()

    # 필수 텍스트가 비어 있는 행 제거
    before_drop = len(df)
    for col in REQUIRED_COLUMNS:
        df = df[df[col].notnull() & (df[col].astype(str).str.strip() != "")]
    after_drop = len(df)
    print(f"[INFO] Dropped {before_drop - after_drop} rows with empty required fields.")

    # id가 없으면 문자열 인덱스로 생성
    if "id" not in df.columns:
        df.insert(0, "id", df.index.astype(str))

    print(f"[INFO] Processed rows to write: {len(df)}")

    # JSONL로 저장
    with OUTPUT_JSONL.open("w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            record = {col: row[col] for col in df.columns}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[INFO] Saved JSONL to: {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()

