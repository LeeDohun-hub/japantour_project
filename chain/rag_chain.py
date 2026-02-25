"""분류 → OpenFDA API 호출 → 답변 생성 RAG 체인"""
import json
from typing import Generator
from langchain_openai import ChatOpenAI

from src.chain.prompts import CLASSIFIER_PROMPT, ANSWER_PROMPT as GENERATOR_PROMPT
from src.api.openfda_client import (
    search_by_brand_name,
    search_by_generic_name,
    search_by_indication,
)
from src.api.formatter import format_label_results
from src.config import CLASSIFIER_MODEL, LLM_MODEL, LLM_TEMPERATURE, OPENAI_API_KEY


def _get_classifier() -> ChatOpenAI:
    """분류용 LLM"""
    return ChatOpenAI(
        model=CLASSIFIER_MODEL,
        temperature=0.0,
        openai_api_key=OPENAI_API_KEY,
    )


def _get_generator(streaming: bool = False) -> ChatOpenAI:
    """답변 생성용 LLM"""
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        openai_api_key=OPENAI_API_KEY,
        streaming=streaming,
    )


def classify(question: str) -> dict:
    """사용자 질문을 분류하여 category, keyword 반환"""
    llm = _get_classifier()
    prompt = CLASSIFIER_PROMPT.format(question=question)
    result = llm.invoke(prompt)

    try:
        parsed = json.loads(result.content.strip())
    except json.JSONDecodeError:
        # 파싱 실패 시 기본값: 브랜드명 검색
        parsed = {"category": "brand_name", "keyword": question}

    return {
        "question": question,
        "category": parsed.get("category", "brand_name"),
        "keyword": parsed.get("keyword", question),
    }


def search_openfda(category: str, keyword: str) -> tuple[str, list[dict]]:
    """분류 결과에 따라 OpenFDA API 호출"""
    # invalid 카테고리 처리
    if category == "invalid":
        return "(invalid query)", []
    
    if category == "brand_name":
        results = search_by_brand_name(keyword)
    elif category == "generic_name":
        results = search_by_generic_name(keyword)
    elif category == "indication":
        results = search_by_indication(keyword)
    else:
        # 기본: 브랜드명 검색
        results = search_by_brand_name(keyword)

    context = format_label_results(results)
    return context, results


def prepare_context(question: str) -> dict:
    """
    분류 + API 호출 + 컨텍스트 구성
    Streamlit에서 스트리밍 전에 호출
    """
    # 1단계: 분류
    classification = classify(question)

    # 2단계: API 호출
    context, raw_results = search_openfda(
        classification["category"],
        classification["keyword"]
    )

    return {
        "question": question,
        "category": classification["category"],
        "keyword": classification["keyword"],
        "context": context,
        "raw_results": raw_results,
        "dur_context": "(OpenFDA 데이터에서는 병용금지(DUR) 정보를 제공하지 않습니다.)",
    }


def stream_answer(context_data: dict) -> Generator[str, None, None]:
    """
    컨텍스트 데이터로 스트리밍 답변 생성
    Generator로 청크 단위 반환
    """
    llm = _get_generator(streaming=True)

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


def generate_answer(context_data: dict) -> str:
    """
    컨텍스트 데이터로 전체 답변 생성 (비스트리밍)
    """
    llm = _get_generator(streaming=False)

    prompt_value = GENERATOR_PROMPT.format_messages(
        question=context_data["question"],
        category=context_data["category"],
        keyword=context_data["keyword"],
        context=context_data["context"],
        dur_context=context_data["dur_context"],
    )

    result = llm.invoke(prompt_value)
    return result.content
