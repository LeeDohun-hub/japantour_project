"""docs/chat_answerable_questions.md의 ID로 /chat 말뭉치 평가셋을 생성한다."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "raw" / "tour_knowledge.csv"
DEFAULT_QUESTIONS = PROJECT_ROOT / "docs" / "chat_answerable_questions.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation" / "data" / "chat_corpus_eval.json"
ID_RE = re.compile(r"`(J_[A-Z]+_\d+_q\d+)`\s+—\s+(.+)$")


def load_source(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {str(row["id"]): row for row in csv.DictReader(f)}


def load_selected_ids(path: Path) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ID_RE.search(line)
        if match:
            selected.append((match.group(1), match.group(2).strip()))
    return selected


def build_dataset(source_path: Path, questions_path: Path) -> list[dict]:
    source = load_source(source_path)
    selected = load_selected_ids(questions_path)
    if not selected:
        raise ValueError(f"질문 ID를 찾지 못했습니다: {questions_path}")

    records: list[dict] = []
    errors: list[str] = []
    for record_id, documented_question in selected:
        row = source.get(record_id)
        if row is None:
            errors.append(f"{record_id}: CSV에 없음")
            continue
        question = str(row.get("question_ja") or "").strip()
        answer = str(row.get("answer_ja") or "").strip()
        if question != documented_question:
            errors.append(
                f"{record_id}: 문서={documented_question!r} CSV={question!r}"
            )
            continue
        if not question or not answer:
            errors.append(f"{record_id}: 질문 또는 정답이 비어 있음")
            continue
        records.append(
            {
                "id": record_id,
                "question": question,
                "ground_truth": answer,
                "category": str(row.get("category") or ""),
                "area": str(row.get("area") or ""),
                "reply_language": "日本語",
            }
        )

    if errors:
        raise ValueError("평가셋 검증 실패:\n" + "\n".join(errors))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="/chat 말뭉치 RAGAS 평가셋 생성")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    records = build_dataset(args.source, args.questions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    by_category: dict[str, int] = {}
    for record in records:
        category = record["category"]
        by_category[category] = by_category.get(category, 0) + 1
    print(f"[DONE] {len(records)}건 저장: {args.output}")
    print("[CATEGORY] " + ", ".join(f"{k}={v}" for k, v in sorted(by_category.items())))


if __name__ == "__main__":
    main()
