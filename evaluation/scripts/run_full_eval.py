"""통합 평가 실행 스크립트 — 모든 eval 단계를 순서대로 실행하고 요약 리포트를 생성.

실행 순서:
  1. audit_eval_leakage --strict            (누수 감사, 실패해도 계속)
  2. evaluate_router --dataset unseen       (분류만: classify-only)
  3. evaluate_router_rag --dataset unseen   (full pipeline + reply keyword check)
  4. benchmark_vector_backends --backend pgvector  (pgvector, top-k 5)
  5. evaluate_router_ragas --dataset unseen (test_dataset.json 있을 때만, Ragas + route_and_answer)
  6. compare_optimizations                  (--skip-compare 없을 때)

출력:
  evaluation/reports/eval_summary_<timestamp>.md

플래그:
    python -m evaluation.scripts.run_full_eval
    python -m evaluation.scripts.run_full_eval --skip-ragas
    python -m evaluation.scripts.run_full_eval --skip-compare
    python -m evaluation.scripts.run_full_eval --skip-ragas --skip-compare
    python -m evaluation.scripts.run_full_eval --production  # vector benchmark에 production 모드 추가
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "buffer") and (not sys.stdout.encoding or sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig")):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"
SCRIPTS_DIR = PROJECT_ROOT / "evaluation" / "scripts"


# ── 유틸 ──────────────────────────────────────────────────────────────────

def _py(*args: str) -> list[str]:
    return [sys.executable, *args]


def _run_step(name: str, cmd: list[str], allow_fail: bool = False) -> dict:
    """단계 실행 — 결과 dict 반환. 터미널에 실시간 출력."""
    print(f"\n{'='*65}")
    print(f"  STEP [{name}]")
    print(f"  CMD : {' '.join(cmd[1:])}")
    print(f"{'='*65}")

    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    ok = proc.returncode == 0
    status = "OK" if ok else ("WARN" if allow_fail else "FAIL")
    print(f"  → {status}  (exit {proc.returncode})")
    return {"name": name, "ok": ok, "skipped": False, "returncode": proc.returncode}


def _skip_step(name: str, reason: str) -> dict:
    print(f"\n  [SKIP] {name}: {reason}")
    return {"name": name, "ok": True, "skipped": True, "skip_reason": reason}


# ── 메트릭 파싱 ─────────────────────────────────────────────────────────

def _parse_router_classify(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        n = len(data)
        if n == 0:
            return None
        cat_acc = sum(1 for r in data if r.get("category_ok")) / n * 100
        kw_acc = sum(1 for r in data if r.get("keyword_ok")) / n * 100
        avg_ms = sum(r.get("elapsed_ms", 0) for r in data) / n
        return {
            "category_acc": round(cat_acc, 1),
            "keyword_acc": round(kw_acc, 1),
            "avg_ms": round(avg_ms),
            "n": n,
        }
    except Exception:
        return None


def _parse_router_rag(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("summary")
    except Exception:
        return None


def _parse_benchmark(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("summary")
    except Exception:
        return None


def _parse_ragas(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("metrics")
    except Exception:
        return None


# ── 요약 생성 ────────────────────────────────────────────────────────────

def _pct(v: float | None) -> str:
    return f"{v:.1f}%" if v is not None else "—"


def _ms(v: float | None) -> str:
    return f"{v:.0f}ms" if v is not None else "—"


def _generate_summary(
    steps: list[dict],
    ts: str,
    classify_path: Path,
    rag_path: Path,
    benchmark_path: Path,
    ragas_path: Path,
) -> Path:
    classify_m = _parse_router_classify(classify_path)
    rag_m = _parse_router_rag(rag_path)
    bench_m = _parse_benchmark(benchmark_path)
    ragas_m = _parse_ragas(ragas_path)

    lines: list[str] = [
        f"# Eval Summary — {ts}",
        "",
        "## 단계 결과",
        "",
        "| 단계 | 결과 |",
        "|------|------|",
    ]
    for s in steps:
        if s["skipped"]:
            status = f"SKIP ({s.get('skip_reason', '')})"
        elif s.get("expected_fail"):
            # audit: 누수 발견은 정상 동작 (exit 1이 expected)
            status = f"⚠ WARN — {s.get('warn_note', 'see logs')}"
        elif s["ok"]:
            status = "✅ OK"
        else:
            status = f"❌ FAIL (exit {s.get('returncode', '?')})"
        lines.append(f"| {s['name']} | {status} |")

    lines += [
        "",
        "---",
        "",
        "## Router — classify-only (unseen, oracle retrieval 없음)",
        "",
    ]
    if classify_m:
        lines += [
            f"- 분류 정확도 : **{_pct(classify_m.get('category_acc'))}**"
            f"  (n={classify_m.get('n')})",
            f"- 키워드 포함 : {_pct(classify_m.get('keyword_acc'))}",
            f"- 평균 응답   : {_ms(classify_m.get('avg_ms'))}",
        ]
    else:
        lines.append("_데이터 없음_")

    lines += [
        "",
        "## Router RAG — full pipeline (unseen, 프로덕션 경로)",
        "",
        "> `route_and_answer()` 사용. ground_truth 미주입.",
        "",
    ]
    if rag_m:
        lines += [
            f"- 분류 정확도    : **{_pct(rag_m.get('category_acc'))}**",
            f"- 키워드 포함    : {_pct(rag_m.get('keyword_acc'))}",
            f"- RAG 활용율     : {_pct(rag_m.get('rag_used_rate'))}",
            f"- Places 활용율  : {_pct(rag_m.get('places_used_rate'))}",
            f"- 평균 응답시간  : {_ms(rag_m.get('avg_latency_ms'))}",
        ]
        if rag_m.get("reply_keyword_acc") is not None:
            lines.append(f"- 응답 키워드 OK : {_pct(rag_m.get('reply_keyword_acc'))}")
    else:
        lines.append("_데이터 없음_")

    lines += [
        "",
        "## Vector Benchmark — FAISS top-5",
        "",
        "| 모드 | hit@1 | hit@k |",
        "|------|-------|-------|",
    ]
    if bench_m:
        for key, v in sorted(bench_m.items()):
            lines.append(
                f"| {key} | {v.get('hit1_pct', 0):.1f}%  ({v.get('hit1')}/{v.get('cases')}) "
                f"| {v.get('hitk_pct', 0):.1f}%  ({v.get('hitk')}/{v.get('cases')}) |"
            )
        lines += [
            "",
            "> `category` / `category_area` 모드는 oracle upper bound.",
            "> `production` 모드(있을 때)는 분류기 예측 카테고리 사용.",
        ]
    else:
        lines.append("_데이터 없음_")

    lines += [
        "",
        "## Ragas — route_and_answer() 프로덕션 경로 (test_dataset.json 기반)",
        "",
        "> `evaluate_router_ragas.py` 사용. `route_and_answer()` 경로. ground_truth는 생성에 미사용.",
        "",
    ]
    if ragas_m:
        for metric, val in ragas_m.items():
            try:
                lines.append(f"- {metric} : **{float(val):.4f}**")
            except (TypeError, ValueError):
                lines.append(f"- {metric} : {val}")
    else:
        lines.append("_데이터 없음 (--skip-ragas 또는 test_dataset.json 없음)_")

    lines += [
        "",
        "---",
        "",
        "## 해석 주의사항",
        "",
        "- **seen vs unseen** : seen 케이스(T001·T002·T003·T006)는 few-shot 노출 → 분류 점수 과대 가능.",
        "- **oracle vs production** : `category`/`category_area` 필터는 oracle upper bound. "
        "  `production` 모드만 실제 운영 정확도 반영.",
        "- **ragas_router** : `evaluate_router_ragas.py` → `route_and_answer()` 경로 (실제 파이프라인). "
        "  `evaluate_router_rag` 는 Ragas 점수 없이 분류/RAG 정확도만 측정.",
        "",
        f"_생성: {datetime.now().isoformat()}_",
    ]

    out_path = REPORTS_DIR / f"eval_summary_{ts}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ── main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="통합 평가 실행")
    parser.add_argument("--skip-ragas", action="store_true", help="Ragas 단계 건너뜀 (OpenAI 비용 절감)")
    parser.add_argument("--skip-compare", action="store_true", help="compare_optimizations 건너뜀")
    parser.add_argument("--production", action="store_true", help="vector benchmark에 production 모드 포함")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    classify_out = REPORTS_DIR / f"router_classify_{ts}.json"
    rag_out = REPORTS_DIR / f"router_rag_{ts}.json"
    bench_out = REPORTS_DIR / f"vector_benchmark_{ts}.json"
    ragas_router_out = REPORTS_DIR / f"router_ragas_{ts}.json"

    steps: list[dict] = []

    # ── 1. Audit ──────────────────────────────────────────────────────────
    # --strict: 누수 발견 시 exit 1. 누수는 '알려진 상태'이므로 overall FAIL 처리하지 않음.
    s = _run_step(
        "audit",
        _py("-m", "evaluation.scripts.audit_eval_leakage", "--strict"),
        allow_fail=True,
    )
    # 누수 발견(exit 1)은 예상된 결과 — summary에 WARN으로 표시
    if not s["ok"] and s.get("returncode") == 1:
        s["expected_fail"] = True
        s["warn_note"] = "leakages found — EVAL_LEAKAGE.md 참조"
        s["ok"] = True  # overall 카운트에서 제외하지 않으려면 ok=True
    steps.append(s)

    # ── 2. Router classify-only ───────────────────────────────────────────
    s = _run_step(
        "router_classify",
        _py(
            "-m", "evaluation.scripts.evaluate_router",
            "--dataset", "unseen",
            "--no-answer",
            "--output", str(classify_out),
        ),
    )
    steps.append(s)

    # ── 3. Router full pipeline ───────────────────────────────────────────
    s = _run_step(
        "router_rag",
        _py(
            "-m", "evaluation.scripts.evaluate_router_rag",
            "--dataset", "unseen",
            "--check-reply-keywords",
            "--output", str(rag_out),
        ),
    )
    steps.append(s)

    # ── 4. Vector benchmark ───────────────────────────────────────────────
    bench_cmd = _py(
        "-m", "evaluation.scripts.benchmark_vector_backends",
        "--backend", "pgvector",
        "--top-k", "5",
        "--output", str(bench_out),
    )
    if args.production:
        bench_cmd.append("--production")
    s = _run_step("vector_benchmark", bench_cmd)
    steps.append(s)

    # ── 5. Ragas — route_and_answer() 기반 (프로덕션 경로) ───────────────
    # evaluate_router_ragas.py: ground_truth는 생성에 미사용, Ragas reference에만 사용
    test_dataset_path = SCRIPTS_DIR / "test_dataset.json"
    if args.skip_ragas:
        steps.append(_skip_step("ragas", "--skip-ragas 지정"))
    elif not test_dataset_path.exists():
        steps.append(_skip_step("ragas", f"test_dataset.json 없음 ({test_dataset_path})"))
    else:
        s = _run_step(
            "ragas_router",
            _py(
                "-m", "evaluation.scripts.evaluate_router_ragas",
                "--dataset", "unseen",
                "--output", str(ragas_router_out),
            ),
        )
        steps.append(s)

    # ── 6. compare_optimizations (선택) ──────────────────────────────────
    if args.skip_compare:
        steps.append(_skip_step("compare_optimizations", "--skip-compare 지정"))
    else:
        s = _run_step(
            "compare_optimizations",
            _py("-m", "evaluation.scripts.compare_optimizations"),
            allow_fail=True,
        )
        steps.append(s)

    # ── 요약 생성 ─────────────────────────────────────────────────────────
    summary_path = _generate_summary(steps, ts, classify_out, rag_out, bench_out, ragas_router_out)

    print(f"\n{'='*65}")
    print("  EVAL COMPLETE")
    print(f"{'='*65}")
    warn_count = sum(1 for s in steps if s.get("expected_fail"))
    fail_count = sum(1 for s in steps if not s.get("ok") and not s.get("skipped") and not s.get("expected_fail"))
    ok_count = len(steps) - fail_count - warn_count
    print(f"  단계: {ok_count} OK  |  {warn_count} WARN  |  {fail_count} FAIL  (total {len(steps)})")
    if warn_count:
        print(f"  WARN = 예상된 결과 (누수 감지 등) — EVAL_LEAKAGE.md 참조")
    print(f"  요약: {summary_path}")
    print()

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
