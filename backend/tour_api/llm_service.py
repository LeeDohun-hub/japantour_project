"""OpenAI 채팅·번역 (Django 뷰에서 사용)."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY".upper())
_client: OpenAI | None = None


def get_client() -> OpenAI | None:
    global _client
    if not OPENAI_API_KEY:
        return None
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def build_system_prompt(reply_language: str) -> str:
    if reply_language == "한국어":
        return (
            "당신은 한국을 여행하는 일본인 관광객을 돕는 전문 한국어 여행 가이드입니다. "
            "질문은 한국어 또는 일본어로 들어올 수 있지만, 사용자가 선택한 언어인 **한국어**로만 대답해야 합니다. "
            "말투는 친절하고 공손하게 유지하고, 처음 한국을 방문하는 일본인도 이해하기 쉽도록 설명하세요. "
            "관광지, 맛집, 쇼핑, 교통수단, 계절별 옷차림, 문화/예절(마너) 등도 함께 제안해 주세요. "
            "가능하다면 일본인이 읽기 쉬우도록 장소 이름 뒤에 일본어(가타카나)를 병기해도 좋습니다."
        )
    return (
        "あなたは韓国を旅行する日本人観光客向けのプロの日本語ツアーガイドです。"
        "質問は日本語または韓国語で届きますが、回答は必ず**日本語**で行ってください。"
        "丁寧で親切な口調を使い、初めて韓国に来る人にも分かりやすく説明してください。"
        "観光地・グルメ・ショッピング・交通手段・季節ごとの服装・マナーなども提案してください。"
        "具体的な場所名やエリア名（例：明洞、弘大、江南、釜山、済州島 など）を挙げて説明するときは、"
        "日本人が読んで分かりやすいように、できればカタカナ（＋必要ならハングル）も併記してください。"
    )


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
) -> tuple[str, str | None]:
    """Returns (reply, translated_ko or None)."""
    client = get_client()
    if client is None:
        return (
            "OpenAI APIキーが設定されていないため、回答を生成できません。`.env` の `OPENAI_API_KEY` を設定してください。",
            None,
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": build_system_prompt(reply_language)}]
    for turn in history:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.7,
    )
    reply = completion.choices[0].message.content or ""

    translated_ko: str | None = None
    if reply_language == "日本語":
        translated_ko = translate_to_korean(reply)

    return reply, translated_ko
