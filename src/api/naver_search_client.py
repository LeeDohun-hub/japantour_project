"""Official Naver Search API client for local place quality signals.

Naver Maps place visitor-review keywords are not exposed through an official
public API. This client uses official Local and Blog Search APIs to build a
conservative quality score from discoverability, blog review volume, recency,
and preference keyword matches.
"""

from __future__ import annotations

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

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured:
            return {}
        with NaverSearchClient._rate_lock:
            wait = NaverSearchClient._min_interval - (time.monotonic() - NaverSearchClient._last_request_at)
            if wait > 0:
                time.sleep(wait)
            NaverSearchClient._last_request_at = time.monotonic()
        try:
            resp = requests.get(url, params=params, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("Naver Search request failed [%s]: %s", params.get("query"), exc)
            return {}
        except ValueError:
            logger.warning("Naver Search invalid JSON [%s]", params.get("query"))
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
        local_items = self.search_local(query, display=display)
        out: list[NaverPlace] = []
        seen: set[str] = set()
        for idx, item in enumerate(local_items):
            name = _clean_html(item.get("title"))
            if not name:
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
            maps_url = naver_map_search_url(f"{name} {area_hint}".strip(), lat, lng)
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
