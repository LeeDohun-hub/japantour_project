"""Ragas 평가 — route_and_answer() 기반 (프로덕션 경로).

평가 원칙:
  - route_and_answer()에는 ground_truth를 절대 입력하지 않음
  - ground_truth는 Ragas 평가 단계에서만 사용 (reference 필드)
  - 컨텍스트는 RAG 검색 결과에서 추출 (실제 파이프라인과 동일)

실행:
    python -m evaluation.scripts.evaluate_router_ragas
    python -m evaluation.scripts.evaluate_router_ragas --dataset unseen
    python -m evaluation.scripts.evaluate_router_ragas --output evaluation/reports/router_ragas.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
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

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")

SCRIPTS_DIR = PROJECT_ROOT / "evaluation" / "scripts"
REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"

_DATASET_PATHS: dict[str, Path] = {
    "unseen": PROJECT_ROOT / "evaluation" / "data" / "tour_eval_unseen.json",
    "seen":   PROJECT_ROOT / "evaluation" / "data" / "tour_eval_seen.json",
    "all":    PROJECT_ROOT / "evaluation" / "data" / "tour_eval.json",
}


def _load_eval_cases(dataset: str) -> list[dict]:
    path = _DATASET_PATHS.get(dataset, _DATASET_PATHS["all"])
    if not path.exists():
        fallback = _DATASET_PATHS["all"]
        print(f"[경고] {path.name} 없음 → {fallback.name} 사용")
        path = fallback
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_ground_truths() -> dict[str, str]:
    """test_dataset.json에서 id → ground_truth 매핑 로드."""
    td_path = SCRIPTS_DIR / "test_dataset.json"
    if not td_path.exists():
        return {}
    with open(td_path, encoding="utf-8") as f:
        data = json.load(f)
    return {item["id"]: item["ground_truth"] for item in data if "ground_truth" in item}


def _collect_rag_contexts(rag_results: list[dict]) -> list[str]:
    """RAG 결과 레코드를 Ragas context 문자열 리스트로 변환."""
    contexts: list[str] = []
    for r in rag_results:
        q = r.get("question_ja", "")
        a = r.get("answer_ja", "")
        text = "\n".join(filter(None, [q, a])).strip()
        if text:
            contexts.append(text)
    return contexts or ["(知識ベースに該当データなし)"]


def _generate_one(case: dict, client, ground_truths: dict[str, str]) -> dict | None:
    """
    1건 처리: route_and_answer() 호출 → 답변 + 컨텍스트 수집.

    ground_truth는 절대 route_and_answer()에 전달하지 않음.
    """
    from src.chain.router import (
        _classify,
        search_rag,
        RAG_CATEGORY_MAP,
        route_and_answer,
    )

    question = case["question"]
    case_id = case["id"]
    gt = ground_truths.get(case_id, "")

    if not gt:
        print(f"  [SKIP] {case_id}: test_dataset.json에 ground_truth 없음")
        return None

    # 1. 컨텍스트 수집 (RAG 검색 — ground_truth 미사용)
    clf = _classify(question, client)
    rag_category = RAG_CATEGORY_MAP.get(clf.category, "")
    rag_bundle = search_rag(clf.keyword, category=rag_category)
    contexts = _collect_rag_contexts(rag_bundle.results)

    # 2. 답변 생성 (route_and_answer — ground_truth 미사용)
    try:
        result = route_and_answer(
            user_message=question,
            reply_language=case.get("reply_language", "日本語"),
            history=[],
            openai_client=client,
        )
        answer = result.reply or ""
        category = result.category
        is_fallback = result.is_fallback
    except Exception as exc:
        print(f"\n[ERROR] {case_id} route_and_answer() 실패: {exc}")
        _traceback.print_exc()
        return None

    print(f"  {case_id}  cat={category}  fallback={is_fallback}  ctx={len(contexts)}건  ans={len(answer)}chars")

    # ground_truth는 Ragas 평가 단계에서만 사용 — 생성에 절대 입력 안 됨
    return {
        "id": case_id,
        "question": question,
        "answer": answer,
        "contexts": contexts,
        "ground_truth": gt,         # Ragas reference용, 생성에 미사용
        "category": category,
        "is_fallback": is_fallback,
    }


def _run_ragas(records: list[dict]) -> dict:
    """Ragas 평가 — ground_truth(reference)는 여기서만 사용."""
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    ragas_data = [
        {
            "question": r["question"],
            "answer": r["answer"],
            "contexts": r["contexts"],
            "ground_truth": r["ground_truth"],
        }
        for r in records
    ]
    dataset = Dataset.from_list(ragas_data)

    eval_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    eval_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

    eval_result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=eval_llm,
        embeddings=eval_embeddings,
    )

    try:
        df = eval_result.to_pandas()
        return {
            col: float(df[col].mean())
            for col in df.columns
            if col not in ("user_input", "retrieved_contexts", "response", "reference")
        }
    except Exception:
        return {m.name: getattr(eval_result, m.name, None) for m in metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ragas 평가 — route_and_answer() 기반")
    parser.add_argument(
        "--dataset",
        choices=["unseen", "seen", "all"],
        default="unseen",
        help="평가 데이터셋 (기본: unseen)",
    )
    parser.add_argument("--output", type=str, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    from openai import OpenAI
    client = OpenAI()

    eval_cases = _load_eval_cases(args.dataset)
    ground_truths = _load_ground_truths()

    if not ground_truths:
        print(f"[ERROR] test_dataset.json 없음 또는 ground_truth 비어있음: {SCRIPTS_DIR / 'test_dataset.json'}")
        sys.exit(1)

    print(f"\n[Ragas 생성] dataset={args.dataset}  {len(eval_cases)}건  ground_truth {len(ground_truths)}건")
    print("  ground_truth는 생성에 미사용 — Ragas 평가 단계에서만 reference로 사용\n")

    records: list[dict] = []
    for case in eval_cases:
        r = _generate_one(case, client, ground_truths)
        if r is not None:
            records.append(r)

    if not records:
        print("[ERROR] 유효한 케이스가 없음 — ground_truth 없거나 route_and_answer() 전부 실패")
        sys.exit(1)

    print(f"\n[Ragas 평가] {len(records)}건으로 평가 시작 (gpt-4o-mini 사용)...")
    try:
        metrics_dict = _run_ragas(records)
    except Exception as exc:
        print(f"\n[ERROR] Ragas 평가 실패: {exc}")
        _traceback.print_exc()
        sys.exit(1)

    print("\n── 결과 ──────────────────────────────────")
    for k, v in metrics_dict.items():
        bar = "█" * int(float(v or 0) * 40) if v is not None else ""
        print(f"  {k:25s} {bar}  {float(v or 0):.4f}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.output or str(REPORTS_DIR / f"router_ragas_{args.dataset}_{ts}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out = {
        "metadata": {
            "dataset": args.dataset,
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(records),
            "note": (
                "route_and_answer() 기반 Ragas 평가. "
                "ground_truth는 생성에 미사용 — Ragas reference 단계에서만 사용."
            ),
            "path": "src/chain/router.py:route_and_answer()",
        },
        "metrics": {k: float(v) if v is not None else None for k, v in metrics_dict.items()},
        "cases": records,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
