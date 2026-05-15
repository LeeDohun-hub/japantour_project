"""FAISS / pgvector 검색 품질을 비교하는 간단한 벤치마크.

실행 예:
    python -m evaluation.scripts.benchmark_vector_backends
    python -m evaluation.scripts.benchmark_vector_backends --backend faiss
    python -m evaluation.scripts.benchmark_vector_backends --top-k 3
"""

from __future__ import annotations

import argparse
import json
import io
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv(PROJECT_ROOT / ".env")

EVAL_PATH = PROJECT_ROOT / "evaluation" / "data" / "tour_eval.json"

from src.chain.router import RAG_CATEGORY_MAP
from src.chain.vector_store import FaissVectorStore, PgVectorStore


def load_cases() -> list[dict]:
    with open(EVAL_PATH, encoding="utf-8") as f:
        return json.load(f)


def matched_keywords(results: list[dict], expected_keywords: list[str]) -> bool:
    if not expected_keywords:
        return bool(results)
    for result in results:
        haystack = f"{result.get('question_ja', '')} {result.get('answer_ja', '')}".lower()
        if any(keyword.lower() in haystack for keyword in expected_keywords):
            return True
    return False


def run_case(store, case: dict, top_k: int) -> dict:
    query = case["question"]
    rag_category = RAG_CATEGORY_MAP.get(case.get("expected_category", ""), "")
    area = case.get("expected_area", "") or ""
    expected_keywords = case.get("expected_result_keywords") or case.get("expected_keyword_contains") or []

    scenarios = [
        ("no_filter", "", ""),
        ("category", rag_category, ""),
        ("category_area", rag_category, area),
    ]

    results = []
    for name, category_filter, area_filter in scenarios:
        search_results = store.search(
            query=query,
            category=category_filter,
            area=area_filter,
            top_k=top_k,
        )
        results.append(
            {
                "mode": name,
                "hit_at_1": matched_keywords(search_results[:1], expected_keywords),
                "hit_at_k": matched_keywords(search_results, expected_keywords),
                "count": len(search_results),
                "top_result": search_results[0]["question_ja"][:60] if search_results else "",
            }
        )
    return {
        "id": case["id"],
        "question": query,
        "backend": store.backend_name,
        "results": results,
    }


def print_report(rows: list[dict]) -> None:
    summary: dict[str, dict[str, int]] = {}

    for row in rows:
        print(f"\n[{row['backend']}] {row['id']}  {row['question']}")
        for item in row["results"]:
            hit1 = "✅" if item["hit_at_1"] else "❌"
            hitk = "✅" if item["hit_at_k"] else "❌"
            print(
                f"  - {item['mode']:<14} hit@1={hit1}  hit@k={hitk}  count={item['count']:<2d}  "
                f"top={item['top_result']}"
            )
            backend_summary = summary.setdefault(
                f"{row['backend']}::{item['mode']}",
                {"cases": 0, "hit1": 0, "hitk": 0},
            )
            backend_summary["cases"] += 1
            backend_summary["hit1"] += int(item["hit_at_1"])
            backend_summary["hitk"] += int(item["hit_at_k"])

    print("\n" + "=" * 70)
    print("Summary")
    for key, stats in sorted(summary.items()):
        cases = stats["cases"]
        print(
            f"{key:<26}  hit@1={stats['hit1']}/{cases} ({stats['hit1'] / cases * 100:.1f}%)"
            f"  hit@k={stats['hitk']}/{cases} ({stats['hitk'] / cases * 100:.1f}%)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="벡터 검색 백엔드 벤치마크")
    parser.add_argument("--backend", choices=["faiss", "pgvector", "both"], default="both")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    stores = []
    if args.backend in {"faiss", "both"}:
        stores.append(FaissVectorStore())
    if args.backend in {"pgvector", "both"}:
        stores.append(PgVectorStore())

    cases = load_cases()
    rows: list[dict] = []

    for store in stores:
        if not store.is_ready():
            print(f"[SKIP] backend={store.backend_name} 는 아직 준비되지 않았습니다.")
            continue
        for case in cases:
            rows.append(run_case(store, case, top_k=args.top_k))

    if not rows:
        print("실행 가능한 백엔드가 없습니다. FAISS 인덱스 또는 pgvector 적재를 먼저 준비하세요.")
        return

    print_report(rows)


if __name__ == "__main__":
    main()
