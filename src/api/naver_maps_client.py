"""Naver Cloud Maps helpers.

This client intentionally covers only Naver Maps Platform APIs, not Naver
Developers Search API. It is used as a low-cost map/geocoding fallback when
Google Places is disabled.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

MAPS_APIGW_BASE_URL = "https://maps.apigw.ntruss.com"
GEOCODE_URL = f"{MAPS_APIGW_BASE_URL}/map-geocode/v2/geocode"
DIRECTIONS5_URL = f"{MAPS_APIGW_BASE_URL}/map-direction/v1/driving"


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def naver_maps_client_id() -> str:
    return _first_env(
        "NAVER_MAPS_CLIENT_ID",
        "NAVER_CLOUD_MAPS_CLIENT_ID",
        "NCP_MAPS_CLIENT_ID",
        "NCP_APIGW_API_KEY_ID",
        "X_NCP_APIGW_API_KEY_ID",
    )


def naver_maps_client_secret() -> str:
    return _first_env(
        "NAVER_MAPS_CLIENT_SECRET",
        "NAVER_CLOUD_MAPS_CLIENT_SECRET",
        "NCP_MAPS_CLIENT_SECRET",
        "NCP_APIGW_API_KEY",
        "X_NCP_APIGW_API_KEY",
    )


def is_naver_maps_configured(*, require_secret: bool = False) -> bool:
    if require_secret:
        return bool(naver_maps_client_id() and naver_maps_client_secret())
    return bool(naver_maps_client_id())


def naver_map_search_url(query: str, latitude: float | None = None, longitude: float | None = None) -> str:
    q = " ".join(str(query or "").split()).strip()
    if latitude is not None and longitude is not None:
        label = urllib.parse.quote(q or f"{latitude},{longitude}")
        return f"https://map.naver.com/p/search/{label}?c={longitude},{latitude},16,0,0,0,dh"
    if q:
        return f"https://map.naver.com/p/search/{urllib.parse.quote(q)}"
    return "https://map.naver.com/"


@dataclass(frozen=True)
class NaverGeocodeResult:
    name: str
    address: str
    latitude: float | None
    longitude: float | None
    maps_url: str


class NaverMapsClient:
    # 401 means the key pair is invalid for the geocoding API. Do not sleep or
    # retry in the same plan generation; just fall back to search URLs.
    _geocode_disabled: bool = False

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: int = 10,
    ):
        self.client_id = (client_id or naver_maps_client_id()).strip()
        self.client_secret = (client_secret or naver_maps_client_secret()).strip()
        self.timeout = timeout
        self.last_error: dict[str, Any] | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id)

    @property
    def can_geocode(self) -> bool:
        return bool(self.client_id and self.client_secret) and not NaverMapsClient._geocode_disabled

    @property
    def can_route(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def geocode(self, query: str, *, limit: int = 5) -> list[NaverGeocodeResult]:
        q = " ".join(str(query or "").split()).strip()
        if not q:
            return []
        if not self.can_geocode:
            if not (self.client_id and self.client_secret):
                logger.info("Naver Maps geocode skipped: client secret not configured")
            return []

        headers = {
            "X-NCP-APIGW-API-KEY-ID": self.client_id,
            "X-NCP-APIGW-API-KEY": self.client_secret,
            "Accept": "application/json",
        }
        try:
            resp = requests.get(
                GEOCODE_URL,
                params={"query": q},
                headers=headers,
                timeout=self.timeout,
            )
            if resp.status_code == 401:
                NaverMapsClient._geocode_disabled = True
                id_hint = self.client_id[:6] + "…" if len(self.client_id) > 6 else repr(self.client_id)
                sec_hint = self.client_secret[:4] + "…" if len(self.client_secret) > 4 else repr(self.client_secret)
                logger.warning(
                    "Naver Maps geocode 401 Unauthorized — "
                    "using CLIENT_ID=%s (len=%d) CLIENT_SECRET=%s (len=%d). "
                    "Geocoding disabled for this process; using Naver search URLs instead.",
                    id_hint, len(self.client_id), sec_hint, len(self.client_secret),
                )
                return []
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
        except requests.RequestException as exc:
            logger.warning("Naver Maps geocode request failed [%r]: %s", q[:60], exc)
            return []
        except ValueError:
            logger.warning("Naver Maps geocode invalid JSON [%r]", q[:60])
            return []

        out: list[NaverGeocodeResult] = []
        for row in (payload.get("addresses") or [])[: max(1, min(int(limit), 10))]:
            try:
                lng = float(row.get("x")) if row.get("x") not in (None, "") else None
                lat = float(row.get("y")) if row.get("y") not in (None, "") else None
            except (TypeError, ValueError):
                lat = lng = None
            address = (
                row.get("roadAddress")
                or row.get("jibunAddress")
                or row.get("englishAddress")
                or q
            )
            name = row.get("roadAddress") or row.get("jibunAddress") or q
            out.append(
                NaverGeocodeResult(
                    name=str(name),
                    address=str(address),
                    latitude=lat,
                    longitude=lng,
                    maps_url=naver_map_search_url(q, lat, lng),
                )
            )
        return out

    def driving_route(
        self,
        *,
        start_lng: float,
        start_lat: float,
        goal_lng: float,
        goal_lat: float,
        waypoints: list[tuple[float, float]] | None = None,
        option: str = "traoptimal",
        lang: str = "ja",
    ) -> dict[str, Any] | None:
        """Call Naver Directions 5 API.

        waypoints: list of (lng, lat) tuples, up to 5 intermediate stops.
        The API supports start + up to 5 waypoints + goal.
        """
        if not self.can_route:
            logger.info("Naver Directions skipped: client secret not configured")
            return None
        opt = option if option in {
            "trafast",
            "tracomfort",
            "traoptimal",
            "traavoidtoll",
            "traavoidcaronly",
        } else "traoptimal"
        headers = {
            "X-NCP-APIGW-API-KEY-ID": self.client_id,
            "X-NCP-APIGW-API-KEY": self.client_secret,
            "Accept": "application/json",
        }
        params: dict[str, str] = {
            "start": f"{start_lng},{start_lat}",
            "goal": f"{goal_lng},{goal_lat}",
            "option": opt,
            "lang": lang if lang in {"ko", "en", "ja", "zh"} else "ja",
        }
        if waypoints:
            # Naver Directions 5 accepts up to 5 waypoints as "lng,lat|lng,lat|..."
            via = "|".join(f"{lng},{lat}" for lng, lat in waypoints[:5])
            params["waypoints"] = via
        try:
            resp = requests.get(DIRECTIONS5_URL, params=params, headers=headers, timeout=self.timeout)
            if resp.status_code == 401:
                self.last_error = {"status_code": 401, "error": "naver_auth_failed"}
                logger.warning("Naver Directions 401 Unauthorized — check Maps Client ID/Secret for REST APIs")
                return None
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
        except requests.RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            self.last_error = {"status_code": status_code, "error": "naver_request_failed"}
            logger.warning("Naver Directions request failed: %s", exc)
            return None
        except ValueError:
            self.last_error = {"status_code": None, "error": "naver_invalid_json"}
            logger.warning("Naver Directions invalid JSON")
            return None

        if payload.get("code") not in (0, "0", None):
            self.last_error = {
                "status_code": None,
                "error": "naver_route_error",
                "code": payload.get("code"),
                "message": payload.get("message"),
            }
            logger.info("Naver Directions returned code=%s message=%s", payload.get("code"), payload.get("message"))
            return None
        routes = payload.get("route") or {}
        candidates = routes.get(opt) or routes.get("traoptimal") or routes.get("trafast") or []
        if not candidates:
            return None
        route = candidates[0] or {}
        raw_path = route.get("path") or []
        path: list[dict[str, float]] = []
        for point in raw_path:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                lng = float(point[0])
                lat = float(point[1])
            except (TypeError, ValueError):
                continue
            path.append({"lat": lat, "lng": lng})
        if len(path) < 2:
            return None
        return {
            "option": opt,
            "summary": route.get("summary") or {},
            "path": path,
            "section": route.get("section") or [],
            "guide": route.get("guide") or [],
            "source": "naver_directions5",
        }
