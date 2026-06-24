"""/chat 전용 말뭉치 RAGAS 평가.

검색은 search_chat_corpus(), 답변은 실제 route_and_answer()를 사용한다.

실행 예:
  python -m evaluation.scripts.build_chat_corpus_eval
  python -m evaluation.scripts.evaluate_chat_corpus_ragas --limit 20
  python -m evaluation.scripts.evaluate_chat_corpus_ragas --limit 0
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8")

DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "data" / "chat_corpus_eval.json"
REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"
DEFAULT_TOP_K = 8

# RAGAS 판정 시 사용할 최대 컨텍스트 수.
# Faithfulness/Context Precision은 컨텍스트 개수·길이에 비례해 LLM 호출이 늘어 타임아웃의
# 주원인이 된다. 검색 지표(hit/MRR)는 전체 컨텍스트로 계산하고, RAGAS 판정에 넘기는
# 컨텍스트만 상위 N개로 줄여 호출량을 낮춘다.
RAGAS_MAX_CONTEXTS = 3
# 각 컨텍스트 텍스트도 과도하게 길면 프롬프트가 커지므로 상한을 둔다.
RAGAS_CONTEXT_CHAR_LIMIT = 600


def load_cases(path: Path, limit: int) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if limit <= 0 or limit >= len(cases):
        return cases

    # 문서 순서는 카테고리별 블록이므로 앞에서 자르면 nature만 평가된다.
    # 카테고리별 큐를 라운드로빈해 작은 시험 평가도 전체 분야를 포함시킨다.
    grouped: dict[str, list[dict]] = {}
    category_order: list[str] = []
    for case in cases:
        category = str(case.get("category") or "other")
        if category not in grouped:
            grouped[category] = []
            category_order.append(category)
        grouped[category].append(case)

    selected: list[dict] = []
    index = 0
    while len(selected) < limit:
        added = False
        for category in category_order:
            queue = grouped[category]
            if index < len(queue):
                selected.append(queue[index])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        index += 1
    return selected


def contexts_from_results(results: list[dict]) -> list[str]:
    contexts: list[str] = []
    for result in results:
        question = str(result.get("question_ja") or "").strip()
        answer = str(result.get("answer_ja") or "").strip()
        text = "\n".join(part for part in (question, answer) if part)
        if text:
            contexts.append(text)
    return contexts or ["(内部知識ベースに該当データなし)"]


def generate_case(case: dict, client, top_k: int) -> dict:
    from src.chain.router import route_and_answer, search_chat_corpus

    started = time.perf_counter()
    bundle = search_chat_corpus(case["question"], top_k=top_k)
    contexts = contexts_from_results(bundle.results)
    retrieved_ids = [
        str(result.get("id")) for result in bundle.results if result.get("id")
    ]

    route_result = route_and_answer(
        user_message=case["question"],
        reply_language=case.get("reply_language", "日本語"),
        history=[],
        openai_client=client,
        traveler_profile=None,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        **case,
        "answer": route_result.reply or "",
        "contexts": contexts,
        "retrieved_ids": retrieved_ids,
        "target_retrieved": case["id"] in retrieved_ids,
        "target_rank": (
            retrieved_ids.index(case["id"]) + 1 if case["id"] in retrieved_ids else None
        ),
        "retrieval_backend": bundle.backend,
        "route_category": route_result.category,
        "route_keyword": route_result.keyword,
        "sources_used": route_result.sources_used,
        "rag_count": route_result.rag_count,
        "places_count": route_result.places_count,
        "latency_ms": elapsed_ms,
    }


def run_ragas(records: list[dict]) -> tuple[dict[str, float | None], list[dict]]:
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.run_config import RunConfig
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    dataset = Dataset.from_list(
        [
            {
                "question": record["question"],
                "answer": record["answer"],
                # 판정 호출량을 줄이기 위해 상위 N개 컨텍스트만, 길이도 제한해 전달.
                "contexts": [
                    ctx[:RAGAS_CONTEXT_CHAR_LIMIT]
                    for ctx in record["contexts"][:RAGAS_MAX_CONTEXTS]
                ] or [""],
                "ground_truth": record["ground_truth"],
            }
            for record in records
        ]
    )
    metrics = [
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    ]
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
        run_config=RunConfig(
            # faithfulness/context_precision는 건당 LLM 호출이 많아 90초로는 한 잡을
            # 끝내지 못해 None이 됐다. 잡당 시간을 충분히(240s) 주되, 재시도는 1회로
            # 묶어 누적 폭주(과거 180s×3 → 24분 정체)는 막는다. 컨텍스트 축소
            # (RAGAS_MAX_CONTEXTS/CHAR_LIMIT)와 함께 적용해 잡당 작업량도 낮춘다.
            timeout=240,
            max_retries=1,
            max_wait=10,
            max_workers=2,
        ),
        raise_exceptions=False,
    )
    frame = result.to_pandas()
    metric_names = [metric.name for metric in metrics]
    averages: dict[str, float | None] = {}
    for name in metric_names:
        values = [
            float(value)
            for value in frame[name].tolist()
            if value is not None and not (isinstance(value, float) and math.isnan(value))
        ]
        averages[name] = sum(values) / len(values) if values else None

    per_case: list[dict] = []
    for _, row in frame.iterrows():
        per_case.append(
            {
                name: (
                    None
                    if row.get(name) is None
                    or (isinstance(row.get(name), float) and math.isnan(row.get(name)))
                    else float(row.get(name))
                )
                for name in metric_names
            }
        )
    return averages, per_case


def main() -> None:
    parser = argparse.ArgumentParser(description="/chat 말뭉치 RAGAS 평가")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="평가 건수. 0이면 전체 120건 (기본: 20)",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help="검색·답변 생성만 수행하고 RAGAS 판정은 생략",
    )
    args = parser.parse_args()

    if not args.dataset.exists():
        from evaluation.scripts.build_chat_corpus_eval import build_dataset

        questions = PROJECT_ROOT / "docs" / "chat_answerable_questions.md"
        source = PROJECT_ROOT / "data" / "raw" / "tour_knowledge.csv"
        records = build_dataset(source, questions)
        args.dataset.parent.mkdir(parents=True, exist_ok=True)
        args.dataset.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    from openai import OpenAI

    logging.basicConfig(level=logging.WARNING)
    client = OpenAI()
    cases = load_cases(args.dataset, args.limit)
    print(f"[GENERATE] {len(cases)}건, top_k={args.top_k}")

    records: list[dict] = []
    for index, case in enumerate(cases, 1):
        try:
            record = generate_case(case, client, args.top_k)
            records.append(record)
            mark = "OK" if record["target_retrieved"] else "MISS"
            print(
                f"  {index:03d}/{len(cases):03d} {mark:4s} "
                f"rank={str(record['target_rank']):>4s} "
                f"rag={record['rag_count']} places={record['places_count']} "
                f"{record['latency_ms']}ms {case['id']}"
            )
        except Exception as exc:
            print(f"  {index:03d}/{len(cases):03d} ERROR {case['id']}: {exc}")
            traceback.print_exc()

    if not records:
        raise SystemExit("평가 가능한 결과가 없습니다.")

    metrics: dict[str, float | None] = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or (
        REPORTS_DIR / f"chat_corpus_ragas_{len(records)}_{timestamp}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = output.with_name(output.stem + "_generated.json")
    checkpoint.write_text(
        json.dumps(
            {
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "dataset": str(args.dataset),
                    "pipeline": "search_chat_corpus + route_and_answer",
                    "top_k": args.top_k,
                    "status": "answers_generated_before_ragas",
                },
                "cases": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[CHECKPOINT] {checkpoint}")

    if not args.skip_ragas:
        print(f"[RAGAS] {len(records)}건 평가 시작")
        metrics, per_case_scores = run_ragas(records)
        for record, scores in zip(records, per_case_scores):
            record["ragas"] = scores

    hit_count = sum(1 for record in records if record["target_retrieved"])
    invalid_count = sum(
        1 for record in records if record.get("route_category") == "invalid"
    )
    route_rag_used_count = sum(
        1 for record in records if int(record.get("rag_count") or 0) > 0
    )
    mrr = sum(
        1.0 / record["target_rank"]
        for record in records
        if record["target_rank"]
    ) / len(records)
    summary = {
        "total_cases": len(records),
        "retrieval_hit_rate": hit_count / len(records),
        "retrieval_mrr": mrr,
        "route_accept_rate": (len(records) - invalid_count) / len(records),
        "route_rag_used_rate": route_rag_used_count / len(records),
        "avg_latency_ms": sum(r["latency_ms"] for r in records) / len(records),
        **metrics,
    }

    print("[RESULT]")
    for key, value in summary.items():
        if isinstance(value, float):
            print(f"  {key:24s} {value:.4f}")
        else:
            print(f"  {key:24s} {value}")

    payload = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "dataset": str(args.dataset),
            "pipeline": "search_chat_corpus + route_and_answer",
            "top_k": args.top_k,
            "ragas_version_target": "0.4.x",
            "ground_truth_usage": "RAGAS reference only; never passed to answer generation",
        },
        "summary": summary,
        "cases": records,
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[SAVED] {output}")


if __name__ == "__main__":
    main()
