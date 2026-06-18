"""Official Naver Search API client for local place quality signals.

Naver Maps place visitor-review keywords are not exposed through an official
public API. This client uses official Local and Blog Search APIs to build a
conservative quality score from discoverability, blog review volume, recency,
and preference keyword matches.
"""

from __future__ import annotations

import copy
import html
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from src.api.naver_maps_client import NaverMapsClient, naver_map_search_url

logger = logging.getLogger(__name__)

LOCAL_SEARCH_URL = "https://openapi.naver.com/v1/search/local.json"
BLOG_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def naver_search_client_id() -> str:
    return _first_env("NAVER_SEARCH_CLIENT_ID", "NAVER_CLIENT_ID")


def naver_search_client_secret() -> str:
    return _first_env("NAVER_SEARCH_CLIENT_SECRET", "NAVER_CLIENT_SECRET")


def _clean_html(text: str | None) -> str:
    raw = html.unescape(str(text or ""))
    return re.sub(r"<[^>]+>", "", raw).strip()


def _norm(text: str | None) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or "").lower(), flags=re.UNICODE)


def _parse_yyyymmdd(text: str | None) -> datetime | None:
    try:
        return datetime.strptime(str(text or ""), "%Y%m%d")
    except ValueError:
        return None


# 제너릭 검색어 키워드 — 이 단어가 포함된 쿼리는 장소명 일치 검사를 건너뜀
# e.g. "홍대 맛집", "유성구 관광" 등은 반환 이름이 달라도 정상
_GENERIC_QUERY_WORDS: frozenset[str] = frozenset([
    "맛집", "관광", "명소", "거리", "카페", "식당", "레스토랑", "음식점",
    "체험", "박물관", "공원", "쇼핑", "시장", "축제", "온천", "볼거리",
    "야경", "관광지", "음식", "여행", "뷔페", "분식", "술집", "포차",
    # 숙박 관련 — 지역+숙박 유형 검색("경기도 고양시 호텔")을 특정 장소명으로 오판하지 않도록
    "호텔", "숙소", "숙박", "모텔", "펜션", "리조트", "게스트하우스", "여관", "민박",
])

_BAD_PLACE_QUERY_RE = re.compile(
    r"^(?:곳|장소|지점|스팟|후보|카페|식당|맛집|관광|명소|주변|근처|일대|"
    r"エリア|スポット|場所|カフェ|レストラン|観光|名所)$",
    re.I,
)


def _is_bad_place_query(query: str) -> bool:
    value = re.sub(r"\s+", " ", str(query or "")).strip()
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 2:
        return True
    if _BAD_PLACE_QUERY_RE.search(compact):
        return True
    if re.search(r"(?:지역|에리어|エリア|근처|주변|일대|近く|周辺).{0,12}(?:음식점|식당|맛집|한국음식|요리|レストラン|食堂|食事)", value, re.I):
        return True
    if re.search(r"(?:현지|当地|地元|한국\s*같은|韓国らしい).{0,12}(?:맛|요리|음식|グルメ|料理|食事)", value, re.I):
        return True
    if re.search(r"(?:공원|公園|타워|タワー|관광지|観光地).{0,10}(?:근처|주변|近く|周辺).{0,12}(?:음식점|식당|맛집|食事|レストラン)", value, re.I):
        return True
    if re.search(r"^\d+\s*곳$", value):
        return True
    if re.search(r"실제.{0,20}(?:요리점|음식점|식당|레스토랑)", value, re.I):
        return True
    if re.search(r"을\s*사용$", value):
        return True
    return False


def _is_specific_place_query(query: str) -> bool:
    """쿼리가 특정 장소명(고유명사)인지 판단. 제너릭 단어 포함 시 False."""
    tokens = re.findall(r"[가-힣]{2,}", query)
    if not tokens:
        return False  # 한글 없으면 판단 불가 — 검사 skip
    return not any(t in _GENERIC_QUERY_WORDS for t in tokens)


