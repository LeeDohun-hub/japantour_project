"""인터파크 NOL 티켓 공연·전시 메타데이터.

티켓링크 공연 메인은 순수 SPA라 HTML만으로는 목록을 얻기 어렵다. 인터파크는 아래 3경로를 병합한다.

- 소스 ① 장르 페이지 ProductList: ``tickets.interpark.com/contents/genre/{concert|musical|...}``
  HTML에 임베드된 상품 JSON(하위 탭 목록에 가까운 전체 리스트, 배너만이 아님)
- 소스 ② 장르 SSR: 동일 URL의 ``__NEXT_DATA__`` (배너·ticketOpen·interparkPlay)
- 소스 ③ 통합 검색: ``/contents/search?keyword=...`` — 장르별 하위 키워드(페스티벌·가요 등) +
  워터밤 등 메인·ProductList에 없는 공연 보강

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
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

# ProductList 영역에 임베드된 상품 블록 (장르 페이지 HTML 전체 파싱)
_HTML_GOODS_BLOCK_RE = re.compile(
    r'"goodsCode":"(\d{8})"'
    r'.*?"goodsName":"([^"\\]+(?:\\.[^"\\])*)"'
    r'.*?"placeName":"([^"\\]*)"'
    r'.*?"playStartDate":"(\d{8})"'
    r'.*?"playEndDate":"(\d{8})"',
    re.DOTALL,
)

_INTERPARK_GENRE_BASE = "https://tickets.interpark.com/contents/genre"
_INTERPARK_SEARCH_URL = "https://tickets.interpark.com/contents/search"

# slug, 라벨, 하위 탭에 대응하는 검색 키워드(통합 검색으로 보강)
_GENRE_CATALOG: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("concert", "콘서트", ("페스티벌", "가요", "록", "재즈", "인디", "트로트", "발라드", "힙합", "어쿠스틱")),
    ("musical", "뮤지컬", ("창작", "라이선스", "갈라", "내한", "웨스트엔드")),
    ("play", "연극", ("코미디", "드라마", "스릴러", "리더십")),
    ("exhibition", "전시", ("전시", "체험", "박람회", "아트", "팝업")),
    ("classic", "클래식/무용", ("클래식", "무용", "오페라", "발레", "콘서트")),
    ("family", "아동/가족", ("아동", "가족", "키즈", "인형극")),
)

# 여행 프로필·계절에 따른 검색 키워드 (메인 스냅샷에 없는 페스티벌 보강)
_SEARCH_KEYWORDS_SUMMER: tuple[str, ...] = (
    "워터밤",
    "waterbomb",
    "페스티벌",
)
_SEARCH_KEYWORDS_BY_REGION: dict[str, tuple[str, ...]] = {
    "gyeonggi": ("고양 페스티벌", "킨텍스 콘서트", "일산 공연"),
    "seoul": ("서울 페스티벌", "서울 콘서트"),
    "incheon": ("인천 페스티벌",),
    "busan": ("부산 페스티벌",),
    "jeju": (
        "제주 공연",
        "서귀포 공연",
        "제주 콘서트",
        "제주 뮤지컬",
        "제주 전시",
    ),
}

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
    "busan": ("부산", "釜山", "busan", "金海", "海雲臺", "海雲台"),
    "gyeongsang": ("부산", "대구", "경상", "庆尚", "大邱", "金海"),
    "gangwon": ("강원", "江原", "춘천", "春川", "강릉", "江陵", "속초", "束草"),
    "jeolla": ("전주", "全州", "광주", "光州", "全羅", "光州"),
    "chungcheong": ("대전", "大田", "忠清", "청주", "清州"),
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

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

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
    keys = {str(r).lower() for r in (profile or {}).get("regions") or [] if r}
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
    s = str(raw).strip().replace("-", "").replace(".", "")[:8]
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _trip_overlaps_summer(start_d: date, end_d: date) -> bool:
    for y in range(start_d.year, end_d.year + 1):
        if start_d <= date(y, 9, 30) and end_d >= date(y, 6, 1):
            return True
    return False


def _build_search_queries(traveler_profile: dict | None, start_d: date, end_d: date) -> list[str]:
    """통합 검색 키워드 — 장르·하위 탭·지역 조합(최대 28개)."""
    out: list[str] = []
    if _trip_overlaps_summer(start_d, end_d):
        out.extend(_SEARCH_KEYWORDS_SUMMER)
    else:
        out.append("페스티벌")

    for _slug, label, subs in _GENRE_CATALOG:
        out.append(label)
        for sub in subs:
            out.append(sub)
            out.append(f"{label} {sub}")

    prof = traveler_profile or {}
    for reg in [str(r).lower() for r in (prof.get("regions") or [])]:
        out.extend(_SEARCH_KEYWORDS_BY_REGION.get(reg, ()))

    accom = prof.get("accommodation") or {}
    addr = " ".join(
        str(accom.get(k) or "") for k in ("address", "name", "detail", "region")
    ).lower()
    if any(k in addr for k in ("고양", "일산", "킨텍스", "kintex", "경기")):
        out.extend(_SEARCH_KEYWORDS_BY_REGION["gyeonggi"])
        if _trip_overlaps_summer(start_d, end_d):
            out.extend(("고양 페스티벌", "킨텍스 페스티벌"))
    if "서울" in addr or "seoul" in addr:
        out.extend(_SEARCH_KEYWORDS_BY_REGION["seoul"])
    for reg in [str(r).lower() for r in (prof.get("regions") or [])]:
        if reg == "jeju":
            out.extend(_SEARCH_KEYWORDS_BY_REGION["jeju"])

    return list(dict.fromkeys(q.strip() for q in out if q and q.strip()))[:28]


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


def _unescape_json_string(s: str) -> str:
    return s.replace("\\u0026", "&").replace('\\"', '"').replace("\\\\", "\\")


def _banner_goods_rows(banner: Any) -> list[dict]:
    """장르 페이지 배너·추천 블록."""
    if not isinstance(banner, dict):
        return []
    rows: list[dict] = []
    for key in ("hotItem", "bigBanner", "miniBanner", "mdPick", "saleZone"):
        block = banner.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, dict) and item.get("goodsCode"):
                    rows.append(item)
    return rows


def _parse_goods_embedded_html(
    html: str,
    genre_slug: str,
    genre_label: str,
) -> list[TicketPlatformEvent]:
    """장르 페이지 ProductList에 임베드된 상품 JSON 전체."""
    seen: set[str] = set()
    out: list[TicketPlatformEvent] = []
    for m in _HTML_GOODS_BLOCK_RE.finditer(html):
        code, name, venue, ps_raw, pe_raw = m.groups()
        if code in seen:
            continue
        seen.add(code)
        name = _unescape_json_string(name)
        venue = _unescape_json_string(venue)
        ps = _parse_yyyymmdd(ps_raw)
        pe = _parse_yyyymmdd(pe_raw) or ps
        out.append(
            TicketPlatformEvent(
                title=name,
                genre_page=genre_slug,
                genre_label_ko=genre_label,
                venue=venue,
                place_region="",
                play_start=ps,
                play_end=pe,
                goods_code=code,
                ticket_url=f"https://tickets.interpark.com/goods/{code}",
                source="interpark_product_list",
            )
        )
    return out


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
    ps = _parse_yyyymmdd(
        gi.get("playStartDate") or gi.get("startDate")
    )
    pe = _parse_yyyymmdd(
        gi.get("playEndDate") or gi.get("endDate")
    ) or ps
    link = (gi.get("link") or "").strip()
    if link and link.startswith("http"):
        ticket_url = link
    else:
        ticket_url = f"https://tickets.interpark.com/goods/{code}"
    region = (gi.get("goodsRegionStr") or gi.get("placeRegion") or "").strip()
    return TicketPlatformEvent(
        title=name,
        genre_page=genre_path,
        genre_label_ko=genre_label,
        venue=venue,
        place_region=region,
        play_start=ps,
        play_end=pe,
        goods_code=code,
        ticket_url=ticket_url,
        source=gi.get("_source") or "interpark_mticket",
    )


def _event_from_search_doc(doc: dict) -> TicketPlatformEvent | None:
    """통합 검색 ``searchResult.goods.docs`` 항목."""
    cat = (doc.get("category") or "").strip()
    sub = (doc.get("subCategory") or "").strip()
    label = f"{cat}>{sub}" if cat and sub else (cat or sub or "검색")
    gi = {**doc, "_source": "interpark_search"}
    return _event_from_goods_flat(
        gi,
        genre_path="search",
        genre_label=label,
    )


def _fetch_interpark_genre(
    genre_slug: str,
    genre_label: str,
    *,
    timeout: int = 14,
) -> list[TicketPlatformEvent]:
    """장르 페이지 — SSR 배너 + HTML ProductList(하위 목록에 가까운 전체 리스트)."""
    url = f"{_INTERPARK_GENRE_BASE}/{genre_slug}"
    try:
        r = requests.get(url, timeout=timeout, headers=_REQUEST_HEADERS)
        r.raise_for_status()
    except Exception as exc:
        logger.warning("interpark genre fetch failed [%s]: %s", genre_slug, exc)
        return []

    by_code: dict[str, TicketPlatformEvent] = {}

    for ev in _parse_goods_embedded_html(r.text, genre_slug, genre_label):
        by_code[ev.goods_code] = ev

    m = _NEXT_DATA_RE.search(r.text)
    if m:
        try:
            payload: dict[str, Any] = json.loads(m.group(1))
            pp = (payload.get("props") or {}).get("pageProps") or {}
            for row in pp.get("interparkPlay") or []:
                if not isinstance(row, dict):
                    continue
                gi = row.get("goodsInfo") or {}
                if isinstance(gi, dict):
                    gi = {**gi, "_source": "interpark_ssr"}
                    ev = _event_from_goods_flat(
                        gi, genre_path=genre_slug, genre_label=genre_label
                    )
                    if ev:
                        by_code.setdefault(ev.goods_code, ev)
            banner = pp.get("banner") or {}
            for gi in _banner_goods_rows(banner):
                gi = {**gi, "_source": "interpark_ssr"}
                ev = _event_from_goods_flat(
                    gi, genre_path=genre_slug, genre_label=genre_label
                )
                if ev:
                    by_code.setdefault(ev.goods_code, ev)
        except Exception as exc:
            logger.warning("interpark JSON parse [%s]: %s", genre_slug, exc)
    else:
        logger.warning("interpark no __NEXT_DATA__ [%s]", genre_slug)

    logger.info(
        "interpark genre [%s] → %d goods (html+ssr)",
        genre_slug,
        len(by_code),
    )
    return list(by_code.values())


def _fetch_interpark_search(keyword: str, *, timeout: int = 12) -> list[TicketPlatformEvent]:
    """인터파크 NOL 통합 검색 — 메인 장르 스냅샷에 없는 공연(워터밤 등) 보강."""
    url = f"{_INTERPARK_SEARCH_URL}?keyword={quote(keyword)}"
    try:
        r = requests.get(url, timeout=timeout, headers=_REQUEST_HEADERS)
        r.raise_for_status()
    except Exception as exc:
        logger.warning("interpark search failed [%r]: %s", keyword, exc)
        return []

    m = _NEXT_DATA_RE.search(r.text)
    if not m:
        logger.warning("interpark search no __NEXT_DATA__ [%r]", keyword)
        return []

    try:
        payload: dict[str, Any] = json.loads(m.group(1))
    except Exception as exc:
        logger.warning("interpark search JSON parse [%r]: %s", keyword, exc)
        return []

    pp = (payload.get("props") or {}).get("pageProps") or {}
    sr = (pp.get("searchResult") or {}).get("goods") or {}
    docs = sr.get("docs") if isinstance(sr, dict) else []
    out: list[TicketPlatformEvent] = []
    for doc in docs or []:
        if not isinstance(doc, dict):
            continue
        ev = _event_from_search_doc(doc)
        if ev:
            out.append(ev)
    logger.info("interpark search [%r] → %d goods", keyword, len(out))
    return out


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
) -> list[TicketPlatformEvent]:
    """여행 기간과 겹치는 공연·전시 — 장르 ProductList + 하위 검색 키워드 병합."""
    start_d, end_d = _travel_window(traveler_profile)
    if not start_d:
        start_d = date.today()
    if not end_d:
        end_d = start_d + timedelta(days=14)
    if end_d < start_d:
        end_d = start_d

    blob = _profile_location_blob(traveler_profile)
    search_queries = _build_search_queries(traveler_profile, start_d, end_d)

    merged: list[TicketPlatformEvent] = []
    genre_jobs = [(slug, label) for slug, label, _ in _GENRE_CATALOG]
    workers = min(16, len(genre_jobs) + len(search_queries))
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        futs: list = []
        for slug, label in genre_jobs:
            futs.append(
                pool.submit(
                    _fetch_interpark_genre, slug, label, timeout=timeout_per_genre
                )
            )
        for q in search_queries:
            futs.append(pool.submit(_fetch_interpark_search, q, timeout=timeout_per_genre))
        for fut in as_completed(futs):
            try:
                merged.extend(fut.result())
            except Exception as exc:
                logger.warning("interpark worker: %s", exc)

    # 기간 필터 — 날짜 없으면 대형 페스 키워드만 여행 기간과 함께 통과
    in_window: list[TicketPlatformEvent] = []
    for ev in merged:
        pe = ev.play_end or ev.play_start
        if ev.play_start is not None and pe is not None:
            if _overlap(start_d, end_d, ev.play_start, pe):
                in_window.append(ev)
            continue
        hay = f"{ev.title} {ev.venue}".lower()
        if any(s.lower() in hay for s in _MAJOR_EVENT_SUBSTRINGS):
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
        sc, _ = _is_major_or_region_relevant(ev, blob, traveler_profile)
        # 기간 내 전부 후보로 두되, 점수 0도 소량 포함(지역 무관 대형 공연 놓침 방지)
        scored.append((sc, ev))

    scored.sort(key=lambda x: (-x[0], x[1].play_start or date.min))
    filtered = [ev for _, ev in scored if _event_matches_trip_region(ev, traveler_profile)]
    if not filtered:
        logger.info(
            "interpark: no events for regions %s",
            sorted(_trip_active_region_keys(traveler_profile)),
        )
    return filtered[:max_total]


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
        "인터파크 NOL — 장르 ProductList(HTML) + 하위 키워드 검색 + SSR — 예매는 각 URL에서 확인."
        if lang == "ko"
        else "Interpark NOL — ジャンルProductList＋下位キーワード検索＋SSR — 購入は各URLで確認。"
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
