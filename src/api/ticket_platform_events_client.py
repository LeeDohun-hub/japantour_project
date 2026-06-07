"""KOPIS 공연예술통합전산망 공연 메타데이터.

KOPIS OpenAPI(``KOPIS_API_KEY``)로 여행 기간과 겹치는 공연·전시 후보를 가져온다.
기존 라우터/프론트 호환을 위해 공개 함수명은 ``ticket_platform``으로 유지한다.
"""

from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

_KOPIS_BASE = "http://www.kopis.or.kr/openApi/restful"
_KOPIS_BASE_URLS = (
    "https://www.kopis.or.kr/openApi/restful",
    "http://www.kopis.or.kr/openApi/restful",
)
_KOPIS_PUBLIC_PAGE = "https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20Id="

# KOPIS 장르코드: 연극/뮤지컬/클래식/국악/대중음악/무용/대중무용/서커스·마술/복합
_KOPIS_GENRES: tuple[tuple[str, str, str], ...] = (
    ("CCCD", "concert", "대중음악"),
    ("GGGA", "musical", "뮤지컬"),
    ("CCCA", "classic", "서양음악(클래식)"),
    ("AAAA", "play", "연극"),
    ("CCCC", "korean_music", "한국음악(국악)"),
    ("BBBC", "dance", "무용"),
    ("BBBE", "popular_dance", "대중무용"),
    ("EEEB", "magic", "서커스/마술"),
    ("EEEA", "mixed", "복합"),
)

_KOPIS_GENRE_BY_SLUG = {slug: item for item in _KOPIS_GENRES for slug in (item[1],)}
_KOPIS_KPOP_SLUGS = ("concert",)
_KOPIS_PERFORMANCE_SLUGS = ("play", "musical")

_JEJU_REGION_MARKERS: tuple[str, ...] = (
    "제주",
    "서귀포",
    "済州",
    "jeju",
    "西歸浦",
    "제주시",
    "제주도",
)

# 관광 지역(위저드 regions) ↔ 공연 장소 매칭
_REGION_VENUE_MARKERS: dict[str, tuple[str, ...]] = {
    "seoul": (
        "서울", "ソウル", "seoul", "江南", "弘大", "明洞", "蚕室", "奧林匹克",
        "三成", "景福宮", "北村", "大学路", "貞洞", "鐘路", "龍山", "永登浦",
        "国立", "세종", "coex", "ロッテ", "lotte",
    ),
    "gyeonggi": (
        "경기", "京畿", "고양", "일산", "킨텍스", "kintex", "수원", "水原",
        "성남", "城南", "용인", "龍仁", "파주", "坡州", "南極", "정극", "京畿アート",
    ),
    "incheon": (
        "인천", "仁川", "incheon", "송도", "松島", "영종", "永宗", "パラダイス",
        "paradise", "월미", "青羅",
    ),
    "jeju": _JEJU_REGION_MARKERS,
    "busan": ("부산", "부산광역시", "釜山", "busan", "海雲臺", "海雲台", "해운대"),
    "gyeongsang": ("부산", "대구", "경상", "庆尚", "大邱", "金海"),
    "gangwon": ("강원", "江原", "춘천", "春川", "강릉", "江陵", "속초", "束草"),
    "jeolla": ("전주", "全州", "광주", "光州", "全羅", "光州"),
    "chungcheong": ("대전", "大田", "忠清", "청주", "清州"),
}

_AREA_KEY_TO_EVENT_REGION: dict[str, str] = {
    "busan": "busan",
    "jeju": "jeju",
    "seoul": "seoul",
    "gyeonggi": "gyeonggi",
    "incheon": "incheon",
    "gangwon": "gangwon",
    "chungcheong": "chungcheong",
    "jeolla": "jeolla",
    "gyeongsang": "gyeongsang",
    "gyeongbuk": "gyeongsang",
    "gyeongnam": "gyeongsang",
    "daegu": "gyeongsang",
    "ulsan": "gyeongsang",
}

_CAPITAL_REGION_KEYS = frozenset({"seoul", "gyeonggi", "incheon"})

