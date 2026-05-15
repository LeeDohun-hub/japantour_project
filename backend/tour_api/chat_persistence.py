from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from tour_api.models import ChatMessage, ChatSession, RetrievalLog, TravelerProfile


PROFILE_FIELDS = {
    "budget_level",
    "personality_type",
    "home_country",
    "travel_style",
    "hotel_booked",
    "arrival_airport",
    "arrival_time",
    "return_time",
    "interests",
    "extra_preferences",
}


def get_or_create_chat_session(
    *,
    session_id: str | None,
    reply_language: str,
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[ChatSession, bool]:
    session = None
    created = False

    if session_id:
        try:
            session = ChatSession.objects.filter(id=uuid.UUID(str(session_id))).first()
        except (TypeError, ValueError):
            session = None

    if session is None:
        session = ChatSession.objects.create(
            reply_language=reply_language,
            current_latitude=latitude,
            current_longitude=longitude,
            last_message_at=timezone.now(),
        )
        return session, True

    session.reply_language = reply_language
    if latitude is not None:
        session.current_latitude = latitude
    if longitude is not None:
        session.current_longitude = longitude
    session.last_message_at = timezone.now()
    session.save(update_fields=[
        "reply_language",
        "current_latitude",
        "current_longitude",
        "last_message_at",
        "updated_at",
    ])
    return session, created


def upsert_traveler_profile(session: ChatSession, payload: dict[str, Any] | None) -> TravelerProfile | None:
    if not isinstance(payload, dict):
        return None

    defaults: dict[str, Any] = {}
    for key in PROFILE_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if key in {"arrival_time", "return_time"} and isinstance(value, str) and value.strip():
            value = parse_datetime(value.strip()) or value
        defaults[key] = value

    if not defaults:
        return None

    profile, _ = TravelerProfile.objects.update_or_create(session=session, defaults=defaults)
    return profile


def save_chat_turn(
    *,
    session: ChatSession,
    user_message: str,
    assistant_reply: str,
    translated_ko: str | None,
    route_result: Any | None,
) -> tuple[ChatMessage, ChatMessage]:
    session.last_message_at = timezone.now()
    session.save(update_fields=["last_message_at", "updated_at"])

    user_record = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content=user_message,
    )

    assistant_record = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content=assistant_reply,
        translated_ko=translated_ko or "",
        category=getattr(route_result, "category", "") or "",
        keyword=getattr(route_result, "keyword", "") or "",
        sources_used=list(getattr(route_result, "sources_used", []) or []),
        rag_count=int(getattr(route_result, "rag_count", 0) or 0),
        places_count=int(getattr(route_result, "places_count", 0) or 0),
        is_fallback=bool(getattr(route_result, "is_fallback", False)),
    )

    if route_result is not None:
        RetrievalLog.objects.create(
            session=session,
            message=assistant_record,
            query=user_message,
            backend=getattr(route_result, "retrieval_backend", "") or "none",
            category_filter=getattr(route_result, "category", "") or "",
            area_filter=getattr(route_result, "rag_area", "") or "",
            top_k=max(int(getattr(route_result, "rag_count", 0) or 0), 5),
            result_chunk_ids=list(getattr(route_result, "rag_result_ids", []) or []),
            result_scores=[],
        )

    return user_record, assistant_record