def _name_matches_query(name: str, query: str) -> bool:
    """반환된 장소명이 쿼리와 충분히 겹치는지 확인.

    - 제너릭 쿼리("홍대 맛집")는 항상 True(필터 없음)
    - 특정 장소명 쿼리("유성불고기")에서 반환 이름("버거킹")과 한글 토큰 겹침이
      전혀 없으면 False — 체인 오점 반환 방지
    """
    if not _is_specific_place_query(query):
        return True
    q_tokens = set(re.findall(r"[가-힣]{2,}", query))
    n_tokens = set(re.findall(r"[가-힣]{2,}", name))
    if not q_tokens or not n_tokens:
        return True  # 토큰 추출 불가 — 허용
    # 부분문자열 일치 (공백 제거): "홍대개미" ⊂ "홍대개미식당" → OK
    q_compact = re.sub(r"\s+", "", query)
    n_compact = re.sub(r"\s+", "", name)
    if q_compact in n_compact or n_compact in q_compact:
        return True
    # 토큰 교집합 존재: {"상상마당"} ∩ {"상상마당", "홍대점"} → OK
    return bool(q_tokens & n_tokens)


POSITIVE_KEYWORDS = {
    "음식이 맛있어요": ("맛있", "음식", "라멘", "맛집", "존맛"),
    "양이 많아요": ("양이", "푸짐", "많", "든든"),
    "가성비가 좋아요": ("가성비", "가격", "저렴", "합리"),
    "혼밥하기 좋아요": ("혼밥", "혼자", "1인"),
    "친절해요": ("친절", "서비스"),
    "분위기가 좋아요": ("분위기", "감성", "예쁘", "인테리어"),
    "특별한 메뉴가 있어요": ("특별", "커스텀", "대표", "시그니처"),
}


@dataclass(frozen=True)
class NaverPlace:
    name: str
    category: str
    address: str
    latitude: float | None
    longitude: float | None
    rating: float | None
    user_rating_count: int | None
    google_maps_uri: str | None
    is_open_now: bool | None
    distance_meters: int | None
    place_id: str | None = None
    price_level: str | None = None
    photo_name: str | None = None
    serves_breakfast: bool | None = None
    has_restaurant: bool | None = None
    search_area: str | None = None
    source: str = "naver_search"
    naver_score: float | None = None
    naver_place_url: str | None = None
    naver_local_link: str | None = None
    blog_review_count: int | None = None
    review_keywords: list[str] | None = None
    quality_reason: str | None = None
    mapx: str | None = None
    mapy: str | None = None
    name_ja: str | None = None