# 수도권 여행인데 타 지역 전용 공연 제외
_FAR_FROM_CAPITAL_MARKERS: tuple[str, ...] = (
    "대구",
    "大邱",
    "광주",
    "光州",
    "대전",
    "大田",
    "전주",
    "全州",
    "울산",
    "蔚山",
    "창원",
    "昌原",
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
    "대학로",
    "大学路",
    "daehakro",
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
    "제주",
    "서귀포",
    "済州",
    "jeju",
)


def _profile_jeju_only(profile: dict | None) -> bool:
    if not profile:
        return False
    return _trip_active_region_keys(profile) == {"jeju"}


def _trip_active_region_keys(profile: dict | None) -> set[str]:
    """위저드 관광 지역 + 도착 공항 기준."""
    raw_area_keys = (
        (profile or {}).get("regionAreaKeys")
        or (profile or {}).get("region_area_keys")
        or []
    )
    area_keys = {str(r).lower() for r in raw_area_keys if r}
    # regionAreaKeys is the user's explicit chip (ex. busan), while regions can be a
    # broader bucket (ex. gyeongsang). Prefer the explicit chip to avoid cross-region
    # event cards like Daegu/Changwon for a Busan trip.
    keys = {
        _AREA_KEY_TO_EVENT_REGION.get(k, k)
        for k in area_keys
    } if area_keys else {
        str(r).lower() for r in (profile or {}).get("regions") or [] if r
    }
    flight = (profile or {}).get("flight") or {}
    arr = (flight.get("to") or flight.get("arrival_airport") or "").upper()
    if arr == "CJU":
        return {"jeju"}
    if arr == "PUS":
        keys.add("busan")
    if not keys:
        if arr == "GMP":
            keys = {"seoul", "gyeonggi"}
        elif arr == "ICN":
            keys = {"seoul", "gyeonggi", "incheon"}
        else:
            keys = {"seoul", "gyeonggi"}
    return keys


def _event_matches_trip_region(
    ev: TicketPlatformEvent, profile: dict | None
) -> bool:
    """여행 목적지·도착 공항과 무관한 지역 공연은 제외."""
    if not profile:
        return True
    keys = _trip_active_region_keys(profile)
    hay = f"{ev.title} {ev.venue} {ev.place_region}".lower()

    if keys == {"jeju"}:
        return any(m.lower() in hay for m in _JEJU_REGION_MARKERS)

    capital_trip = bool(keys & _CAPITAL_REGION_KEYS) and not keys & {
        "busan",
        "gyeongsang",
        "jeju",
        "jeolla",
        "gangwon",
        "chungcheong",
    }
    if capital_trip:
        for ex in _FAR_FROM_CAPITAL_MARKERS:
            if ex.lower() in hay:
                return False
        if "부산" in hay or "釜山" in hay:
            return False

    markers: list[str] = []
    for k in keys:
        markers.extend(_REGION_VENUE_MARKERS.get(k, ()))
    if markers and any(m.lower() in hay for m in markers):
        return True

    blob = _profile_location_blob(profile)
    for s in _MAJOR_EVENT_SUBSTRINGS:
        if s.lower() in hay and blob and s.lower() in blob:
            return True

    return False


@dataclass(frozen=True)
class TicketPlatformEvent:
    """KOPIS에서 조회한 공연·전시 1건."""

    title: str
    genre_page: str
    genre_label_ko: str
    venue: str
    place_region: str  # goodsRegionStr 등
    play_start: date | None
    play_end: date | None
    goods_code: str
    ticket_url: str
    source: str = "kopis"
    poster: str = ""
    state: str = ""

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
            "poster": self.poster,
            "state": self.state,
        }


def _parse_yyyymmdd(raw: str | None) -> date | None:
    if not raw or len(str(raw).strip()) < 8:
        return None
    s = str(raw).strip().replace("-", "").replace(".", "")[:8]
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _parse_profile_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s[:10].replace(".", "-"), fmt).date()
        except ValueError:
            continue
    try:
        from src.api.sports_schedule_client import SportsScheduleClient

        return SportsScheduleClient._normalize_date(s)
    except Exception:
        return None


