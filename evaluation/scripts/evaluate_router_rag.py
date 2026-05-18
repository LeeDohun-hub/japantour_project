"""프로덕션 파이프라인 전체 평가 (route_and_answer 기반).

평가 항목:
  - category_acc       : 분류 정확도 (expected vs got)
  - keyword_acc        : 키워드 포함율 (expected_keyword_contains)
  - rag_used_rate      : RAG 활용 비율
  - places_used_rate   : Google Places 활용 비율
  - avg_latency_ms     : 평균 응답 시간
  - reply_keyword_acc  : 응답 내 expected_result_keywords 부분 일치율 (--check-reply-keywords 시)

주의:
  - route_and_answer()는 ground_truth를 사용하지 않음 (프로덕션 동작 유지)
  - ground_truth는 Ragas 평가(evaluate_single.py)에서만 사용

실행:
    python -m evaluation.scripts.evaluate_router_rag
    python -m evaluation.scripts.evaluate_router_rag --dataset unseen
    python -m evaluation.scripts.evaluate_router_rag --check-reply-keywords
    python -m evaluation.scripts.evaluate_router_rag --output evaluation/reports/router_rag.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback as _traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import io as _io
if hasattr(sys.stdout, "buffer") and (not sys.stdout.encoding or sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig")):
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

_DATASET_PATHS: dict[str, Path] = {
    "unseen": PROJECT_ROOT / "evaluation" / "data" / "tour_eval_unseen.json",
    "seen":   PROJECT_ROOT / "evaluation" / "data" / "tour_eval_seen.json",
    "all":    PROJECT_ROOT / "evaluation" / "data" / "tour_eval.json",
}
REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"


def _load_cases(dataset: str, ids: list[str] | None = None) -> list[dict]:
    path = _DATASET_PATHS.get(dataset, _DATASET_PATHS["all"])
    if not path.exists():
        fallback = _DATASET_PATHS["all"]
        print(f"[경고] {path.name} 없음 → {fallback.name} 사용 (audit_eval_leakage 먼저 실행 권장)")
        path = fallback
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    return cases


def _run_case(case: dict, client, check_reply_kw: bool) -> dict:
    from src.chain.router import route_and_answer

    logging.basicConfig(level=logging.WARNING)

    start = time.perf_counter()
    try:
        result = route_and_answer(
            user_message=case["question"],
            reply_language=case.get("reply_language", "日本語"),
            history=[],
            openai_client=client,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - start
        print(f"\n[ERROR] {case['id']} route_and_answer() 실패: {exc}")
        _traceback.print_exc()
        return {
            "id": case["id"],
            "question": case["question"],
            "reply_language": case.get("reply_language", "日本語"),
            "expected_category": case["expected_category"],
            "got_category": "ERROR",
            "category_ok": False,
            "got_keyword": "",
            "keyword_ok": False,
            "reply_keyword_ok": None,
            "reply_keyword_ratio": None,
            "sources_used": [],
            "rag_count": 0,
            "places_count": 0,
            "reply": "",
            "is_fallback": True,
            "latency_ms": round(elapsed * 1000),
            "error": str(exc),
        }
    elapsed = time.perf_counter() - start

    expected_cat = case["expected_category"]
    cat_ok = result.category == expected_cat

    kw_checks = case.get("expected_keyword_contains", [])
    kw_ok = all(kw.lower() in result.keyword.lower() for kw in kw_checks)

    reply_kw_ok: bool | None = None
    reply_kw_ratio: float | None = None
    if check_reply_kw:
        reply_kws = case.get("expected_result_keywords", [])
        if reply_kws and result.reply:
            reply_lower = result.reply.lower()
            matched_count = sum(1 for kw in reply_kws if kw.lower() in reply_lower)
            reply_kw_ratio = matched_count / len(reply_kws)
            reply_kw_ok = reply_kw_ratio >= 0.5

    return {
        "id": case["id"],
        "question": case["question"],
        "reply_language": case.get("reply_language", "日本語"),
        "expected_category": expected_cat,
        "got_category": result.category,
        "category_ok": cat_ok,
        "got_keyword": result.keyword,
        "keyword_ok": kw_ok,
        "reply_keyword_ok": reply_kw_ok,
        "reply_keyword_ratio": reply_kw_ratio,
        "sources_used": result.sources_used,
        "rag_count": result.rag_count,
        "places_count": result.places_count,
        "reply": result.reply or "",
        "is_fallback": result.is_fallback,
        "latency_ms": round(elapsed * 1000),
    }


def _print_row(r: dict) -> None:
    cat_mark = "✅" if r["category_ok"] else "❌"
    kw_mark = "✅" if r["keyword_ok"] else "⚠ "
    src = ",".join(r.get("sources_used", [])) or "none"
    line = (
        f"  {r['id']:5s}  {cat_mark} {r['got_category']:12s}  "
        f"{kw_mark} kw={r['got_keyword'][:22]:<22s}  "
        f"src={src:<14s}  rag={r['rag_count']} places={r['places_count']}  "
        f"{r['latency_ms']:4d}ms"
    )
    print(line)
    if not r["category_ok"]:
        print(f"         ↳ expected: {r['expected_category']}")
    if r.get("reply_keyword_ok") is False:
        ratio = r.get("reply_keyword_ratio", 0)
        print(f"         ↳ reply keyword FAIL ({ratio:.0%} 일치)")
    if r.get("reply"):
        print(f"         ↳ {r['reply'][:120]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="프로덕션 파이프라인 전체 평가")
    parser.add_argument(
        "--dataset",
        choices=["unseen", "seen", "all"],
        default="unseen",
        help="평가 데이터셋 (기본: unseen)",
    )
    parser.add_argument("--ids", nargs="+", help="특정 케이스 ID만 실행 (예: T005 T007)")
    parser.add_argument(
        "--check-reply-keywords",
        action="store_true",
        help="expected_result_keywords 응답 내 부분 일치율 검사 (≥50%면 OK)",
    )
    parser.add_argument("--output", type=str, help="결과 JSON 저장 경로 (미지정 시 reports/ 자동 생성)")
    args = parser.parse_args()

    from openai import OpenAI

    client = OpenAI()

    cases = _load_cases(args.dataset, args.ids)
    print(
        f"\n[평가 시작] dataset={args.dataset}  {len(cases)}개 케이스  "
        f"check_reply_kw={args.check_reply_keywords}\n"
    )

    results: list[dict] = []
    for case in cases:
        r = _run_case(case, client, args.check_reply_keywords)
        results.append(r)
        _print_row(r)

    # ── 요약 ─────────────────────────────────────────────────────────────
    n = len(results)
    error_n = sum(1 for r in results if r.get("error"))
    cat_ok_n = sum(1 for r in results if r["category_ok"])
    kw_ok_n = sum(1 for r in results if r["keyword_ok"])
    rag_used_n = sum(1 for r in results if r["rag_count"] > 0)
    places_used_n = sum(1 for r in results if r["places_count"] > 0)
    avg_ms = sum(r["latency_ms"] for r in results) / n

    rk_checked = [r for r in results if r.get("reply_keyword_ok") is not None]
    reply_kw_acc: float | None = (
        sum(1 for r in rk_checked if r["reply_keyword_ok"]) / len(rk_checked) * 100
        if rk_checked
        else None
    )

    print(f"\n{'─'*65}")
    if error_n:
        print(f"[!] route_and_answer() 오류 케이스 : {error_n}/{n} (위 traceback 참조)")
    print(f"분류 정확도    : {cat_ok_n}/{n}  ({cat_ok_n/n*100:.1f}%)")
    print(f"키워드 포함    : {kw_ok_n}/{n}  ({kw_ok_n/n*100:.1f}%)")
    print(f"RAG 활용       : {rag_used_n}/{n}건")
    print(f"Places 활용    : {places_used_n}/{n}건")
    print(f"평균 응답시간  : {avg_ms:.0f}ms")
    if reply_kw_acc is not None:
        print(f"응답 키워드 OK : {sum(1 for r in rk_checked if r['reply_keyword_ok'])}/{len(rk_checked)}  ({reply_kw_acc:.1f}%)")

    failed_cat = [r for r in results if not r["category_ok"] and not r.get("error")]
    if failed_cat:
        print(f"\n[분류 실패 {len(failed_cat)}건]")
        for r in failed_cat:
            print(f"  {r['id']}: '{r['question'][:40]}' → {r['got_category']} (expected {r['expected_category']})")

    summary = {
        "category_acc": round(cat_ok_n / n * 100, 1),
        "keyword_acc": round(kw_ok_n / n * 100, 1),
        "rag_used_rate": round(rag_used_n / n * 100, 1),
        "places_used_rate": round(places_used_n / n * 100, 1),
        "avg_latency_ms": round(avg_ms),
        "reply_keyword_acc": round(reply_kw_acc, 1) if reply_kw_acc is not None else None,
        "error_count": error_n,
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(
        args.output
        or str(REPORTS_DIR / f"router_rag_{args.dataset}_{ts}.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "metadata": {
            "dataset": args.dataset,
            "timestamp": datetime.now().isoformat(),
            "total_cases": n,
            "check_reply_keywords": args.check_reply_keywords,
            "note": "route_and_answer() — ground_truth 미사용 (프로덕션 경로)",
        },
        "summary": summary,
        "results": results,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")
    print()

    if error_n:
        sys.exit(1)


if __name__ == "__main__":
    main()