class NaverSearchClient:
    # Class-level rate limiter: max ~7 requests/sec to stay under Naver's QPS limit.
    _rate_lock = threading.Lock()
    _last_request_at: float = 0.0
    _min_interval: float = 0.15  # seconds between requests (~6-7 req/sec)
    _cache_lock = threading.Lock()
    _cache: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, dict[str, Any]]] = {}
    _cache_max_entries: int = 512
    _local_cache_ttl: float = 6 * 60 * 60
    _blog_cache_ttl: float = 60 * 60
    _error_cache_ttl: float = 2 * 60

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: int = 10,
    ):
        self.client_id = (client_id or naver_search_client_id()).strip()
        self.client_secret = (client_secret or naver_search_client_secret()).strip()
        self.timeout = timeout
        self.maps = NaverMapsClient(timeout=timeout)

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Accept": "application/json",
        }

    @classmethod
    def _cache_key(cls, url: str, params: dict[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
        return url, tuple(sorted((str(k), str(v)) for k, v in params.items()))

    @classmethod
    def _cache_ttl(cls, url: str, payload: dict[str, Any]) -> float:
        if not payload:
            return cls._error_cache_ttl
        if url == BLOG_SEARCH_URL:
            return cls._blog_cache_ttl
        return cls._local_cache_ttl

    @staticmethod
    def _clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return copy.deepcopy(payload)
        except Exception:
            return dict(payload)

    @classmethod
    def _cache_get(cls, key: tuple[str, tuple[tuple[str, str], ...]]) -> dict[str, Any] | None:
        now = time.monotonic()
        with cls._cache_lock:
            cached = cls._cache.get(key)
            if not cached:
                return None
            expires_at, payload = cached
            if expires_at <= now:
                cls._cache.pop(key, None)
                return None
            return cls._clone_payload(payload)

    @classmethod
    def _cache_set(cls, key: tuple[str, tuple[tuple[str, str], ...]], url: str, payload: dict[str, Any]) -> None:
        expires_at = time.monotonic() + cls._cache_ttl(url, payload)
        with cls._cache_lock:
            if len(cls._cache) >= cls._cache_max_entries:
                expired = [k for k, (exp, _) in cls._cache.items() if exp <= time.monotonic()]
                for k in expired:
                    cls._cache.pop(k, None)
                while len(cls._cache) >= cls._cache_max_entries:
                    cls._cache.pop(next(iter(cls._cache)))
            cls._cache[key] = (expires_at, cls._clone_payload(payload))

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured:
            return {}
        cache_key = self._cache_key(url, params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        with NaverSearchClient._rate_lock:
            wait = NaverSearchClient._min_interval - (time.monotonic() - NaverSearchClient._last_request_at)
            if wait > 0:
                time.sleep(wait)
            NaverSearchClient._last_request_at = time.monotonic()
        try:
            resp = requests.get(url, params=params, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict):
                self._cache_set(cache_key, url, payload)
                return self._clone_payload(payload)
            return {}
        except requests.RequestException as exc:
            logger.warning("Naver Search request failed [%s]: %s", params.get("query"), exc)
            self._cache_set(cache_key, url, {})
            return {}
        except ValueError:
            logger.warning("Naver Search invalid JSON [%s]", params.get("query"))
            self._cache_set(cache_key, url, {})
            return {}

    def search_local(self, query: str, *, display: int = 5) -> list[dict[str, Any]]:
        payload = self._get(
            LOCAL_SEARCH_URL,
            {
                "query": query,
                "display": max(1, min(int(display), 20)),
                "start": 1,
                "sort": "comment",
            },
        )
        return list(payload.get("items") or [])

    def search_blog(self, query: str, *, display: int = 10) -> tuple[list[dict[str, Any]], int]:
        payload = self._get(
            BLOG_SEARCH_URL,
            {
                "query": query,
                "display": max(1, min(int(display), 30)),
                "start": 1,
                "sort": "sim",
            },
        )
        return list(payload.get("items") or []), int(payload.get("total") or 0)

    def _blog_signals(self, place_name: str, area_hint: str = "") -> tuple[int, list[str], float, str]:
        query = " ".join(x for x in (place_name, area_hint) if x).strip()
        blogs, total = self.search_blog(query, display=10)
        blob = " ".join(
            f"{_clean_html(b.get('title'))} {_clean_html(b.get('description'))}"
            for b in blogs
        )
        found_keywords: list[str] = []
        for label, needles in POSITIVE_KEYWORDS.items():
            if any(n in blob for n in needles):
                found_keywords.append(label)

        recent_bonus = 0.0
        newest = None
        for b in blogs:
            dt = _parse_yyyymmdd(b.get("postdate"))
            if dt and (newest is None or dt > newest):
                newest = dt
        if newest:
            age_days = max(0, (datetime.now() - newest).days)
            if age_days <= 180:
                recent_bonus = 12.0
            elif age_days <= 365:
                recent_bonus = 7.0
            elif age_days <= 730:
                recent_bonus = 3.0

        reason_bits = []
        if total:
            reason_bits.append(f"blog reviews/search hits {total:,}")
        if found_keywords:
            reason_bits.append("keywords: " + ", ".join(found_keywords[:4]))
        if newest:
            reason_bits.append(f"latest blog {newest.date().isoformat()}")
        return total, found_keywords, recent_bonus, "; ".join(reason_bits)

    def _score(
        self,
        *,
        local_rank: int,
        local_name: str,
        query: str,
        blog_total: int,
        review_keywords: list[str],
        recent_bonus: float,
    ) -> float:
        match = 20.0 if _norm(local_name) and _norm(local_name) in _norm(query + local_name) else 12.0
        rank_score = max(0.0, 18.0 - (local_rank * 2.0))
        blog_score = min(22.0, math.log10(max(blog_total, 1)) * 8.0)
        keyword_score = min(25.0, len(review_keywords) * 5.0)
        score = match + rank_score + blog_score + keyword_score + recent_bonus
        return round(min(100.0, score), 1)

    def search_places(
        self,
        query: str,
        *,
        display: int = 5,
        area_hint: str = "",
        geocode: bool = True,
    ) -> list[NaverPlace]:
        if _is_bad_place_query(query):
            logger.debug("Naver search skipped bad place query: %r", query)
            return []
        # area_hint를 로컬 검색 쿼리에 포함하여 같은 이름 다른 지점 혼동 방지
        # 예: "KT&G 상상마당" + area_hint="홍대" → "KT&G 상상마당 홍대" → 홍대점 반환
        local_search_q = f"{query} {area_hint}".strip() if area_hint and area_hint not in query else query
        local_items = self.search_local(local_search_q, display=display)
        out: list[NaverPlace] = []
        seen: set[str] = set()
        for idx, item in enumerate(local_items):
            name = _clean_html(item.get("title"))
            if not name:
                continue
            # 장소명이 쿼리와 무관한 다른 가게인 경우 제외
            # e.g. "유성불고기" 검색 → "버거킹" 반환 → 토큰 겹침 없음 → skip
            if not _name_matches_query(name, query):
                logger.debug("Naver name mismatch filtered: query=%r returned=%r", query, name)
                continue
            address = _clean_html(item.get("roadAddress")) or _clean_html(item.get("address"))
            key = f"{_norm(name)}|{_norm(address)}"
            if key in seen:
                continue
            seen.add(key)

            lat = lng = None
            try:
                raw_x = float(item.get("mapx") or 0)
                raw_y = float(item.get("mapy") or 0)
                if raw_x > 10_000 and raw_y > 10_000:
                    # Naver Local returns coords as WGS84 × 10^7 integers
                    lng = raw_x / 1e7
                    lat = raw_y / 1e7
            except (TypeError, ValueError):
                pass
            if geocode and (lat is None or lng is None):
                geocoded = self.maps.geocode(address or name, limit=1)
                if geocoded:
                    lat, lng = geocoded[0].latitude, geocoded[0].longitude

            blog_total, keywords, recent_bonus, reason = self._blog_signals(name, area_hint)
            score = self._score(
                local_rank=idx,
                local_name=name,
                query=query,
                blog_total=blog_total,
                review_keywords=keywords,
                recent_bonus=recent_bonus,
            )
            maps_url = naver_map_search_url(name, lat, lng)
            out.append(
                NaverPlace(
                    name=name,
                    category=_clean_html(item.get("category")) or "place",
                    address=address,
                    latitude=lat,
                    longitude=lng,
                    rating=None,
                    user_rating_count=None,
                    google_maps_uri=maps_url,
                    is_open_now=None,
                    distance_meters=None,
                    naver_score=score,
                    naver_place_url=maps_url,
                    naver_local_link=str(item.get("link") or ""),
                    blog_review_count=blog_total,
                    review_keywords=keywords,
                    quality_reason=reason,
                    mapx=str(item.get("mapx") or ""),
                    mapy=str(item.get("mapy") or ""),
                )
            )
        out.sort(key=lambda p: p.naver_score or 0.0, reverse=True)
        return out
