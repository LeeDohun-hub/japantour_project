"""인터파크 모바일 티켓(NOL 티켓 계열) 공연·전시 메타데이터.

티켓링크(www.ticketlink.co.kr) 공연 메인은 순수 SPA(#app만 제공)로, 서버 HTML에
목록 JSON이 없어 안정적으로 크롤링하기 어렵다. 동급 예매 데이터는 인터파크
모바일 장르 페이지의 Next.js ``__NEXT_DATA__``(SSR)에서 구조화되어 노출된다.

- 소스: ``https://mticket.interpark.com/genre/{MusicalMain|ConcertMain|...}``
- 각 항목: 공연명, 장르, 회차(가능 시), 장소, ``playStartDate``/``playEndDate``, 예매 URL

주의: 공식 오픈 API가 아니다. 과도한 호출·상업적 재배포는 각 사이트 정책을 따른다.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

# 장르 페이지 path → 한국어 라벨 (프롬프트·로그용)
_INTERPARK_GENRE_PAGES: tuple[tuple[str, str], ...] = (
    ("MusicalMain", "뮤지컬"),
    ("DramaMain", "연극"),
    ("ConcertMain", "콘서트"),
    ("ClassicMain", "클래식/무용"),
    ("ExhibitionMain", "전시"),
    ("FamilyMain", "아동/가족"),
)

# 여행지·숙소 매칭 + 대형 페스 키워드 (제목·장소에 포함 시 우선 표시)
_MAJOR_EVENT_SUBSTRINGS: tuple[str, ...] = (
    "워터밤",
    "waterbomb",
    "water bomb",
    "s2o",
    "월드 dj",
    "world dj",
    "울트라",
    "ultra korea",
    "서울재즈",
    "seoul jazz",
    "페스티벌",
    "festival",
    "rock fest",
)

_REGION_HINTS_DEFAULT: tuple[str, ...] = (
    "서울",
    "경기",
    "고양",
    "일산",
    "킨텍스",
    "kintex",
    "인천",
    "김포",
    "수원",
    "성남",
    "부천",
    "의정부",
)


@dataclass(frozen=True)
class TicketPlatformEvent:
    """인터파크 모바일에서 추출한 공연·전시 1건."""

    title: str
    genre_page: str
    genre_label_ko: str
    venue: str
    place_region: str  # goodsRegionStr 등
    play_start: date | None
    play_end: date | None
    goods_code: str
    ticket_url: str
    source: str = "interpark_mticket"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "genre_page": self.genre_page,
            "genre_label_ko": self.genre_label_ko,
            "venue": self.venue,
            "place_region": self.place_region,
            "play_start": self.play_start.isoformat() if self.play_start else None,
            "play_end": self.play_end.isoformat() if self.play_end else None,
            "goods_code": self.goods_code,
            "ticket_url": self.ticket_url,
            "source": self.source,
        }


def _parse_yyyymmdd(raw: str | None) -> date | None:
    if not raw or len(str(raw).strip()) < 8:
        return None
    s = str(raw).strip().replace("-", "")[:8]
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _travel_window(profile: dict | None) -> tuple[date | None, date | None]:
    if not profile:
        return None, None
    try:
        from src.api.sports_schedule_client import travel_dates_from_profile

        return travel_dates_from_profile(profile)
    except Exception:
        return None, None


def _profile_location_blob(profile: dict | None) -> str:
    if not profile:
        return ""
    parts: list[str] = []
    ac = profile.get("accommodation") or {}
    for k in ("address", "name", "detail", "region"):
        v = ac.get(k)
        if v:
            parts.append(str(v))
    rc = profile.get("regionCities")
    if rc:
        parts.append(str(rc))
    for r in profile.get("regions") or []:
        parts.append(str(r))
    parts.append(profile.get("keyword") or "")
    return " ".join(parts).lower()


def _overlap(a0: date, a1: date, b0: date, b1: date) -> bool:
    return not (a1 < b0 or b1 < a0)


def _banner_goods_rows(banner: Any) -> list[dict]:
    """메인 장르 페이지 배너 블록 — hotItem 등에 대량의 goods 메타가 있다."""
    if not isinstance(banner, dict):
        return []
    rows: list[dict] = []
    for key in ("hotItem", "bigBanner", "miniBanner"):
        block = banner.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, dict) and item.get("goodsCode"):
                    rows.append(item)
    return rows


def _event_from_goods_flat(
    gi: dict,
    *,
    genre_path: str,
    genre_label: str,
) -> TicketPlatformEvent | None:
    code = str(gi.get("goodsCode") or "").strip()
    name = (gi.get("goodsName") or gi.get("title") or gi.get("playName") or "").strip()
    if not code or not name:
        return None
    venue = (gi.get("placeName") or "").strip()
    ps = _parse_yyyymmdd(gi.get("playStartDate"))
    pe = _parse_yyyymmdd(gi.get("playEndDate")) or ps
    link = (gi.get("link") or "").strip()
    if link and link.startswith("http"):
        ticket_url = link
    else:
        ticket_url = f"https://tickets.interpark.com/goods/{code}"
    return TicketPlatformEvent(
        title=name,
        genre_page=genre_path,
        genre_label_ko=genre_label,
        venue=venue,
        place_region="",
        play_start=ps,
        play_end=pe,
        goods_code=code,
        ticket_url=ticket_url,
    )


def _fetch_interpark_genre(
    genre_path: str,
    genre_label: str,
    *,
    timeout: int = 12,
) -> list[TicketPlatformEvent]:
    url = f"https://mticket.interpark.com/genre/{genre_path}"
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
        )
        r.raise_for_status()
    except Exception as exc:
        logger.warning("interpark genre fetch failed [%s]: %s", genre_path, exc)
        return []

    m = _NEXT_DATA_RE.search(r.text)
    if not m:
        logger.warning("interpark no __NEXT_DATA__ [%s]", genre_path)
        return []

    try:
        payload: dict[str, Any] = json.loads(m.group(1))
    except Exception as exc:
        logger.warning("interpark JSON parse [%s]: %s", genre_path, exc)
        return []

    pp = (payload.get("props") or {}).get("pageProps") or {}
    out: list[TicketPlatformEvent] = []

    for row in pp.get("interparkPlay") or []:
        if not isinstance(row, dict):
            continue
        gi = row.get("goodsInfo") or {}
        if not isinstance(gi, dict):
            continue
        ev = _event_from_goods_flat(gi, genre_path=genre_path, genre_label=genre_label)
        if ev:
            out.append(ev)

    banner = pp.get("banner") or {}
    for gi in _banner_goods_rows(banner):
        ev = _event_from_goods_flat(gi, genre_path=genre_path, genre_label=genre_label)
        if ev:
            out.append(ev)

    return out


def _is_major_or_region_relevant(ev: TicketPlatformEvent, blob: str) -> tuple[int, str]:
    """정렬용 점수: 높을수록 여행자에게 유용."""
    hay = f"{ev.title} {ev.venue} {ev.place_region}".lower()
    score = 0
    reason = ""
    for s in _MAJOR_EVENT_SUBSTRINGS:
        if s.lower() in hay:
            score += 50
            reason = "major_event_keyword"
            break
    for hint in _REGION_HINTS_DEFAULT:
        if hint in blob and hint in hay:
            score += 30
            reason = reason or "region_match"
    if blob:
        for token in blob.replace(",", " ").split():
            if len(token) >= 2 and token in hay:
                score += 15
                reason = reason or "profile_token_match"
    return score, reason


def fetch_ticket_platform_events(
    traveler_profile: dict | None,
    *,
    max_total: int = 24,
    timeout_per_genre: int = 12,
) -> list[TicketPlatformEvent]:
    """여행 기간과 겹치는 공연·전시를 장르별로 수집 후 점수순으로 자른다."""
    start_d, end_d = _travel_window(traveler_profile)
    if not start_d:
        start_d = date.today()
    if not end_d:
        end_d = start_d + timedelta(days=14)
    if end_d < start_d:
        end_d = start_d

    blob = _profile_location_blob(traveler_profile)

    merged: list[TicketPlatformEvent] = []
    with ThreadPoolExecutor(max_workers=min(6, len(_INTERPARK_GENRE_PAGES))) as pool:
        futs = {
            pool.submit(_fetch_interpark_genre, path, label, timeout=timeout_per_genre): (
                path,
                label,
            )
            for path, label in _INTERPARK_GENRE_PAGES
        }
        for fut in as_completed(futs):
            try:
                merged.extend(fut.result())
            except Exception as exc:
                logger.warning("interpark worker: %s", exc)

    # 기간 필터: 공연 종료일이 여행 시작 전이거나, 공연 시작이 여행 종료 후면 제외
    in_window: list[TicketPlatformEvent] = []
    for ev in merged:
        if ev.play_start is None:
            continue
        pe = ev.play_end or ev.play_start
        if _overlap(start_d, end_d, ev.play_start, pe):
            in_window.append(ev)

    # 중복 goods_code
    seen: set[str] = set()
    deduped: list[TicketPlatformEvent] = []
    for ev in in_window:
        if ev.goods_code in seen:
            continue
        seen.add(ev.goods_code)
        deduped.append(ev)

    scored: list[tuple[int, TicketPlatformEvent]] = []
    for ev in deduped:
        sc, _ = _is_major_or_region_relevant(ev, blob)
        # 기간 내 전부 후보로 두되, 점수 0도 소량 포함(지역 무관 대형 공연 놓침 방지)
        scored.append((sc, ev))

    scored.sort(key=lambda x: (-x[0], x[1].play_start or date.min))
    return [ev for _, ev in scored[:max_total]]


def fmt_ticket_platform_events(events: list[TicketPlatformEvent], lang: str = "ja") -> str:
    """LLM 컨텍스트용 텍스트."""
    if not events:
        empty = (
            "(인터파크 모바일 NOL — 해당 여행 기간·조건에 맞는 공연 메타 없음)"
            if lang == "ko"
            else "(Interpark mobile NOL — 該当旅行期間に一致する公演メタなし)"
        )
        return empty
    intro = (
        "인터파크 모바일(mticket) 장르 페이지 SSR 데이터 — 예매는 각 URL에서 확인."
        if lang == "ko"
        else "Interpark モバイル(mticket) ジャンルページのSSRデータ — 購入は各URLで確認。"
    )
    lines = [intro, ""]
    for i, ev in enumerate(events, 1):
        dr = ""
        if ev.play_start:
            dr = ev.play_start.isoformat()
            if ev.play_end and ev.play_end != ev.play_start:
                dr += " ~ " + ev.play_end.isoformat()
        lines.append(
            f"[{i}] [{ev.genre_label_ko}] {ev.title}\n"
            f"    장소: {ev.venue or '(미상)'}\n"
            f"    기간: {dr or '(일정 SSR에 없음)'}\n"
            f"    URL: {ev.ticket_url}"
        )
    return "\n".join(lines)
