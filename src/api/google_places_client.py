"""Google Places API client for nearby travel recommendations."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Iterable

import requests


PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
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
    ]
)


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


class GooglePlacesClient:
    """Small wrapper around Places API Nearby Search (New)."""

    def __init__(self, api_key: str | None = None, timeout: int = 12):
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
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
            raise ValueError("GOOGLE_MAPS_API_KEY is not configured.")

        radius = max(1, min(int(radius_meters), 50000))
        body = {
            "includedTypes": list(included_types),
            "maxResultCount": max(1, min(int(max_results), 20)),
            "rankPreference": "POPULARITY",
            "languageCode": language_code,
            "regionCode": "KR",
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
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
            PLACES_NEARBY_URL,
            json=body,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return [
            self._normalize_place(place, latitude, longitude)
            for place in data.get("places", [])
        ]

    def _normalize_place(
        self,
        place: dict,
        origin_latitude: float,
        origin_longitude: float,
    ) -> NearbyPlace:
        location = place.get("location") or {}
        place_latitude = location.get("latitude")
        place_longitude = location.get("longitude")
        distance = None
        if place_latitude is not None and place_longitude is not None:
            distance = round(
                _haversine_meters(
                    origin_latitude,
                    origin_longitude,
                    place_latitude,
                    place_longitude,
                )
            )

        opening_hours = place.get("currentOpeningHours") or {}
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
        )


def recommend_nearby_places(
    latitude: float,
    longitude: float,
    radius_meters: int = 1000,
    language_code: str = "ja",
) -> dict[str, list[NearbyPlace]]:
    """Return tourist attractions and cafes near the given coordinates."""
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
        included_types=["cafe"],
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
