"""질문 분류 → (향후) 지식 검색 → 답변 생성 체인. 현재는 관광 지식베이스 연동 전 단계입니다."""
import json
from typing import Generator
from langchain_openai import ChatOpenAI

from src.chain.prompts import CLASSIFIER_PROMPT, ANSWER_PROMPT as GENERATOR_PROMPT
from src.config import CLASSIFIER_MODEL, LLM_MODEL, LLM_TEMPERATURE, OPENAI_API_KEY

_NO_KB_CONTEXT = (
    "(지식 베이스에서 검색된 문서가 없습니다. "
    "一般的な韓国旅行の知識に基づいて回答し、最新の料金・営業時間・規則は公式サイトや現地で確認するよう案内してください。)"
)


def _get_classifier() -> ChatOpenAI:
    return ChatOpenAI(
        model=CLASSIFIER_MODEL,
        temperature=0.0,
        openai_api_key=OPENAI_API_KEY,
    )


def _get_generator(streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        openai_api_key=OPENAI_API_KEY,
        streaming=streaming,
    )


def classify(question: str) -> dict:
    """질문 분류 → category, keyword"""
    llm = _get_classifier()
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


def retrieve_context(category: str, keyword: str) -> tuple[str, list[dict]]:
    """향후 tour_knowledge RAG 연결 지점. 현재는 검색 결과 없음."""
    if category == "invalid":
        return "(invalid query)", []
    return _NO_KB_CONTEXT, []


def prepare_context(question: str) -> dict:
    classification = classify(question)
    context, raw_results = retrieve_context(
        classification["category"],
        classification["keyword"],
    )

    return {
        "question": question,
        "category": classification["category"],
        "keyword": classification["keyword"],
        "context": context,
        "raw_results": raw_results,
        "dur_context": "（観光ナレッジベース未接続のため、補足情報なし）",
    }


def stream_answer(context_data: dict) -> Generator[str, None, None]:
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
