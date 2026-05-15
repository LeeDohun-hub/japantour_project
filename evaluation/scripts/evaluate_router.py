"""라우터 분류 정확도 + 파이프라인 출력 평가 스크립트.

실행:
    python -m evaluation.scripts.evaluate_router
    python -m evaluation.scripts.evaluate_router --ids T001 T003 T019
    python -m evaluation.scripts.evaluate_router --no-answer    # 분류만 테스트
    python -m evaluation.scripts.evaluate_router --output results.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_EVAL_PATH = PROJECT_ROOT / "evaluation" / "data" / "tour_eval.json"
LEGACY_EVAL_PATH = PROJECT_ROOT / "data" / "evaluation" / "tour_eval.json"


def _load_cases(ids: list[str] | None = None) -> list[dict]:
    eval_path = DEFAULT_EVAL_PATH if DEFAULT_EVAL_PATH.exists() else LEGACY_EVAL_PATH
    with open(eval_path, encoding="utf-8") as f:
        cases = json.load(f)
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    return cases


def _classify_only(case: dict, client) -> dict:
    from src.chain.router import _classify

    start = time.perf_counter()
    result = _classify(case["question"], client)
    elapsed = time.perf_counter() - start

    expected_cat = case["expected_category"]
    got_cat = result.category
    cat_ok = got_cat == expected_cat

    kw_checks = case.get("expected_keyword_contains", [])
    kw_ok = all(kw.lower() in result.keyword.lower() for kw in kw_checks)

    return {
        "id": case["id"],
        "question": case["question"][:60],
        "expected_category": expected_cat,
        "got_category": got_cat,
        "category_ok": cat_ok,
        "got_keyword": result.keyword,
        "keyword_ok": kw_ok,
        "is_fallback": result.is_fallback,
        "elapsed_ms": round(elapsed * 1000),
    }


def _full_pipeline(case: dict, client) -> dict:
    from src.chain.router import route_and_answer

    start = time.perf_counter()
    result = route_and_answer(
        user_message=case["question"],
        reply_language=case["reply_language"],
        history=[],
        openai_client=client,
    )
    elapsed = time.perf_counter() - start

    expected_cat = case["expected_category"]
    cat_ok = result.category == expected_cat

    kw_checks = case.get("expected_keyword_contains", [])
    kw_ok = all(kw.lower() in result.keyword.lower() for kw in kw_checks)

    return {
        "id": case["id"],
        "question": case["question"][:60],
        "expected_category": expected_cat,
        "got_category": result.category,
        "category_ok": cat_ok,
        "got_keyword": result.keyword,
        "keyword_ok": kw_ok,
        "sources_used": result.sources_used,
        "rag_count": result.rag_count,
        "places_count": result.places_count,
        "reply_preview": result.reply[:120] if result.reply else "",
        "is_fallback": result.is_fallback,
        "elapsed_ms": round(elapsed * 1000),
    }


def _print_row(r: dict, full: bool) -> None:
    cat_mark = "✅" if r["category_ok"] else "❌"
    kw_mark = "✅" if r["keyword_ok"] else "⚠ "
    parts = [
        f"{r['id']:5s}",
        f"{cat_mark} {r['got_category']:12s}",
        f"{kw_mark} kw={r['got_keyword'][:25]:<25s}",
        f"{r['elapsed_ms']:4d}ms",
    ]
    if full:
        parts.append(f"src={','.join(r.get('sources_used', []))}")
        parts.append(f"rag={r.get('rag_count', 0)} places={r.get('places_count', 0)}")
    print("  ".join(parts))
    if not r["category_ok"]:
        print(f"       ↳ expected: {r['expected_category']}")
    if full and r.get("reply_preview"):
        print(f"       ↳ {r['reply_preview']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="라우터 평가")
    parser.add_argument("--ids", nargs="+", help="특정 케이스 ID만 실행 (예: T001 T003)")
    parser.add_argument("--no-answer", action="store_true", help="분류만 테스트 (응답 생성 생략)")
    parser.add_argument("--output", type=str, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    from openai import OpenAI
    client = OpenAI()

    cases = _load_cases(args.ids)
    print(f"\n[평가 시작] {len(cases)}개 케이스  mode={'classify-only' if args.no_answer else 'full-pipeline'}\n")

    results = []
    for case in cases:
        if args.no_answer:
            r = _classify_only(case, client)
        else:
            r = _full_pipeline(case, client)
        results.append(r)
        _print_row(r, full=not args.no_answer)

    # ── 요약 ──────────────────────────────────────────────────────────
    n = len(results)
    cat_acc = sum(1 for r in results if r["category_ok"]) / n * 100
    kw_acc = sum(1 for r in results if r["keyword_ok"]) / n * 100
    avg_ms = sum(r["elapsed_ms"] for r in results) / n

    print(f"\n{'─'*60}")
    print(f"분류 정확도 : {cat_acc:.1f}%  ({sum(1 for r in results if r['category_ok'])}/{n})")
    print(f"키워드 포함 : {kw_acc:.1f}%  ({sum(1 for r in results if r['keyword_ok'])}/{n})")
    print(f"평균 응답  : {avg_ms:.0f}ms")

    if not args.no_answer:
        rag_used = sum(1 for r in results if r.get("rag_count", 0) > 0)
        places_used = sum(1 for r in results if r.get("places_count", 0) > 0)
        print(f"RAG 활용   : {rag_used}/{n}건")
        print(f"Places 활용: {places_used}/{n}건")

    # 실패 케이스 목록
    failed = [r for r in results if not r["category_ok"]]
    if failed:
        print(f"\n[분류 실패 {len(failed)}건]")
        for r in failed:
            print(f"  {r['id']}: '{r['question']}' → {r['got_category']} (expected {r['expected_category']})")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n결과 저장: {out_path}")

    print()


if __name__ == "__main__":
    main()
