"""OpenAI 채팅·번역 서비스 (Django 뷰에서 사용).

채팅 경로:
  run_chat() → src/chain/router.route_and_answer() → 분류 + RAG + Places API + LLM
번역 경로:
  translate_to_korean() → 단순 번역 LLM 호출
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY".upper())
_client: OpenAI | None = None


@dataclass
class ChatRunResult:
    reply: str
    translated_ko: str | None
    route_result: Any | None = None


def get_client() -> OpenAI | None:
    global _client
    if not OPENAI_API_KEY:
        return None
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def translate_to_korean(text: str) -> str:
    client = get_client()
    if client is None:
        return "번역 기능을 사용하려면 OPENAI_API_KEY가 필요합니다."
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional translator. "
                    "Translate the user's message into natural Korean. "
                    "답변은 반드시 한국어로만 작성하고, 다른 설명은 하지 마세요."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )
    return completion.choices[0].message.content or ""


def run_chat(
    *,
    message: str,
    reply_language: str,
    history: list[dict[str, Any]],
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: int = 1000,
) -> ChatRunResult:
    """분류 → RAG → Places API → LLM 라우팅 파이프라인으로 응답 생성.

    Returns:
        reply, 번역, 라우팅 메타데이터
    """
    client = get_client()
    if client is None:
        return ChatRunResult(
            reply=(
                "OpenAI APIキーが設定されていないため、回答を生成できません。"
                "`.env` の `OPENAI_API_KEY` を設定してください。"
            ),
            translated_ko=None,
        )

    route_result = None
    try:
        from src.chain.router import route_and_answer
        route_result = route_and_answer(
            user_message=message,
            reply_language=reply_language,
            history=history,
            openai_client=client,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
        )
        reply = route_result.reply
    except Exception:
        # 라우터 오류 시 안전 폴백 (최소한의 LLM 응답)
        reply = _fallback_chat(message, reply_language, history, client)

    translated_ko: str | None = None
    if reply_language == "日本語":
        translated_ko = translate_to_korean(reply)

    return ChatRunResult(reply=reply, translated_ko=translated_ko, route_result=route_result)


def _fallback_chat(
    message: str,
    reply_language: str,
    history: list[dict[str, Any]],
    client: OpenAI,
) -> str:
    """라우터 오류 시 기본 LLM 폴백 (환각 방지 규칙 포함)."""
    lang_rule = (
        "回答は必ず日本語で行ってください。"
        if reply_language == "日本語"
        else "반드시 한국어로만 답변해 주세요."
    )
    system = (
        f"あなたは韓国旅行の案内ガイドです。{lang_rule}\n"
        "具体的な店舗名・施設名・住所は、確認できるデータがない場合は生成しないでください。"
        "エリア名の紹介や一般的なアドバイスに留め、具体的な場所はNaver MapやGoogle Mapsで検索するよう案内してください。"
        "不確かな情報は「公式サイトや現地でご確認ください」と明示してください。"
    )
    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in history[-6:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.3,
    )
    return completion.choices[0].message.content or ""
