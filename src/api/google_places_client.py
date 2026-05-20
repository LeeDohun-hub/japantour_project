"""Google Places API client for nearby travel recommendations."""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Iterable

import requests

logger = logging.getLogger(__name__)


PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PHOTO_BASE_URL = "https://places.googleapis.com/v1/{name}/media"

DEFAULT_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.rating",
        "places.userRatingCount",
        "places.currentOpeningHours",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.priceLevel",
        "places.photos",
        "places.servesBreakfast",
        "places.dineIn",
    ]
)

_PRICE_DISPLAY: dict[str, str] = {
    "PRICE_LEVEL_FREE": "무료",
    "PRICE_LEVEL_INEXPENSIVE": "¥",
    "PRICE_LEVEL_MODERATE": "¥¥",
    "PRICE_LEVEL_EXPENSIVE": "¥¥¥",
    "PRICE_LEVEL_VERY_EXPENSIVE": "¥¥¥¥",
}


@dataclass(frozen=True)
class NearbyPlace:
    """Normalized place data returned by Google Places."""

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
    price_level: str | None = None       # e.g. "¥¥" (변환 후 표시용)
    photo_name: str | None = None        # places/.../photos/... (proxy용)
    serves_breakfast: bool | None = None
    has_restaurant: bool | None = None   # dineIn 필드
    search_area: str | None = None       # itinerary 검색 시 에리어 라벨


def _resolve_api_key(explicit: str | None = None) -> str | None:
    """GOOGLE_HOTELS_API_KEY 우선, 없으면 GOOGLE_MAPS_API_KEY."""
    return (
        explicit
        or os.getenv("GOOGLE_HOTELS_API_KEY")
        or os.getenv("GOOGLE_MAPS_API_KEY")
    )


class GooglePlacesClient:
    """Small wrapper around Places API Nearby Search (New)."""

    def __init__(self, api_key: str | None = None, timeout: int = 12):
        self.api_key = _resolve_api_key(api_key)
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search_nearby(
        self,
        latitude: float,
        longitude: float,
        included_types: Iterable[str],
        radius_meters: int = 1000,
        max_results: int = 8,
        language_code: str = "ja",
    ) -> list[NearbyPlace]:
        """Search nearby places and normalize the response."""
        if not self.api_key:
            raise ValueError("Google API key is not configured.")

        radius = max(1, min(int(radius_meters), 50000))
        body = {
            "includedTypes": list(included_types),
            "maxResultCount": max(1, min(int(max_results), 20)),
            "rankPreference": "POPULARITY",
            "languageCode": language_code,
            "regionCode": "KR",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius),
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
        }

        response = requests.post(
            PLACES_NEARBY_URL, json=body, headers=headers, timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        return [
            self._normalize_place(place, origin_latitude=latitude, origin_longitude=longitude)
            for place in data.get("places", [])
        ]

    def search_by_text(
        self,
        text_query: str,
        max_results: int = 5,
        language_code: str = "ja",
        region_code: str = "KR",
        included_type: str | None = None,
        page_token: str | None = None,
    ) -> tuple[list[NearbyPlace], str | None]:
        """텍스트 쿼리로 장소 검색 (예: '성수동 맛집', '명동 호텔').

        Returns:
            (places, next_page_token) — next_page_token is None when no more pages.
        """
        if not self.api_key:
            raise ValueError("Google API key is not configured.")

        body: dict = {
            "textQuery": text_query,
            "maxResultCount": max(1, min(int(max_results), 20)),
            "languageCode": language_code,
            "regionCode": region_code,
        }
        if included_type:
            body["includedType"] = included_type
        if page_token:
            body["pageToken"] = page_token

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
        }

        response = requests.post(
            PLACES_TEXT_SEARCH_URL, json=body, headers=headers, timeout=self.timeout
        )
        logger.info("Places textSearch HTTP %d — query=%r", response.status_code, text_query)
        if not response.ok:
            logger.warning("Places textSearch error body: %s", response.text[:400])
        response.raise_for_status()
        data = response.json()
        raw_places = data.get("places", [])
        next_token = data.get("nextPageToken") or None
        logger.info(
            "Places textSearch returned %d places (has_next=%s)",
            len(raw_places),
            bool(next_token),
        )
        places = [self._normalize_place(place) for place in raw_places]
        return places, next_token

    def search_by_text_all(
        self,
        text_query: str,
        *,
        max_total: int = 60,
        language_code: str = "ja",
        region_code: str = "KR",
        included_type: str | None = None,
    ) -> list[NearbyPlace]:
        """Text Search 전 페이지 수집 (API 상한 약 60건)."""
        cap = max(1, min(int(max_total), 60))
        collected: list[NearbyPlace] = []
        seen: set[str] = set()
        page_token: str | None = None

        while len(collected) < cap:
            batch, page_token = self.search_by_text(
                text_query,
                max_results=20,
                language_code=language_code,
                region_code=region_code,
                included_type=included_type,
                page_token=page_token,
            )
            if not batch:
                break
            for place in batch:
                key = f"{place.name}|{place.address}"
                if key in seen:
                    continue
                seen.add(key)
                collected.append(place)
                if len(collected) >= cap:
                    break
            if not page_token:
                break

        return collected

    def find_for_plan_item(
        self,
        maps_url: str,
        query: str = "",
        language_code: str = "ja",
    ) -> NearbyPlace | None:
        """プラン内 Maps URL + 店名ラベルから Places 詳細を取得."""
        if not self.is_configured:
            return None
        target_cid = extract_maps_cid(maps_url)
        q = (query or "").strip()
        if not q and not target_cid:
            return None
        if q:
            try:
                results, _ = self.search_by_text(
                    text_query=q,
                    max_results=8,
                    language_code=language_code,
                )
            except Exception as exc:
                logger.warning("find_for_plan_item search failed: %s", exc)
                return None
            if target_cid:
                for place in results:
                    if maps_urls_same_cid(place.google_maps_uri, maps_url):
                        return place
            if results:
                return results[0]
        return None

    def _normalize_place(
        self,
        place: dict,
        origin_latitude: float | None = None,
        origin_longitude: float | None = None,
    ) -> NearbyPlace:
        location = place.get("location") or {}
        place_latitude = location.get("latitude")
        place_longitude = location.get("longitude")
        distance = None
        if (
            place_latitude is not None
            and place_longitude is not None
            and origin_latitude is not None
            and origin_longitude is not None
        ):
            distance = round(
                _haversine_meters(
                    origin_latitude, origin_longitude,
                    place_latitude, place_longitude,
                )
            )

        opening_hours = place.get("currentOpeningHours") or {}
        raw_price = place.get("priceLevel")

        # 첫 번째 사진 이름 추출
        photos = place.get("photos") or []
        photo_name = photos[0].get("name") if photos else None

        return NearbyPlace(
            name=(place.get("displayName") or {}).get("text", "이름 없음"),
            category=place.get("primaryType", "place"),
            address=place.get("formattedAddress", ""),
            latitude=place_latitude,
            longitude=place_longitude,
            rating=place.get("rating"),
            user_rating_count=place.get("userRatingCount"),
            google_maps_uri=place.get("googleMapsUri"),
            is_open_now=opening_hours.get("openNow"),
            distance_meters=distance,
            price_level=_PRICE_DISPLAY.get(raw_price) if raw_price else None,
            photo_name=photo_name,
            serves_breakfast=place.get("servesBreakfast"),
            has_restaurant=place.get("dineIn"),
        )


