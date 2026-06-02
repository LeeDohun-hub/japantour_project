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

GEOCODE_URL = "https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"


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
    # Flipped to True on first 401 to suppress repeated auth-failure warnings.
    _geocode_auth_failed: bool = False

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: int = 10,
    ):
        self.client_id = (client_id or naver_maps_client_id()).strip()
        self.client_secret = (client_secret or naver_maps_client_secret()).strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id)

    @property
    def can_geocode(self) -> bool:
        return bool(self.client_id and self.client_secret) and not NaverMapsClient._geocode_auth_failed

    def geocode(self, query: str, *, limit: int = 5) -> list[NaverGeocodeResult]:
        q = " ".join(str(query or "").split()).strip()
        if not q:
            return []
        if NaverMapsClient._geocode_auth_failed:
            return []
        if not self.can_geocode:
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
                NaverMapsClient._geocode_auth_failed = True
                id_hint = self.client_id[:6] + "…" if len(self.client_id) > 6 else repr(self.client_id)
                sec_hint = self.client_secret[:4] + "…" if len(self.client_secret) > 4 else repr(self.client_secret)
                logger.warning(
                    "Naver Maps geocode 401 Unauthorized — "
                    "using CLIENT_ID=%s (len=%d) CLIENT_SECRET=%s (len=%d). "
                    "Geocoding disabled for this session.",
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
