"""Fast direct lookups for narrow chat questions."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from collections.abc import Iterator

from src.api.sports_schedule_client import SportsScheduleClient
from src.api.ticket_platform_events_client import fetch_ticket_platform_events
from src.api.web_search_client import WebSearchClient
from src.chain.concert_lookup_helpers import (
    CHAT_CONCERT_CONCERT_ONLY_RE,
    CHAT_CONCERT_KPOP_RE,
    CHAT_CONCERT_NATIONWIDE_REGION_KEYS,
    CHAT_CONCERT_RE,
    chat_concert_region_area_keys,
    chat_lookup_date_window,
    concert_artist_query,
    concert_lookup_reply,
)
from src.chain.router_models import RouteResult

logger = logging.getLogger(__name__)

_CHAT_KBO_RE = re.compile(
    r"\bKBO\b|프로야구|야구\s*(?:경기|일정)|野球|プロ野球",
    re.IGNORECASE,
)


def stream_text(text: str) -> Iterator[str]:
    return (text[i:i + 160] for i in range(0, len(text or ""), 160))


def chat_direct_sports_lookup(
    message: str,
    reply_language: str,
    *,
    stream: bool = False,
) -> RouteResult | None:
    if not _CHAT_KBO_RE.search(message or ""):
        return None
    start_d, end_d = chat_lookup_date_window(message)
    try:
        matches = SportsScheduleClient().search(
            leagues=["kbo"],
            start=start_d,
            end=end_d,
            max_per_league=30,
        )
    except Exception as exc:
        logger.warning("direct KBO chat lookup failed: %s", exc)
        matches = []

    if reply_language == "日本語":
        reply = (
            f"{start_d.isoformat()}のKBO公式日程を確認しました。"
            "下のカードで試合時間・球場・公式リンクを確認できます。"
            if matches else f"{start_d.isoformat()}のKBO試合データは見つかりませんでした。"
        )
    else:
        reply = (
            f"{start_d.isoformat()} KBO 공식 일정 기준으로 확인했습니다. "
            "아래 카드에서 경기 시간, 구장, 공식 링크를 확인해 주세요."
            if matches else f"{start_d.isoformat()} KBO 경기 데이터가 없습니다."
        )
    return RouteResult(
        reply="" if stream else reply,
        category="general",
        keyword=f"KBO {start_d.isoformat()}",
        sources_used=["sports"],
        sports_events=matches,
        token_stream=stream_text(reply) if stream else None,
    )


def chat_direct_concert_lookup(
    message: str,
    reply_language: str,
    *,
    stream: bool = False,
) -> RouteResult | None:
    if not CHAT_CONCERT_RE.search(message or ""):
        return None
    artist = concert_artist_query(message)
    start_d, end_d = chat_lookup_date_window(message)
    if end_d < start_d:
        end_d = start_d + timedelta(days=180)
    region_keys = chat_concert_region_area_keys(message)
    profile = {
        "activities": ["kpop"],
        "hallyu": ["kpop"],
        "regionAreaKeys": region_keys or list(CHAT_CONCERT_NATIONWIDE_REGION_KEYS),
        "flight": {
            "depart": start_d.isoformat(),
            "returnDate": end_d.isoformat(),
        },
    }
    try:
        events = fetch_ticket_platform_events(profile, max_total=80)
    except Exception as exc:
        logger.warning("direct KOPIS chat lookup failed: %s", exc)
        events = []
    raw_events_count = len(events)

    if CHAT_CONCERT_CONCERT_ONLY_RE.search(message or ""):
        events = [ev for ev in events if getattr(ev, "genre_page", "") == "concert"]

    if artist:
        aliases = {artist.lower()}
        if "세븐틴" in artist:
            aliases.update({"seventeen", "svt", "세븐틴"})
        events = [
            ev for ev in events
            if any(a and a in f"{ev.title} {ev.venue}".lower() for a in aliases)
        ]

    web_lines: list[str] = []
    if not events and (artist or CHAT_CONCERT_KPOP_RE.search(message or "")):
        try:
            wsc = WebSearchClient()
            if wsc.is_available:
                if artist:
                    query = f"{artist} 콘서트 한국 일정 티켓 {start_d.year}"
                else:
                    area = " ".join(region_keys) if region_keys else "한국"
                    if start_d.month == end_d.month:
                        period = f"{start_d.year}년 {start_d.month}월"
                    else:
                        period = f"{start_d.isoformat()}~{end_d.isoformat()}"
                    query = f"{area} K-pop 콘서트 일정 티켓 {period}"
                for r in wsc.search(query, max_results=3):
                    if r.title and r.url:
                        web_lines.append(f"- {r.title}\n  {r.url}")
        except Exception as exc:
            logger.warning("direct concert web lookup failed: %s", exc)

    reply = concert_lookup_reply(
        reply_language=reply_language,
        message=message,
        artist=artist,
        region_keys=region_keys,
        start_d=start_d,
        end_d=end_d,
        events_count=len(events),
        raw_count=raw_events_count,
        web_lines=web_lines,
    )
    return RouteResult(
        reply="" if stream else reply,
        category="general",
        keyword=(artist or "K-pop 공연")[:80],
        sources_used=["ticket_platform"] + (["web_search"] if web_lines else []),
        ticket_platform_events=events[:12],
        token_stream=stream_text(reply) if stream else None,
    )


def chat_direct_lookup(
    message: str,
    reply_language: str,
    *,
    stream: bool = False,
) -> RouteResult | None:
    return (
        chat_direct_sports_lookup(message, reply_language, stream=stream)
        or chat_direct_concert_lookup(message, reply_language, stream=stream)
    )