def extract_maps_cid(maps_url: str) -> str | None:
    """Google Maps URL の cid パラメータを抽出."""
    if not maps_url:
        return None
    match = re.search(r"[?&]cid=(\d+)", maps_url)
    return match.group(1) if match else None


def maps_urls_same_cid(a: str | None, b: str | None) -> bool:
    ca, cb = extract_maps_cid(a or ""), extract_maps_cid(b or "")
    if ca and cb:
        return ca == cb
    if not a or not b:
        return False
    return a.split("&g_mp=")[0].rstrip("/") == b.split("&g_mp=")[0].rstrip("/")


def recommend_nearby_places(
    latitude: float,
    longitude: float,
    radius_meters: int = 1000,
    language_code: str = "ja",
) -> dict[str, list[NearbyPlace]]:
    """Return tourist attractions and food/cafe spots near the given coordinates."""
    client = GooglePlacesClient()
    attractions = client.search_nearby(
        latitude=latitude,
        longitude=longitude,
        included_types=["tourist_attraction"],
        radius_meters=radius_meters,
        max_results=6,
        language_code=language_code,
    )
    cafes = client.search_nearby(
        latitude=latitude,
        longitude=longitude,
        included_types=["restaurant", "cafe"],
        radius_meters=radius_meters,
        max_results=6,
        language_code=language_code,
    )
    return {
        "tourist_attractions": _rank_places(attractions),
        "cafes": _rank_places(cafes),
    }


def _rank_places(places: list[NearbyPlace]) -> list[NearbyPlace]:
    def score(place: NearbyPlace) -> tuple[float, int]:
        rating = place.rating or 0.0
        review_weight = min(place.user_rating_count or 0, 1000) / 1000
        distance_penalty = (place.distance_meters or 50000) / 50000
        open_bonus = 0.3 if place.is_open_now else 0.0
        return (rating + review_weight + open_bonus - distance_penalty, -(place.distance_meters or 50000))

    return sorted(places, key=score, reverse=True)


def _haversine_meters(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    earth_radius_meters = 6371000
    lat1 = math.radians(latitude1)
    lat2 = math.radians(latitude2)
    delta_lat = math.radians(latitude2 - latitude1)
    delta_lon = math.radians(longitude2 - longitude1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_meters * c