def _travel_window(profile: dict | None) -> tuple[date | None, date | None]:
    if not profile:
        return None, None
    try:
        from src.api.sports_schedule_client import travel_dates_from_profile

        start, end = travel_dates_from_profile(profile)
    except Exception:
        start, end = None, None
    if not start:
        for key in ("travelStart", "startDate", "departDate", "departureDate"):
            start = _parse_profile_date(profile.get(key))
            if start:
                break
        flight = profile.get("flight") or {}
        if not start:
            start = _parse_profile_date(
                flight.get("depart") or flight.get("departure")
            )
    if not end:
        for key in ("travelEnd", "endDate", "returnDate"):
            end = _parse_profile_date(profile.get(key))
            if end:
                break
        if not end:
            flight = profile.get("flight") or {}
            end = _parse_profile_date(
                flight.get("returnDate") or flight.get("return")
            )
    if start and not end and profile.get("nights"):
        try:
            end = start + timedelta(days=max(int(profile["nights"]), 1))
        except (TypeError, ValueError):
            pass
    return start, end


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


def _kopis_api_key() -> str:
    return (os.getenv("KOPIS_API_KEY") or "").strip()


def _kopis_genres_for_profile(
    profile: dict | None,
    genre_slugs: list[str] | tuple[str, ...] | None = None,
) -> tuple[tuple[str, str, str], ...]:
    """Return the KOPIS genre codes to query for the selected itinerary intent."""
    if genre_slugs:
        selected: list[tuple[str, str, str]] = []
        for slug in genre_slugs:
            item = _KOPIS_GENRE_BY_SLUG.get(str(slug))
            if item and item not in selected:
                selected.append(item)
        return tuple(selected) or _KOPIS_GENRES

    prof = profile or {}
    activities = {str(a).lower() for a in prof.get("activities") or []}
    hallyu = {str(a).lower() for a in prof.get("hallyu") or []}
    slugs: list[str] = []
    if "kpop" in activities or "hallyu" in activities or "kpop" in hallyu:
        slugs.extend(_KOPIS_KPOP_SLUGS)
    # Legacy key "drama" now represents the UI label 公演.
    if any(a in activities for a in ("drama", "performance", "performances", "theater", "musical")):
        slugs.extend(_KOPIS_PERFORMANCE_SLUGS)
    if not slugs:
        return _KOPIS_GENRES
    return _kopis_genres_for_profile(None, slugs)


def _xml_text(node: ET.Element | None, name: str) -> str:
    if node is None:
        return ""
    found = node.find(name)
    return (found.text or "").strip() if found is not None and found.text else ""


def _parse_xml(content: bytes | str) -> ET.Element:
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    return ET.fromstring(content)


