"""OpenAI 채팅·번역 서비스 (Django 뷰에서 사용).

채팅 경로:
  run_chat() → src/chain/router.route_and_answer() → 분류 + RAG + Places API + LLM
번역 경로:
  응답 언어가「한국어」이고 본문에 가타카나·히라가나가 섞인 경우에만
  translate_to_korean() 호출 → 보조 한국어 블록(translated_ko)
  「日本語」모드에서는 번역 블록을 만들지 않음.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY".upper())
_client: OpenAI | None = None


@dataclass
class ChatRunResult:
    reply: str
    translated_ko: str | None
    route_result: Any | None = None
    places: list = field(default_factory=list)
    visitkorea_stays: list = field(default_factory=list)
    visitkorea_festivals: list = field(default_factory=list)
    visitkorea_attractions: list = field(default_factory=list)
    sports_events: list = field(default_factory=list)
    flights: list = field(default_factory=list)
    gyeonggi_events: list = field(default_factory=list)
    ticket_platform_events: list = field(default_factory=list)
    airport: dict | None = None
    flight_subtype: str = ""


def get_client() -> OpenAI | None:
    global _client
    if not OPENAI_API_KEY:
        return None
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _reply_has_japanese_kana(text: str) -> bool:
    """답변에 히라가나·가타카나가 있으면 True (한국어 모드에서 일본어 혼용 시 번역용)."""
    for ch in text:
        if "\u3040" <= ch <= "\u309f":  # Hiragana
            return True
        if "\u30a0" <= ch <= "\u30ff":  # Katakana
            return True
    return False


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
    traveler_profile: dict | None = None,
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
            traveler_profile=traveler_profile,
        )
        reply = route_result.reply
    except Exception as exc:
        logger.exception("route_and_answer failed: %s", exc)
        reply = _fallback_chat(message, reply_language, history, client)

    translated_ko: str | None = None
    if reply_language == "한국어" and _reply_has_japanese_kana(reply):
        translated_ko = translate_to_korean(reply)

    places: list = []
    visitkorea_stays: list = []
    visitkorea_festivals: list = []
    visitkorea_attractions: list = []
    sports_events: list = []
    flights: list = []
    gyeonggi_events: list = []
    ticket_platform_events: list = []
    airport: dict | None = None
    flight_subtype: str = ""

    if route_result is not None:
        card_categories = frozenset({"food", "lodging", "shopping", "leisure"})
        if route_result.places:
            places = [dataclasses.asdict(p) for p in route_result.places]
        if route_result.visitkorea_stays:
            visitkorea_stays = [
                i.to_dict() if hasattr(i, "to_dict") else dataclasses.asdict(i)
                for i in route_result.visitkorea_stays
            ]
        if route_result.visitkorea_festivals:
            visitkorea_festivals = [
                i.to_dict() if hasattr(i, "to_dict") else dataclasses.asdict(i)
                for i in route_result.visitkorea_festivals
            ]
        if route_result.visitkorea_attractions:
            visitkorea_attractions = [
                i.to_dict() if hasattr(i, "to_dict") else dataclasses.asdict(i)
                for i in route_result.visitkorea_attractions
            ]
        if route_result.sports_events:
            sports_events = [
                m.to_dict() if hasattr(m, "to_dict") else dataclasses.asdict(m)
                for m in route_result.sports_events
            ]
        if getattr(route_result, "gyeonggi_events", None):
            gyeonggi_events = [
                e.to_dict() if hasattr(e, "to_dict") else dataclasses.asdict(e)
                for e in route_result.gyeonggi_events
            ]
        if getattr(route_result, "ticket_platform_events", None):
            ticket_platform_events = [
                e.to_dict() if hasattr(e, "to_dict") else dataclasses.asdict(e)
                for e in route_result.ticket_platform_events
            ]
        if route_result.flights:
            flights = [dataclasses.asdict(f) for f in route_result.flights]
            reply = ""
        if route_result.airport is not None:
            airport = dataclasses.asdict(route_result.airport)
            reply = ""
        flight_subtype = route_result.flight_subtype

    return ChatRunResult(
        reply=reply,
        translated_ko=translated_ko,
        route_result=route_result,
        places=places,
        visitkorea_stays=visitkorea_stays,
        visitkorea_festivals=visitkorea_festivals,
        visitkorea_attractions=visitkorea_attractions,
        sports_events=sports_events,
        flights=flights,
        gyeonggi_events=gyeonggi_events,
        ticket_platform_events=ticket_platform_events,
        airport=airport,
        flight_subtype=flight_subtype,
    )


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
        f"あなたはこの韓国旅行プランナー内のAIチャットガイドです。{lang_rule}\n"
        "このサービスは韓国旅行プランナーで、ホーム画面では航空・宿泊・交通・目的地・活動・予算をもとに旅行プランを生成し、"
        "KOPIS公演情報、KBO等のスポーツ日程、空港交通、Juso住所検索、Visit Korea/TourAPI、Naver系スポット情報、保存済みプラン機能を扱います。"
        "ユーザーが個別質問をした場合は、その質問に合う機能・データソースを前提に答えてください。"
        "このアプリ自体の使い方、対応範囲、保存・共有・PDF・地図カードについても説明できます。"
        "関係ない質問に仁川空港交通の定型文を返さないでください。"
        "具体的な店舗名・施設名・住所は、確認できるデータがない場合は生成しないでください。"
        "エリア名の紹介や一般的なアドバイスに留めてください。"
        "「予約サイトで確認」「Naverで検索」など、ユーザーに確認を押し付ける締めの文は使わないでください。"
    )
    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in history[-6:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": _trim_fallback_history_content(content)})
    messages.append({"role": "user", "content": message})

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.3,
    )
    return completion.choices[0].message.content or ""


from typing import Generator


_FALLBACK_HISTORY_CONTENT_LIMIT = 2000


def _trim_fallback_history_content(content: str) -> str:
    text = str(content or "").strip()
    if len(text) <= _FALLBACK_HISTORY_CONTENT_LIMIT:
        return text
    return text[:_FALLBACK_HISTORY_CONTENT_LIMIT].rstrip() + "\n...[history truncated]"


def run_chat_stream(
    *,
    message: str,
    reply_language: str,
    history: list[dict[str, Any]],
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: int = 1000,
    traveler_profile: dict | None = None,
) -> Generator[tuple[str, Any], None, None]:
    """SSE 스트리밍용 generator. (type, data) 튜플을 순차 yield.
    types: "meta" → dict, "token" → str 청크, "done" → dict, "error" → str
    """
    client = get_client()
    if client is None:
        err = (
            "OpenAI APIキーが設定されていません。"
            if reply_language == "日本語"
            else "OpenAI API 키가 설정되지 않았습니다."
        )
        yield ("error", err)
        return

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
            traveler_profile=traveler_profile,
            _stream=True,
        )
    except Exception as exc:
        logger.exception("route_and_answer (stream) failed: %s", exc)
        yield ("error", str(exc))
        return

    # 메타 데이터 (카드·분류 결과) 먼저 전송
    meta: dict[str, Any] = {
        "category": route_result.category,
        "keyword": route_result.keyword,
        "sources_used": route_result.sources_used,
        "places_count": route_result.places_count,
    }
    if route_result.places:
        meta["places"] = [dataclasses.asdict(p) for p in route_result.places]
    if route_result.visitkorea_stays:
        meta["visitkorea_stays"] = [
            i.to_dict() if hasattr(i, "to_dict") else dataclasses.asdict(i)
            for i in route_result.visitkorea_stays
        ]
    if route_result.visitkorea_festivals:
        meta["visitkorea_festivals"] = [
            i.to_dict() if hasattr(i, "to_dict") else dataclasses.asdict(i)
            for i in route_result.visitkorea_festivals
        ]
    if route_result.visitkorea_attractions:
        meta["visitkorea_attractions"] = [
            i.to_dict() if hasattr(i, "to_dict") else dataclasses.asdict(i)
            for i in route_result.visitkorea_attractions
        ]
    if route_result.sports_events:
        meta["sports_events"] = [
            m.to_dict() if hasattr(m, "to_dict") else dataclasses.asdict(m)
            for m in route_result.sports_events
        ]
    if getattr(route_result, "gyeonggi_events", None):
        meta["gyeonggi_events"] = [
            e.to_dict() if hasattr(e, "to_dict") else dataclasses.asdict(e)
            for e in route_result.gyeonggi_events
        ]
    if getattr(route_result, "ticket_platform_events", None):
        meta["ticket_platform_events"] = [
            e.to_dict() if hasattr(e, "to_dict") else dataclasses.asdict(e)
            for e in route_result.ticket_platform_events
        ]
    if route_result.flights:
        meta["flights"] = [dataclasses.asdict(f) for f in route_result.flights]
        meta["flight_subtype"] = route_result.flight_subtype
    if route_result.airport is not None:
        meta["airport"] = dataclasses.asdict(route_result.airport)
        meta["flight_subtype"] = route_result.flight_subtype
    if route_result.places_error:
        meta["places_error"] = route_result.places_error

    yield ("meta", meta)

    # LLM 토큰 스트리밍
    full_reply = ""
    if route_result.token_stream:
        for chunk in route_result.token_stream:
            if chunk:
                full_reply += chunk
                yield ("token", chunk)

    # 번역 (한국어 모드 + 일본어 혼용 시)
    translated_ko: str | None = None
    if reply_language == "한국어" and _reply_has_japanese_kana(full_reply):
        try:
            translated_ko = translate_to_korean(full_reply)
        except Exception:
            pass

    yield ("done", {"translated_ko": translated_ko, "reply": full_reply})
