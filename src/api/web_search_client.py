"""웹 검색 클라이언트 — 공식 API에 없는 이벤트·행사 정보 보완용.

DuckDuckGo 텍스트 검색을 사용 (API 키 불필요).
패키지 미설치 시 graceful fallback (빈 결과 반환).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

try:
    from ddgs import DDGS
    from ddgs.exceptions import DuckDuckGoSearchException, RatelimitException
    _DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # type: ignore[no-redef]
        from duckduckgo_search.exceptions import DuckDuckGoSearchException, RatelimitException  # type: ignore[no-redef]
        _DDGS_AVAILABLE = True
    except ImportError:
        _DDGS_AVAILABLE = False
        DuckDuckGoSearchException = Exception  # type: ignore[misc,assignment]
        RatelimitException = Exception         # type: ignore[misc,assignment]
        logger.debug("ddgs / duckduckgo-search not installed — web search disabled")


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str


_STADIUM_FOOD_EXCLUDE_RE = (
    "구내식당", "사내식당", "직원식당", "급식", "단체급식",
    "社員食堂", "職員食堂", "給食", "canteen", "cafeteria",
)


def _is_bad_stadium_food_result(result: WebSearchResult) -> bool:
    blob = f"{result.title} {result.snippet} {result.url}".lower()
    return any(token.lower() in blob for token in _STADIUM_FOOD_EXCLUDE_RE)


# 웹 검색을 트리거할 이벤트 관련 키워드
_EVENT_TRIGGER_KEYWORDS: list[str] = [
    # 한국어
    "축제", "페스티벌", "공연", "콘서트", "이벤트", "행사", "박람회", "전시",
    "불꽃", "워터밤", "불꽃놀이", "花火",
    "언제", "날짜", "일정", "개최", "열려", "시작",
    # English
    "festival", "concert", "event", "exhibition", "fair", "show",
    "waterbomb", "firework",
    # Japanese
    "フェスティバル", "コンサート", "イベント", "展示", "祭り",
    "いつ", "開催", "始まる",
]

# 연도 패턴 — 연도가 포함된 쿼리는 현재 정보가 필요할 가능성 높음
_YEAR_PATTERN = ("2025", "2026", "2027")


def _trip_overlaps_summer_festival_window(traveler_profile: dict | None) -> bool:
    """6〜9月の大型フェス（Waterbomb 等）候補 — itinerary でウェブ検索を補強するトリガー。"""
    if not traveler_profile:
        return False
    try:
        from src.api.sports_schedule_client import travel_dates_from_profile
    except Exception:
        return False
    s, e = travel_dates_from_profile(traveler_profile)
    if not s:
        return False
    if not e:
        e = s + timedelta(days=14)
    if e < s:
        e = s
    for y in range(s.year, e.year + 1):
        win_s, win_e = date(y, 6, 1), date(y, 9, 30)
        if s <= win_e and e >= win_s:
            return True
    return False


def _needs_web_search(
    user_message: str,
    keyword: str,
    category: str,
    traveler_profile: dict | None = None,
) -> bool:
    """웹 검색이 필요한 쿼리인지 판단."""
    if category not in ("culture", "leisure", "itinerary", "general"):
        return False
    text = (user_message + " " + keyword).lower()
    has_event_kw = any(kw.lower() in text for kw in _EVENT_TRIGGER_KEYWORDS)
    has_year = any(yr in text for yr in _YEAR_PATTERN)
    if has_event_kw or has_year:
        return True
    # 日程プラン: 夏の旅行期間なら Waterbomb 等の取得のためウェブ検索を必ず試す
    if category == "itinerary" and _trip_overlaps_summer_festival_window(traveler_profile):
        return True
    return False


def _build_itinerary_festival_web_query(traveler_profile: dict) -> str | None:
    """夏の音楽フェス・Waterbomb 向け DDG クエリ（API に無いことが多い）。"""
    try:
        from src.api.sports_schedule_client import travel_dates_from_profile
    except Exception:
        return None
    s, e = travel_dates_from_profile(traveler_profile)
    if not s:
        return None
    if not e:
        e = s + timedelta(days=14)
    if e < s:
        e = s
    regions = [str(r).lower() for r in (traveler_profile.get("regions") or [])]
    zones: list[str] = []
    if "gyeonggi" in regions:
        zones.extend(["경기도", "고양", "킨텍스", "KINTEX"])
    if "seoul" in regions:
        zones.append("서울")
    if "incheon" in regions:
        zones.append("인천")
    zone_str = " ".join(zones) if zones else "서울 경기도"
    y = s.year
    return (
        f"{zone_str} 워터밤 Waterbomb {y} 일정 티켓 "
        f"{s.isoformat()}~{e.isoformat()} 한국"
    )


_MAX_USER_MSG_QUERY_LEN = 150


def _build_query(user_message: str, keyword: str) -> str:
    """LLM 키워드 + 사용자 메시지 → 검색 최적화 쿼리."""
    text = user_message + keyword
    has_year = any(yr in text for yr in _YEAR_PATTERN)
    # When user_message is very long (e.g., wizard itinerary prompt), prefer keyword
    # to avoid Bing 400 errors from URLs exceeding length limits.
    if keyword.strip() and len(user_message) > _MAX_USER_MSG_QUERY_LEN:
        base = keyword.strip()
    else:
        base = user_message[:_MAX_USER_MSG_QUERY_LEN].strip()
    if not has_year:
        base = f"{base} 2026"
    if "한국" not in base and "korea" not in base.lower() and "서울" not in base:
        base = f"한국 {base}"
    return base


class WebSearchClient:
    """DuckDuckGo 웹 검색 — 이벤트·행사 정보 보완."""

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    @property
    def is_available(self) -> bool:
        return _DDGS_AVAILABLE

    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[WebSearchResult]:
        if not _DDGS_AVAILABLE:
            return []
        try:
            with DDGS() as ddgs:
                raw = ddgs.text(
                    query,
                    region="kr-ko",
                    safesearch="moderate",
                    timelimit=None,
                    max_results=max_results,
                )
            raw = raw or []
            results = [
                WebSearchResult(
                    title=r.get("title", "").strip(),
                    url=r.get("href", "").strip(),
                    snippet=r.get("body", "").strip(),
                )
                for r in raw
                if r.get("title") or r.get("body")
            ]
            logger.info("web search [%r] → %d results", query[:60], len(results))
            return results
        except RatelimitException:
            logger.warning("web search rate limited — skipping")
            return []
        except DuckDuckGoSearchException as exc:
            logger.warning("web search failed [%r]: %s", query[:60], exc)
            return []
        except Exception as exc:
            logger.warning("web search unexpected error [%r]: %s", query[:60], exc)
            return []

    def search_for_query(
        self,
        user_message: str,
        keyword: str,
        category: str,
        max_results: int = 4,
        traveler_profile: dict | None = None,
    ) -> list[WebSearchResult]:
        """라우터용 — 트리거 판단 후 검색 실행."""
        if not _needs_web_search(user_message, keyword, category, traveler_profile):
            return []
        queries: list[str] = []
        if (
            category == "itinerary"
            and traveler_profile
            and _trip_overlaps_summer_festival_window(traveler_profile)
        ):
            fq = _build_itinerary_festival_web_query(traveler_profile)
            if fq:
                queries.append(fq)
        queries.append(_build_query(user_message, keyword))

        seen: set[str] = set()
        merged: list[WebSearchResult] = []
        per_q = max(3, min(max_results, 5))
        for q in queries:
            for r in self.search(q, max_results=per_q):
                key = (r.url or "").strip() or (r.title or "").strip()
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                merged.append(r)
                if len(merged) >= max_results:
                    return merged
        return merged[:max_results]


def fetch_stadium_food_by_venue(
    venues: list[tuple[str, str, str]] | list[tuple[str, str]],
    *,
    lang: str = "ja",
    max_results_per: int = 4,
    max_workers: int = 4,
) -> dict[str, list[WebSearchResult]]:
    """경기장별 내부 먹거리 — Places 미등록 매점을 웹 검색으로 보완."""
    if not venues:
        return {}
    try:
        from src.api.sports_schedule_client import build_stadium_food_search_queries
    except Exception:
        return {}

    import concurrent.futures

    normalized: list[tuple[str, str, str]] = []
    for item in venues:
        if len(item) >= 3:
            normalized.append((item[0], item[1], item[2]))
        else:
            normalized.append((item[0], item[1], ""))

    if not _DDGS_AVAILABLE:
        return {}

    client = WebSearchClient()

    def _one(item: tuple[str, str, str]) -> tuple[str, list[WebSearchResult]]:
        venue, league, _home = item
        merged: list[WebSearchResult] = []
        seen: set[str] = set()
        for q in build_stadium_food_search_queries(venue, league, lang):
            for r in client.search(q, max_results=max_results_per):
                if _is_bad_stadium_food_result(r):
                    continue
                key = (r.url or "").strip() or (r.title or "").strip()
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                merged.append(r)
                if len(merged) >= max_results_per:
                    return venue, merged
        return venue, merged

    out: dict[str, list[WebSearchResult]] = {}
    workers = min(max_workers, len(normalized))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for venue, results in pool.map(_one, normalized):
            if results:
                out[venue] = results
    return out


def fmt_web_search_results(results: list[WebSearchResult]) -> str:
    """LLM 컨텍스트용 포맷."""
    if not results:
        return ""
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r.title}")
        if r.snippet:
            lines.append(f"    {r.snippet[:300]}")
        if r.url:
            lines.append(f"    URL: {r.url}")
    return "\n".join(lines)
