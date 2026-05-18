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


def run_case(store, case: dict, top_k: int, production_classify=None) -> dict:  # noqa: C901
    query = case["question"]
    oracle_category = RAG_CATEGORY_MAP.get(case.get("expected_category", ""), "")
    area = case.get("expected_area", "") or ""
    expected_keywords = case.get("expected_result_keywords") or case.get("expected_keyword_contains") or []

    scenarios = [
        ("no_filter", "", ""),
        ("category", oracle_category, ""),
        ("category_area", oracle_category, area),
    ]

    # production 모드: 분류기가 예측한 카테고리로 필터
    if production_classify is not None:
        try:
            clf_result = production_classify(query)
            prod_category = RAG_CATEGORY_MAP.get(clf_result.category, "")
        except Exception as e:
            prod_category = ""
            print(f"  [production classify error] {e}")
        scenarios.append(("production", prod_category, ""))

    results = []
    for name, category_filter, area_filter in scenarios:
        try:
            search_results = store.search(
                query=query,
                category=category_filter,
                area=area_filter,
                top_k=top_k,
            )
        except Exception as e:
            import traceback
            print(f"\n[ERROR] {case['id']} backend={store.backend_name} mode={name}: {e}")
            traceback.print_exc()
            raise
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


def build_summary(rows: list[dict]) -> dict[str, dict]:
    summary: dict[str, dict[str, int]] = {}
    for row in rows:
        for item in row["results"]:
            key = f"{row['backend']}::{item['mode']}"
            bucket = summary.setdefault(key, {"cases": 0, "hit1": 0, "hitk": 0})
            bucket["cases"] += 1
            bucket["hit1"] += int(item["hit_at_1"])
            bucket["hitk"] += int(item["hit_at_k"])
    return summary


def print_report(rows: list[dict]) -> None:
    summary = build_summary(rows)

    for row in rows:
        print(f"\n[{row['backend']}] {row['id']}  {row['question']}")
        for item in row["results"]:
            hit1 = "✅" if item["hit_at_1"] else "❌"
            hitk = "✅" if item["hit_at_k"] else "❌"
            print(
                f"  - {item['mode']:<14} hit@1={hit1}  hit@k={hitk}  count={item['count']:<2d}  "
                f"top={item['top_result']}"
            )

    print("\n" + "=" * 70)
    print("Summary")
    for key, stats in sorted(summary.items()):
        cases = stats["cases"]
        print(
            f"{key:<30}  hit@1={stats['hit1']}/{cases} ({stats['hit1'] / cases * 100:.1f}%)"
            f"  hit@k={stats['hitk']}/{cases} ({stats['hitk'] / cases * 100:.1f}%)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="벡터 검색 백엔드 벤치마크")
    parser.add_argument("--backend", choices=["faiss", "pgvector", "both"], default="pgvector")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--production",
        action="store_true",
        help="분류기 예측 카테고리로 필터하는 production 모드 추가 (OpenAI API 필요)",
    )
    parser.add_argument("--output", type=str, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    production_classify = None
    if args.production:
        from openai import OpenAI
        from src.chain.router import _classify as _router_classify
        _client = OpenAI()

        def production_classify(question: str):
            return _router_classify(question, _client)

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
            rows.append(run_case(store, case, top_k=args.top_k, production_classify=production_classify))

    if not rows:
        msg = (
            "[SKIP] 실행 가능한 벡터 백엔드 없음 — 벤치마크 건너뜀.\n"
            "  pgvector: Django ORM + postgresql + pgvector 설정 및 KnowledgeChunk.embedding 채우기 필요.\n"
            "  FAISS: data/vector/tour_knowledge.faiss 빌드 필요 (faiss-cpu 패키지 설치 후 --build)."
        )
        print(msg)
        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps({"note": "no_backends_ready — skip", "summary": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
        sys.exit(0)

    print_report(rows)

    if args.output:
        from datetime import datetime
        summary = build_summary(rows)
        out = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "backend": args.backend,
                "top_k": args.top_k,
                "production_mode": args.production,
                "total_cases": len(cases),
            },
            "summary": {
                k: {
                    "hit1": v["hit1"],
                    "hitk": v["hitk"],
                    "cases": v["cases"],
                    "hit1_pct": round(v["hit1"] / v["cases"] * 100, 1) if v["cases"] else 0,
                    "hitk_pct": round(v["hitk"] / v["cases"] * 100, 1) if v["cases"] else 0,
                }
                for k, v in summary.items()
            },
            "cases": rows,
        }
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
