"""
최적화 설정을 적용한 체인 (평가 스크립트 호환).
현재는 관광 지식베이스 연동 전 단계입니다.
"""
import json
from typing import Generator, Dict
from langchain_openai import ChatOpenAI

from src.chain.prompts import CLASSIFIER_PROMPT, ANSWER_PROMPT as GENERATOR_PROMPT
from src.config import OPENAI_API_KEY
from src.optimization_config import OptimizationConfig, BASELINE
from src.optimizations import apply_optimizations

_NO_KB_CONTEXT = (
    "(지식 베이스에서 검색된 문서가 없습니다. "
    "一般的な韓国旅行の知識に基づいて回答してください。確認をユーザーに押し付ける締めの文は使わないでください。)"
)


def _get_classifier(config: OptimizationConfig) -> ChatOpenAI:
    model = "gpt-4o-mini" if config.use_gpt4 else "gpt-4o-mini"
    return ChatOpenAI(
        model=model,
        temperature=0.0,
        openai_api_key=OPENAI_API_KEY,
    )


def _get_generator(config: OptimizationConfig, streaming: bool = False) -> ChatOpenAI:
    model = "gpt-4o" if config.use_gpt4 else "gpt-4o-mini"
    return ChatOpenAI(
        model=model,
        temperature=0.0,
        openai_api_key=OPENAI_API_KEY,
        streaming=streaming,
    )


def classify(question: str, config: OptimizationConfig = BASELINE) -> dict:
    llm = _get_classifier(config)
    prompt = CLASSIFIER_PROMPT.format(question=question)
    result = llm.invoke(prompt)

    try:
        parsed = json.loads(result.content.strip())
    except json.JSONDecodeError:
        parsed = {"category": "general", "keyword": question[:200]}

    return {
        "question": question,
        "category": parsed.get("category", "general"),
        "keyword": parsed.get("keyword", question) or question,
    }


def retrieve_context(
    category: str,
    keyword: str,
    config: OptimizationConfig = BASELINE,
) -> tuple[str, list[dict]]:
    if category == "invalid":
        return "(invalid query)", []
    raw: list[dict] = []
    optimized = apply_optimizations(raw, config, keyword)
    return _NO_KB_CONTEXT, optimized


def prepare_context(question: str, config: OptimizationConfig = BASELINE) -> dict:
    classification = classify(question, config)
    context, raw_results = retrieve_context(
        classification["category"],
        classification["keyword"],
        config,
    )

    return {
        "question": question,
        "category": classification["category"],
        "keyword": classification["keyword"],
        "context": context,
        "raw_results": raw_results,
        "dur_context": "（観光ナレッジベース未接続のため、補足情報なし）",
        "config_name": config.name,
    }


def stream_answer(context_data: dict, config: OptimizationConfig = BASELINE) -> Generator[str, None, None]:
    llm = _get_generator(config, streaming=True)

    prompt_value = GENERATOR_PROMPT.format_messages(
        question=context_data["question"],
        category=context_data["category"],
        keyword=context_data["keyword"],
        context=context_data["context"],
        dur_context=context_data["dur_context"],
    )

    for chunk in llm.stream(prompt_value):
        if chunk.content:
            yield chunk.content


def generate_answer(context_data: dict, config: OptimizationConfig = BASELINE) -> str:
    llm = _get_generator(config, streaming=False)

    prompt_value = GENERATOR_PROMPT.format_messages(
        question=context_data["question"],
        category=context_data["category"],
        keyword=context_data["keyword"],
        context=context_data["context"],
        dur_context=context_data["dur_context"],
    )

    result = llm.invoke(prompt_value)
    return result.content
