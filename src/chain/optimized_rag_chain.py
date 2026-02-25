"""
최적화된 RAG 체인
OptimizationConfig를 적용한 RAG 파이프라인
"""
import json
from typing import Generator, Dict
from langchain_openai import ChatOpenAI

from src.chain.prompts import CLASSIFIER_PROMPT, ANSWER_PROMPT as GENERATOR_PROMPT
from src.api.openfda_client import (
    search_by_brand_name,
    search_by_generic_name,
    search_by_indication,
)
from src.api.formatter import format_label_results
from src.config import OPENAI_API_KEY
from src.optimization_config import OptimizationConfig, BASELINE
from src.optimizations import apply_optimizations


def _get_classifier(config: OptimizationConfig) -> ChatOpenAI:
    """분류용 LLM (GPT-4 사용 여부에 따라)"""
    model = "gpt-4o-mini" if config.use_gpt4 else "gpt-4o-mini"
    return ChatOpenAI(
        model=model,
        temperature=0.0,
        openai_api_key=OPENAI_API_KEY,
    )


def _get_generator(config: OptimizationConfig, streaming: bool = False) -> ChatOpenAI:
    """답변 생성용 LLM (GPT-4 사용 여부에 따라)"""
    # GPT-4 사용 여부에 따라 모델 선택
    model = "gpt-4o" if config.use_gpt4 else "gpt-4o-mini"
    
    return ChatOpenAI(
        model=model,
        temperature=0.0,  # Faithfulness 향상을 위해 낮은 temperature
        openai_api_key=OPENAI_API_KEY,
        streaming=streaming,
    )


def classify(question: str, config: OptimizationConfig = BASELINE) -> dict:
    """사용자 질문을 분류하여 category, keyword 반환"""
    llm = _get_classifier(config)
    prompt = CLASSIFIER_PROMPT.format(question=question)
    result = llm.invoke(prompt)

    try:
        parsed = json.loads(result.content.strip())
    except json.JSONDecodeError:
        parsed = {"category": "brand_name", "keyword": question}

    return {
        "question": question,
        "category": parsed.get("category", "brand_name"),
        "keyword": parsed.get("keyword", question),
    }


def search_openfda(category: str, keyword: str, config: OptimizationConfig = BASELINE) -> tuple[str, list[dict]]:
    """분류 결과에 따라 OpenFDA API 호출 및 최적화 적용"""
    if category == "invalid":
        return "(invalid query)", []
    
    # 두 단계 검색 설정
    if config.two_stage_retrieval:
        # 1단계: 광범위 검색을 위해 더 많은 결과 가져오기
        # OpenFDAClient에서 SEARCH_LIMIT을 config.stage1_limit으로 변경해야 하지만
        # 지금은 기본 검색 후 필터링하는 방식 사용
        pass
    
    # 기본 검색
    if category == "brand_name":
        results = search_by_brand_name(keyword)
    elif category == "generic_name":
        results = search_by_generic_name(keyword)
    elif category == "indication":
        results = search_by_indication(keyword)
    else:
        results = search_by_brand_name(keyword)
    
    # 최적화 적용 (중복 제거, 재정렬 등)
    optimized_results = apply_optimizations(results, config, keyword)
    
    # 컨텍스트 포맷팅
    context = format_label_results(optimized_results)
    
    return context, optimized_results


def prepare_context(question: str, config: OptimizationConfig = BASELINE) -> dict:
    """
    분류 + API 호출 + 컨텍스트 구성
    config에 따라 최적화 적용
    """
    # 1단계: 분류
    classification = classify(question, config)

    # 2단계: API 호출 및 최적화
    context, raw_results = search_openfda(
        classification["category"],
        classification["keyword"],
        config
    )

    return {
        "question": question,
        "category": classification["category"],
        "keyword": classification["keyword"],
        "context": context,
        "raw_results": raw_results,
        "dur_context": "(OpenFDA 데이터에서는 병용금지(DUR) 정보를 제공하지 않습니다.)",
        "config_name": config.name,  # 설정 정보 포함
    }


def stream_answer(context_data: dict, config: OptimizationConfig = BASELINE) -> Generator[str, None, None]:
    """컨텍스트 데이터로 스트리밍 답변 생성"""
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
    """컨텍스트 데이터로 전체 답변 생성 (비스트리밍)"""
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