def _kopis_get(
    path: str,
    *,
    params: dict[str, Any],
    timeout: int,
    attempts: int = 2,
) -> requests.Response:
    last_exc: Exception | None = None
    clean_path = "/" + path.lstrip("/")
    for attempt in range(max(1, attempts)):
        for base in _KOPIS_BASE_URLS:
            try:
                resp = requests.get(
                    f"{base}{clean_path}",
                    params=params,
                    timeout=timeout,
                )
                resp.raise_for_status()
                return resp
            except Exception as exc:
                last_exc = exc
        if attempt + 1 < attempts:
            time.sleep(0.35 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _kopis_detail_url(mt20id: str) -> str:
    return f"{_KOPIS_PUBLIC_PAGE}{mt20id}"


def _kopis_related_url(detail: ET.Element | None) -> str:
    if detail is None:
        return ""
    urls: list[str] = []
    for rel in detail.findall(".//relate"):
        url = _xml_text(rel, "relateurl")
        if url.startswith("http"):
            urls.append(url)
    if not urls:
        return ""
    ticket_hosts = (
        "interpark",
        "ticketlink",
        "yes24",
        "melon",
        "ticketmelon",
        "ticket.",
    )
    for url in urls:
        low = url.lower()
        if "kopis.or.kr" not in low and any(host in low for host in ticket_hosts):
            return url
    for url in urls:
        if "kopis.or.kr" not in url.lower():
            return url
    return urls[0]


def _kopis_event_from_db(
    db: ET.Element,
    *,
    genre_page: str,
    genre_label: str,
    detail: ET.Element | None = None,
) -> TicketPlatformEvent | None:
    mt20id = _xml_text(db, "mt20id") or _xml_text(detail, "mt20id")
    title = _xml_text(db, "prfnm") or _xml_text(detail, "prfnm")
    if not mt20id or not title:
        return None
    start = _parse_yyyymmdd(_xml_text(db, "prfpdfrom") or _xml_text(detail, "prfpdfrom"))
    end = _parse_yyyymmdd(_xml_text(db, "prfpdto") or _xml_text(detail, "prfpdto")) or start
    venue = _xml_text(db, "fcltynm") or _xml_text(detail, "fcltynm")
    area = _xml_text(db, "area") or _xml_text(db, "signgucode") or _xml_text(detail, "area")
    genre = _xml_text(db, "genrenm") or _xml_text(detail, "genrenm") or genre_label
    poster = _xml_text(db, "poster") or _xml_text(detail, "poster")
    state = _xml_text(db, "prfstate") or _xml_text(detail, "prfstate")
    related = _kopis_related_url(detail)
    return TicketPlatformEvent(
        title=title,
        genre_page=genre_page,
        genre_label_ko=genre,
        venue=venue,
        place_region=area,
        play_start=start,
        play_end=end,
        goods_code=mt20id,
        ticket_url=related or _kopis_detail_url(mt20id),
        source="kopis",
        poster=poster,
        state=state,
    )


def _fetch_kopis_detail(mt20id: str, *, api_key: str, timeout: int) -> ET.Element | None:
    if not mt20id:
        return None
    try:
        resp = _kopis_get(
            f"/pblprfr/{mt20id}",
            params={"service": api_key},
            timeout=timeout,
        )
        root = _parse_xml(resp.content)
        return root.find(".//db")
    except Exception as exc:
        logger.warning("KOPIS detail fetch failed [%s]: %s", mt20id, exc)
        return None


def _fetch_kopis_genre(
    genre_code: str,
    genre_slug: str,
    genre_label: str,
    *,
    api_key: str,
    start_d: date,
    end_d: date,
    rows: int,
    timeout: int,
) -> list[TicketPlatformEvent]:
    try:
        resp = _kopis_get(
            "/pblprfr",
            params={
                "service": api_key,
                "stdate": start_d.strftime("%Y%m%d"),
                "eddate": end_d.strftime("%Y%m%d"),
                "cpage": 1,
                "rows": rows,
                "shcate": genre_code,
            },
            timeout=timeout,
        )
        root = _parse_xml(resp.content)
    except Exception as exc:
        logger.warning("KOPIS list fetch failed [%s]: %s", genre_code, exc)
        return []

    out: list[TicketPlatformEvent] = []
    for db in root.findall(".//db"):
        ev = _kopis_event_from_db(
            db,
            genre_page=genre_slug,
            genre_label=genre_label,
            detail=None,
        )
        if ev:
            out.append(ev)
    logger.info("KOPIS genre [%s] → %d performances", genre_code, len(out))
    return out


def _enrich_kopis_event(ev: TicketPlatformEvent, *, api_key: str, timeout: int) -> TicketPlatformEvent:
    detail = _fetch_kopis_detail(ev.goods_code, api_key=api_key, timeout=timeout)
    if detail is None:
        return ev
    enriched = _kopis_event_from_db(
        detail,
        genre_page=ev.genre_page,
        genre_label=ev.genre_label_ko,
        detail=detail,
    )
    if not enriched:
        return ev
    return replace(
        ev,
        title=enriched.title or ev.title,
        genre_label_ko=enriched.genre_label_ko or ev.genre_label_ko,
        venue=enriched.venue or ev.venue,
        place_region=enriched.place_region or ev.place_region,
        play_start=enriched.play_start or ev.play_start,
        play_end=enriched.play_end or ev.play_end,
        ticket_url=enriched.ticket_url or ev.ticket_url,
        poster=enriched.poster or ev.poster,
        state=enriched.state or ev.state,
    )


def _is_major_or_region_relevant(
    ev: TicketPlatformEvent, blob: str, profile: dict | None = None
) -> tuple[int, str]:
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
    if _profile_jeju_only(profile):
        if any(m.lower() in hay for m in _JEJU_REGION_MARKERS):
            score += 40
            reason = reason or "jeju_match"
        elif not any(m.lower() in hay for m in _JEJU_REGION_MARKERS):
            score -= 25
    if blob:
        for token in blob.replace(",", " ").split():
            if len(token) >= 2 and token in hay:
                score += 15
                reason = reason or "profile_token_match"
    return score, reason


def fetch_ticket_platform_events(
    traveler_profile: dict | None,
    *,
    max_total: int = 36,
    timeout_per_genre: int = 14,
    genre_slugs: list[str] | tuple[str, ...] | None = None,
) -> list[TicketPlatformEvent]:
    """여행 기간과 겹치는 공연·전시 — KOPIS OpenAPI 기반."""
    api_key = _kopis_api_key()
    if not api_key:
        logger.info("KOPIS_API_KEY is not configured; skip performance lookup")
        return []

    start_d, end_d = _travel_window(traveler_profile)
    if not start_d:
        start_d = date.today()
    if not end_d:
        end_d = start_d + timedelta(days=14)
    if end_d < start_d:
        end_d = start_d

    merged: list[TicketPlatformEvent] = []
    genres = _kopis_genres_for_profile(traveler_profile, genre_slugs)
    rows_per_genre = max(8, min(30, max_total))
    for genre_code, genre_slug, genre_label in genres:
        merged.extend(
            _fetch_kopis_genre(
                genre_code,
                genre_slug,
                genre_label,
                api_key=api_key,
                start_d=start_d,
                end_d=end_d,
                rows=rows_per_genre,
                timeout=timeout_per_genre,
            )
        )

    # 기간 필터
    in_window: list[TicketPlatformEvent] = []
    for ev in merged:
        pe = ev.play_end or ev.play_start
        if ev.play_start is not None and pe is not None:
            if _overlap(start_d, end_d, ev.play_start, pe):
                in_window.append(ev)
            continue

    # 중복 mt20id
    seen: set[str] = set()
    deduped: list[TicketPlatformEvent] = []
    for ev in in_window:
        if ev.goods_code in seen:
            continue
        seen.add(ev.goods_code)
        deduped.append(ev)

    blob = _profile_location_blob(traveler_profile)
    scored: list[tuple[int, TicketPlatformEvent]] = []
    for ev in deduped:
        sc, _ = _is_major_or_region_relevant(ev, blob, traveler_profile)
        scored.append((sc, ev))

    scored.sort(key=lambda x: (-x[0], x[1].play_start or date.min))
    filtered = [ev for _, ev in scored if _event_matches_trip_region(ev, traveler_profile)]
    if not filtered:
        logger.info(
            "KOPIS: no events for regions %s",
            sorted(_trip_active_region_keys(traveler_profile)),
        )
    selected = (filtered or [ev for _, ev in scored])[:max_total]
    return [
        _enrich_kopis_event(ev, api_key=api_key, timeout=timeout_per_genre)
        for ev in selected
    ]


def fmt_ticket_platform_events(events: list[TicketPlatformEvent], lang: str = "ja") -> str:
    """LLM 컨텍스트용 텍스트."""
    if not events:
        empty = (
            "(KOPIS 공연예술통합전산망 — 해당 여행 기간·조건에 맞는 공연 메타 없음)"
            if lang == "ko"
            else "(KOPIS公演芸術統合電算網 — 該当旅行期間に一致する公演メタなし)"
        )
        return empty
    intro = (
        "KOPIS 공연예술통합전산망 OpenAPI — 예매/상세는 각 URL에서 확인."
        if lang == "ko"
        else "KOPIS公演芸術統合電算網 OpenAPI — 購入・詳細は各URLで確認。"
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
            f"    기간: {dr or '(일정 정보 없음)'}\n"
            f"    상태: {ev.state or '(미상)'}\n"
            f"    URL: {ev.ticket_url}"
        )
    return "\n".join(lines)
