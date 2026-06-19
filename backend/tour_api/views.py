from __future__ import annotations

import dataclasses
import html
import json
import logging
import os
import re
import secrets
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)

import requests as http_requests
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.models import User
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.core.cache import cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from tour_api.chat_persistence import (
    get_or_create_chat_session,
    save_chat_turn,
    upsert_traveler_profile,
)
from tour_api.llm_service import get_client, run_chat
from tour_api.models import TravelPlanSnapshot

_FRONTEND: Path = settings.FRONTEND_DIR


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def _google_places_enabled() -> bool:
    return False


def _places_provider() -> str:
    return (os.getenv("PLACES_PROVIDER") or os.getenv("MAPS_PROVIDER") or "").strip().lower()

# ── Rate limiting (캐시 기반, 멀티워커 환경에서도 동작) ──────────────────────
_CHAT_RATE_PER_MIN: int = int(os.environ.get("CHAT_RATE_PER_MIN", "30"))
_CHAT_RATE_PER_DAY: int = int(os.environ.get("CHAT_RATE_PER_DAY", "300"))


def _rl_key(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "anon")
    if request.user.is_authenticated:
        return f"rl_chat_u{request.user.id}"
    return f"rl_chat_{ip}"


def _check_chat_rate(request: HttpRequest) -> "JsonResponse | None":
    key = _rl_key(request)
    min_key = f"{key}_m"
    day_key = f"{key}_d"
    if (cache.get(min_key) or 0) >= _CHAT_RATE_PER_MIN:
        return JsonResponse({"detail": "リクエストが多すぎます。少し待ってからお試しください。"}, status=429)
    if (cache.get(day_key) or 0) >= _CHAT_RATE_PER_DAY:
        return JsonResponse({"detail": "本日の利用上限に達しました。明日またお試しください。"}, status=429)
    cache.set(min_key, (cache.get(min_key) or 0) + 1, timeout=60)
    cache.set(day_key, (cache.get(day_key) or 0) + 1, timeout=86400)
    return None


@require_GET
def api_juso_search(request):
    """행정안전부 도로명주소 검색 — 위저드 숙소·상세주소 (시/도·구 선택 후 목록)."""
    import sys
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.juso_client import (
        is_juso_configured,
        is_juso_eng_configured,
        search_road_addresses,
    )

    keyword = (
        request.GET.get("keyword", "").strip()
        or request.GET.get("q", "").strip()
    )
    if not keyword:
        return JsonResponse({"addresses": [], "error": "keyword_required"})

    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        count = min(max(int(request.GET.get("count", 20)), 1), 100)
    except (TypeError, ValueError):
        count = 20

    addresses, meta = search_road_addresses(keyword, page=page, count_per_page=count)
    payload: dict = {
        "addresses": [
            {
                **a.to_dict(),
                "display_name": a.display_name,
            }
            for a in addresses
        ],
        "total": meta.get("count", len(addresses)),
        "page": page,
        "source": meta.get("source") or "juso",
        "configured": is_juso_configured(),
        "eng_configured": is_juso_eng_configured(),
    }
    if meta.get("error"):
        payload["error"] = meta["error"]
    if meta.get("total_count") is not None:
        payload["total_count"] = meta["total_count"]
    return JsonResponse(payload)


_ACCOM_CAT_KEYWORDS = ("숙박", "호텔", "모텔", "게스트하우스", "펜션", "리조트", "콘도", "민박", "호스텔", "여관", "여인숙", "레지던스")
_PET_HOTEL_WORDS = ("애견", "고양이", "반려", "동물", "펫", "pet", "dog", "cat")


def _is_accom_place(category: str, name: str) -> bool:
    cat = (category or "").lower()
    nm = (name or "").lower()
    for kw in _ACCOM_CAT_KEYWORDS:
        if kw in cat:
            return True
    # 카테고리 없어도 이름에 호텔 단어가 있으면 허용 (단, 애견호텔 제외)
    for kw in ("호텔", "hotel", "리조트", "resort", "게스트하우스", "guesthouse", "모텔", "펜션"):
        if kw in nm:
            for pet in _PET_HOTEL_WORDS:
                if pet in nm:
                    return False
            return True
    # 카테고리가 없거나 빈 경우 통과 (나중에 지도 링크로 확인 가능)
    if not cat:
        return True
    return False


@require_GET
def api_places_search(request):
    """위저드 Step 3 숙박시설 검색 — Naver Local/Maps."""
    import sys
    from pathlib import Path as _P
    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.google_places_client import GooglePlacesClient, KR_LOCATION_RESTRICTION
    from src.api.hotel_area_filter import build_hotel_search_query, filter_hotel_places
    from src.api.naver_maps_client import NaverMapsClient, naver_map_search_url
    from src.api.naver_search_client import NaverSearchClient

    sido = request.GET.get("sido", "").strip()
    sigungu = request.GET.get("sigungu", "").strip()
    query = request.GET.get("q", "").strip()
    if not query and (sido or sigungu):
        query = build_hotel_search_query(sido, sigungu)
    if not query:
        return JsonResponse({"places": []})
    if _is_bad_place_query(query):
        return JsonResponse({"places": [], "total": 0, "filtered_out": 0, "provider": "blocked_bad_query"})
    fetch_all = request.GET.get("all", "").lower() in ("1", "true", "yes")
    try:
        limit = min(max(int(request.GET.get("limit", 5)), 1), 20)
    except (TypeError, ValueError):
        limit = 5
    place_type = request.GET.get("type", "").strip().lower()
    included_type = "hotel" if place_type == "hotel" or sido or sigungu else ""
    provider = _places_provider()
    if provider in ("naver", "naver_maps") or not _google_places_enabled():
        try:
            sclient = NaverSearchClient()
            if sclient.is_configured:
                area_hint = " ".join(x for x in (sido, sigungu) if x).strip()
                scored = sclient.search_places(query, display=limit, area_hint=area_hint)
                if (sido or sigungu) and scored:
                    scored = [p for p in scored if _is_accom_place(p.category or "", p.name or "")]
                places = [
                    {
                        "name": p.name,
                        "address": p.address or "",
                        "maps_url": p.google_maps_uri or p.naver_place_url or "",
                        "google_maps_uri": p.google_maps_uri or p.naver_place_url or "",
                        "rating": None,
                        "user_rating_count": None,
                        "price_level": None,
                        "photo_name": None,
                        "latitude": p.latitude,
                        "longitude": p.longitude,
                        "category": p.category,
                        "source": p.source,
                        "naver_score": p.naver_score,
                        "naver_place_url": p.naver_place_url,
                        "naver_local_link": p.naver_local_link,
                        "blog_review_count": p.blog_review_count,
                        "review_keywords": p.review_keywords or [],
                        "quality_reason": p.quality_reason or "",
                        "photo_url": _naver_place_photo_proxy(
                            p.name, p.latitude, p.longitude,
                            p.mapx or "", p.mapy or "",
                            p.naver_local_link or "", p.naver_place_url or "",
                        ),
                        "mapx": p.mapx or "",
                        "mapy": p.mapy or "",
                    }
                    for p in scored
                ]
                if not any(p.get("latitude") is not None and p.get("longitude") is not None for p in places):
                    nclient = NaverMapsClient()
                    geo_query = query
                    if places and places[0].get("address"):
                        geo_query = str(places[0]["address"])
                    geocoded = nclient.geocode(geo_query, limit=1)
                    if geocoded:
                        g = geocoded[0]
                        if places:
                            places[0]["latitude"] = g.latitude
                            places[0]["longitude"] = g.longitude
                            places[0]["maps_url"] = places[0].get("maps_url") or g.maps_url
                            places[0]["google_maps_uri"] = places[0].get("google_maps_uri") or g.maps_url
                            places[0]["source"] = places[0].get("source") or "naver_search_geocoded"
                        else:
                            places = [{
                                "name": query,
                                "address": g.address or "",
                                "maps_url": g.maps_url,
                                "google_maps_uri": g.maps_url,
                                "rating": None,
                                "user_rating_count": None,
                                "price_level": None,
                                "photo_name": None,
                                "latitude": g.latitude,
                                "longitude": g.longitude,
                                "source": "naver_maps_geocode",
                                "photo_url": f"/api/naver-photo/?url={urllib.parse.quote(g.maps_url)}&q={urllib.parse.quote(query)}&image_fallback=1",
                            }]
                return JsonResponse({
                    "places": places,
                    "total": len(places),
                    "total_before_filter": len(places),
                    "filtered_out": 0,
                    "provider": "naver_search",
                    "note": "Naver quality score uses official Local and Blog Search signals.",
                })

            nclient = NaverMapsClient()
            results = nclient.geocode(query, limit=limit)
            places = [
                {
                    "name": p.name,
                    "address": p.address or "",
                    "maps_url": p.maps_url or naver_map_search_url(query, p.latitude, p.longitude),
                    "rating": None,
                    "user_rating_count": None,
                    "price_level": None,
                    "photo_name": None,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "source": "naver_maps_geocode",
                    "photo_url": f"/api/naver-photo/?url={urllib.parse.quote(p.maps_url or naver_map_search_url(query, p.latitude, p.longitude))}&q={urllib.parse.quote(p.name or query)}&image_fallback=1",
                }
                for p in results
            ]
            if not places and nclient.is_configured:
                places = [{
                    "name": query,
                    "address": "",
                    "maps_url": naver_map_search_url(query),
                    "rating": None,
                    "user_rating_count": None,
                    "price_level": None,
                    "photo_name": None,
                    "latitude": None,
                    "longitude": None,
                    "source": "naver_maps_search_url",
                    "photo_url": f"/api/naver-photo/?url={urllib.parse.quote(naver_map_search_url(query))}&q={urllib.parse.quote(query)}&image_fallback=1",
                }]
            return JsonResponse({
                "places": places,
                "total": len(places),
                "total_before_filter": len(places),
                "filtered_out": 0,
                "provider": "naver_maps",
                "note": "Naver Maps Geocoding fallback result.",
            })
        except Exception as exc:
            logger.warning("api_places_search naver error: %s", exc)
            return JsonResponse({"places": [], "error": str(exc), "provider": "naver_maps"})
    try:
        pclient = GooglePlacesClient()
        if not pclient.is_configured:
            return JsonResponse({"places": [], "error": "Legacy place API not configured"})
        search_kwargs: dict = {
            "text_query": query,
            "language_code": "ja",
            "location_restriction": KR_LOCATION_RESTRICTION,
        }
        if included_type:
            search_kwargs["included_type"] = included_type
        if fetch_all:
            results = pclient.search_by_text_all(max_total=60, **search_kwargs)
            next_token = None
        else:
            results, next_token = pclient.search_by_text(
                max_results=limit, **search_kwargs
            )
        if not results and search_kwargs.get("included_type"):
            search_kwargs.pop("included_type", None)
            if fetch_all:
                results = pclient.search_by_text_all(max_total=60, **search_kwargs)
                next_token = None
            else:
                results, next_token = pclient.search_by_text(
                    max_results=limit, **search_kwargs
                )
        places = [
            {
                "name": p.name,
                "address": p.address or "",
                "maps_url": p.google_maps_uri or "",
                "rating": p.rating,
                "user_rating_count": p.user_rating_count,
                "price_level": p.price_level,
                "photo_name": p.photo_name,
                "latitude": p.latitude,
                "longitude": p.longitude,
            }
            for p in results
        ]
        raw_count = len(places)
        if sido or sigungu:
            places, filtered_out = filter_hotel_places(
                places, sido=sido, sigungu=sigungu
            )
        else:
            filtered_out = 0
        payload: dict = {
            "places": places,
            "total": len(places),
            "total_before_filter": raw_count,
            "filtered_out": filtered_out,
        }
        if next_token:
            payload["next_page_token"] = next_token
        return JsonResponse(payload)
    except Exception as exc:
        logger.warning("api_places_search error: %s", exc)
        return JsonResponse({"places": [], "error": str(exc)})


@require_GET
def api_places_geocode(request):
    """Geocode a raw address/place query with Naver Maps only."""
    import sys
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.naver_maps_client import NaverMapsClient, naver_map_search_url

    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"places": []})
    try:
        limit = min(max(int(request.GET.get("limit", 1)), 1), 5)
    except (TypeError, ValueError):
        limit = 1
    try:
        nclient = NaverMapsClient()
        results = nclient.geocode(query, limit=limit)
        places = [
            {
                "name": p.name or query,
                "address": p.address or "",
                "maps_url": p.maps_url or naver_map_search_url(query, p.latitude, p.longitude),
                "google_maps_uri": p.maps_url or naver_map_search_url(query, p.latitude, p.longitude),
                "latitude": p.latitude,
                "longitude": p.longitude,
                "source": "naver_maps_geocode",
            }
            for p in results
        ]
        return JsonResponse({"places": places, "total": len(places), "provider": "naver_maps"})
    except Exception as exc:
        logger.warning("api_places_geocode error [%r]: %s", query[:80], exc)
        return JsonResponse({"places": [], "error": str(exc), "provider": "naver_maps"})


def _float_query(request: HttpRequest, name: str) -> float | None:
    raw = request.GET.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _is_korean_coord(lat: float | None, lng: float | None) -> bool:
    return (
        lat is not None
        and lng is not None
        and 33.0 <= lat <= 39.5
        and 124.0 <= lng <= 132.0
    )


def _has_japanese_place_text(text: str | None) -> bool:
    value = str(text or "")
    return bool(re.search(r"[\u3040-\u30ff]", value) or (re.search(r"[\u3400-\u9fff]", value) and not re.search(r"[가-힣]", value)))


_BAD_PLACE_QUERY_RE = re.compile(
    r"^(?:곳|장소|지점|스팟|후보|카페|식당|맛집|관광|명소|주변|근처|일대|"
    r"エリア|スポット|場所|カフェ|レストラン|観光|名所)$",
    re.I,
)


def _is_bad_place_query(text: str | None) -> bool:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
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
    if re.search(r"^(?:具体|구체|현지|人気|有名|추천|人気の)?\s*(?:곳|장소|スポット|場所)$", value, re.I):
        return True
    if re.search(r"실제.{0,20}(?:요리점|음식점|식당|레스토랑)", value, re.I):
        return True
    if re.search(r"을\s*사용$", value):
        return True
    return False


@require_GET
def api_maps_driving_route(request):
    """Proxy Naver Directions 5 driving route without exposing server API secret."""
    import sys
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.naver_maps_client import NaverMapsClient

    start_lat = _float_query(request, "start_lat")
    start_lng = _float_query(request, "start_lng")
    goal_lat = _float_query(request, "goal_lat")
    goal_lng = _float_query(request, "goal_lng")
    if not (_is_korean_coord(start_lat, start_lng) and _is_korean_coord(goal_lat, goal_lng)):
        return JsonResponse({"ok": False, "error": "invalid_coordinates"}, status=400)

    # waypoints: "lng,lat|lng,lat|..." (up to 5, Korean coords only)
    raw_waypoints = request.GET.get("waypoints", "").strip()
    waypoints: list[tuple[float, float]] = []
    if raw_waypoints:
        for token in raw_waypoints.split("|")[:5]:
            parts = token.strip().split(",")
            if len(parts) == 2:
                try:
                    wlng, wlat = float(parts[0]), float(parts[1])
                    if _is_korean_coord(wlat, wlng):
                        waypoints.append((wlng, wlat))
                except ValueError:
                    pass

    option = request.GET.get("option", "traoptimal").strip() or "traoptimal"
    lang = request.GET.get("lang", "ja").strip() or "ja"
    wp_key = "|".join(f"{lng:.5f},{lat:.5f}" for lng, lat in waypoints)
    cache_key = (
        "naver_driving_route:"
        f"{round(start_lng, 5)},{round(start_lat, 5)}:"
        f"{round(goal_lng, 5)},{round(goal_lat, 5)}:{option}:{lang}:{wp_key}"
    )
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    client = NaverMapsClient(timeout=10)
    try:
        route = client.driving_route(
            start_lng=float(start_lng),
            start_lat=float(start_lat),
            goal_lng=float(goal_lng),
            goal_lat=float(goal_lat),
            waypoints=waypoints or None,
            option=option,
            lang=lang,
        )
    except Exception as exc:
        logger.warning("api_maps_driving_route error: %s", exc)
        route = None

    if not route:
        last_error = client.last_error or {}
        error = last_error.get("error") or "route_unavailable"
        status = 401 if error == "naver_auth_failed" else 502
        return JsonResponse({
            "ok": False,
            "error": error,
            "provider": "naver_directions5",
            **({"upstream_code": last_error.get("code")} if last_error.get("code") is not None else {}),
        }, status=status)
    payload = {"ok": True, "route": route, "provider": "naver_directions5"}
    cache.set(cache_key, payload, timeout=180)
    return JsonResponse(payload)


@require_GET
def api_maps_transit_route(request):
    """Proxy ODsay public transit route without exposing API key."""
    import sys
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.odsay_client import odsay_api_key, transit_route

    start_lat = _float_query(request, "start_lat")
    start_lng = _float_query(request, "start_lng")
    goal_lat = _float_query(request, "goal_lat")
    goal_lng = _float_query(request, "goal_lng")

    if not (_is_korean_coord(start_lat, start_lng) and _is_korean_coord(goal_lat, goal_lng)):
        return JsonResponse({"ok": False, "error": "invalid_coordinates"}, status=400)

    if not odsay_api_key():
        return JsonResponse({"ok": False, "error": "odsay_not_configured"}, status=503)

    cache_key = (
        "odsay_transit_route:"
        f"{round(float(start_lng), 4)},{round(float(start_lat), 4)}:"
        f"{round(float(goal_lng), 4)},{round(float(goal_lat), 4)}"
    )
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    _odsay_detail: str = ""
    try:
        from src.api.odsay_client import ODsayAuthError
        route = transit_route(
            start_lng=float(start_lng),
            start_lat=float(start_lat),
            goal_lng=float(goal_lng),
            goal_lat=float(goal_lat),
        )
    except ODsayAuthError as exc:
        logger.error("ODsay key authentication failed — key is invalid or expired: %s", exc)
        return JsonResponse({"ok": False, "error": "odsay_auth_failed", "detail": str(exc)}, status=503)
    except Exception as exc:
        logger.warning("api_maps_transit_route error: %s", exc)
        _odsay_detail = str(exc)
        route = None

    if not route:
        logger.warning(
            "ODsay transit route unavailable (%.4f,%.4f)→(%.4f,%.4f) detail=%s",
            float(start_lng), float(start_lat), float(goal_lng), float(goal_lat),
            _odsay_detail or "see odsay_client logs",
        )
        return JsonResponse({"ok": False, "error": "route_unavailable"}, status=502)

    payload = {"ok": True, "route": route, "provider": "odsay"}
    cache.set(cache_key, payload, timeout=3600)
    return JsonResponse(payload)


@require_GET
def api_maps_transit_route_debug(request):
    """Raw ODsay API probe — DEBUG mode only. Returns full response for diagnosis."""
    if not settings.DEBUG:
        return JsonResponse({"detail": "DEBUG mode only"}, status=403)

    import sys
    import requests as rq
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.odsay_client import odsay_api_key

    api_key = odsay_api_key()
    if not api_key:
        return JsonResponse({"ok": False, "error": "ODSAY_API_KEY not set"})

    start_lng = float(_float_query(request, "start_lng") or 126.832)
    start_lat = float(_float_query(request, "start_lat") or 37.6374)
    goal_lng = float(_float_query(request, "goal_lng") or 126.4407)
    goal_lat = float(_float_query(request, "goal_lat") or 37.4602)

    params = {
        "apiKey": api_key,
        "SX": f"{start_lng:.6f}",
        "SY": f"{start_lat:.6f}",
        "EX": f"{goal_lng:.6f}",
        "EY": f"{goal_lat:.6f}",
        "OPT": "0",
        "output": "json",
    }

    try:
        resp = rq.get(
            "https://api.odsay.com/v1/api/searchPubTransPathT",
            params=params,
            timeout=15,
            headers={"Accept": "application/json"},
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:2000]

        masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"
        return JsonResponse({
            "ok": True,
            "key_masked": masked_key,
            "key_len": len(api_key),
            "request_url": resp.url,
            "http_status": resp.status_code,
            "coords": {"start_lng": start_lng, "start_lat": start_lat, "goal_lng": goal_lng, "goal_lat": goal_lat},
            "odsay_response": body,
        })
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)})


@require_POST
def api_places_enrich(request):
    """プラン本文の地図URLを場所詳細（写真・評価等）に変換."""
    import sys
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.google_places_client import GooglePlacesClient, normalize_plan_query_label
    from src.api.naver_maps_client import NaverMapsClient, naver_map_search_url
    from src.api.naver_search_client import NaverSearchClient
    from src.api.region_resolver import address_matches_destination

    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    items = body.get("items")
    if not isinstance(items, list) or len(items) > 24:
        return JsonResponse({"detail": "items must be a list (max 24)"}, status=400)

    lang = body.get("language", "ja")
    if lang not in ("ja", "ko"):
        lang = "ja"

    # 목적지 리전 필터: 지역을 벗어난 장소(예: 강릉 일정에 서울 식당) 제거
    dest_regions: list[str] = body.get("regions") or []
    region_cities: str = str(body.get("region_cities") or "").strip()
    region_city_ids: list[str] = [
        str(x).strip().lower()
        for x in (body.get("region_city_ids") or [])
        if str(x).strip()
    ]
    def _addr_matches_dest(addr: str) -> bool:
        return address_matches_destination(
            addr,
            region_city_ids=region_city_ids,
            dest_regions=dest_regions,
        )

    if _places_provider() in ("naver", "naver_maps") or not _google_places_enabled():
        sclient = NaverSearchClient()
        nclient = NaverMapsClient()
        # "대전・유성구" 형태에서 첫 번째 토큰만 area_hint로 사용 (Naver 검색 정확도)
        _enrich_area_hint = re.split(r"[・,、/\s]+", region_cities.strip())[0].strip() if region_cities else ""
        enriched: dict[str, dict] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            query = normalize_plan_query_label(str(raw.get("query") or ""))
            if not url:
                continue
            if not query:
                # Naver search URL: extract term from path so enrich can still run
                m = re.search(r"/search/([^?#]+)", url)
                if m:
                    query = urllib.parse.unquote_plus(m.group(1)).strip()
            if not query:
                continue
            if _is_bad_place_query(query):
                continue
            scored = sclient.search_places(query, display=1, area_hint=_enrich_area_hint) if sclient.is_configured else []
            if scored:
                p = scored[0]
                if p.address and not _addr_matches_dest(p.address):
                    continue
                name_ja = query if _has_japanese_place_text(query) and query != p.name else ""
                enriched[url] = {
                    "name": p.name,
                    **({"name_ja": name_ja} if name_ja else {}),
                    "category": p.category,
                    "address": p.address,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "rating": None,
                    "user_rating_count": None,
                    "google_maps_uri": p.google_maps_uri or p.naver_place_url,
                    "maps_url": p.google_maps_uri or p.naver_place_url,
                    "is_open_now": None,
                    "distance_meters": None,
                    "place_id": None,
                    "price_level": None,
                    "photo_name": None,
                    "search_area": region_cities,
                    "source": p.source,
                    "naver_score": p.naver_score,
                    "naver_place_url": p.naver_place_url,
                    "naver_local_link": p.naver_local_link,
                    "blog_review_count": p.blog_review_count,
                    "review_keywords": p.review_keywords or [],
                    "quality_reason": p.quality_reason or "",
                    "photo_url": _naver_place_photo_proxy(
                        p.name, p.latitude, p.longitude,
                        p.mapx or "", p.mapy or "",
                        p.naver_local_link or "", p.naver_place_url or "",
                    ),
                    "mapx": p.mapx or "",
                    "mapy": p.mapy or "",
                }
                continue

            found = nclient.geocode(query, limit=1)
            if found:
                p = found[0]
                if p.address and not _addr_matches_dest(p.address):
                    continue
                name_ja = query if _has_japanese_place_text(query) else ""
                enriched[url] = {
                    "name": query,
                    **({"name_ja": name_ja} if name_ja else {}),
                    "category": "",
                    "address": p.address,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "rating": None,
                    "user_rating_count": None,
                    "google_maps_uri": p.maps_url,
                    "maps_url": p.maps_url,
                    "is_open_now": None,
                    "distance_meters": None,
                    "place_id": None,
                    "price_level": None,
                    "photo_name": None,
                    "search_area": "",
                    "source": "naver_maps_geocode",
                    "photo_url": f"/api/naver-photo/?url={urllib.parse.quote(p.maps_url)}&q={urllib.parse.quote(query)}&image_fallback=1",
                }
            elif nclient.is_configured:
                maps_url = naver_map_search_url(query)
                enriched[url] = {
                    "name": query,
                    "category": "",
                    "address": "",
                    "latitude": None,
                    "longitude": None,
                    "rating": None,
                    "user_rating_count": None,
                    "google_maps_uri": maps_url,
                    "maps_url": maps_url,
                    "is_open_now": None,
                    "distance_meters": None,
                    "place_id": None,
                    "price_level": None,
                    "photo_name": None,
                    "search_area": "",
                    "source": "naver_maps_search_url",
                    "photo_url": f"/api/naver-photo/?url={urllib.parse.quote(maps_url)}&q={urllib.parse.quote(query)}&image_fallback=1",
                }
        return JsonResponse({"places": enriched, "provider": "naver_maps"})

    try:
        pclient = GooglePlacesClient()
        if not pclient.is_configured:
            return JsonResponse({"places": {}, "error": "Legacy place API not configured"})
    except Exception as exc:
        return JsonResponse({"places": {}, "error": str(exc)})

    _NON_KR = (
        "japan", "日本", "일본",
        "tokyo", "東京", "도쿄", "도쿄도",
        "osaka", "大阪", "오사카",
        "kyoto", "京都", "교토",
        "china", "中国", "中國", "beijing", "北京", "shanghai", "上海",
        "taiwan", "台湾", "台灣",
        "〒", "신주쿠구", "시부야구",
    )

    def _is_korea(addr: str) -> bool:
        a = addr.lower()
        return not any(m.lower() in a for m in _NON_KR)

    enriched: dict[str, dict] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        query = normalize_plan_query_label(str(raw.get("query") or ""))
        if not url:
            continue
        try:
            place = pclient.find_for_plan_item(
                url, query, language_code=lang, region_hint=region_cities,
            )
            if place:
                addr = place.address or ""
                if not _is_korea(addr):
                    logger.debug("enrich: dropped non-KR place %r addr=%r", place.name, addr)
                    continue
                if not _addr_matches_dest(addr):
                    logger.debug("enrich: dropped out-of-region place %r addr=%r dest=%r", place.name, addr, dest_regions)
                    continue
                enriched[url] = dataclasses.asdict(place)
        except Exception as exc:
            logger.warning("places enrich failed for %r: %s", url[:80], exc)

    return JsonResponse({"places": enriched})


@require_GET
def api_places_debug(request):
    """Legacy place debug endpoint. Disabled while Naver place mode is active."""
    from django.conf import settings as _settings
    if not _settings.DEBUG:
        return JsonResponse({"detail": "DEBUG mode only"}, status=403)

    query = request.GET.get("q", "명동 호텔")
    itype = request.GET.get("type", "hotel")
    api_key = os.getenv("GOOGLE_HOTELS_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")

    result: dict = {
        "query": query,
        "included_type": itype,
        "api_key_set": bool(api_key),
        "api_key_prefix": (api_key[:12] + "...") if api_key else None,
    }

    if not api_key:
        result["error"] = "no API key configured"
        return JsonResponse(result)

    import requests as _req
    url = "https://places.googleapis.com/v1/places:searchText"
    body: dict = {
        "textQuery": query,
        "maxResultCount": 3,
        "languageCode": "ko",
        "regionCode": "KR",
    }
    if itype:
        body["includedType"] = itype

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.formattedAddress,places.googleMapsUri,places.starRating",
    }

    try:
        resp = _req.post(url, json=body, headers=headers, timeout=10)
        result["http_status"] = resp.status_code
        result["response"] = resp.json()
    except Exception as exc:
        result["error"] = str(exc)

    return JsonResponse(result)


@require_GET
def api_maps_config(request):
    """Naver Maps JavaScript API key for the browser map."""
    from src.api.naver_maps_client import naver_maps_client_id

    naver_key = naver_maps_client_id()
    if naver_key:
        return JsonResponse({
            "enabled": True,
            "provider": "naver",
            "api_key": naver_key,
            "source": "NAVER_MAPS_CLIENT_ID",
            "browser_note": "Naver Maps JavaScript API key.",
        })

    return JsonResponse({
        "enabled": False,
        "provider": "naver",
        "api_key": "",
        "source": "",
        "browser_note": "NAVER_MAPS_CLIENT_ID is required for the browser map.",
    })


_NAVER_PHOTO_ALLOWED_DOMAINS = frozenset({
    "map.naver.com",
    "m.place.naver.com",
    "pcmap.place.naver.com",
    "search.pstatic.net",
    "ldb-phinf.pstatic.net",
    "apis.naver.com",
})
_NAVER_DIRECT_PHOTO_DOMAINS = frozenset({
    "search.pstatic.net",
    "ldb-phinf.pstatic.net",
    "apis.naver.com",
})
_NAVER_PLACE_ID_RE = re.compile(r"/place/(\d+)")
_NAVER_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://map.naver.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}
NAVER_IMAGE_SEARCH_URL = "https://openapi.naver.com/v1/search/image"
_KOREAN_ADDR_SPLIT_RE = re.compile(
    r"\s+(?:"
    r"서울특별시|서울시|부산광역시|부산시|대구광역시|대구시|인천광역시|인천시|"
    r"광주광역시|광주시|대전광역시|대전시|울산광역시|울산시|세종특별자치시|세종시|"
    r"경기도|강원특별자치도|강원도|충청북도|충북|충청남도|충남|전북특별자치도|전라북도|전북|"
    r"전라남도|전남|경상북도|경북|경상남도|경남|제주특별자치도|제주도"
    r")\s+"
)


def _is_probable_naver_place_photo(url: str) -> bool:
    lower = (url or "").lower()
    if not lower.startswith("http"):
        return False
    if any(x in lower for x in ("favicon", "/assets/", "sp_map", "logo", "marker", "sprite")):
        return False
    return any(
        x in lower
        for x in (
            "ldb-phinf",
            "search.pstatic.net/common",
            "apis.naver.com/place/panorama/thumbnail",
            "postfiles.pstatic",
            "blogthumb",
        )
    )


def _normalize_direct_naver_photo_url(url: str) -> str:
    """Return a direct/proxy Naver photo URL, decoding search.pstatic src= when useful."""
    raw = html.unescape(str(url or "").strip()).replace("\\/", "/")
    parsed = urllib.parse.urlparse(raw)
    if parsed.netloc.lower() == "search.pstatic.net":
        src = urllib.parse.parse_qs(parsed.query).get("src", [""])[0]
        decoded = urllib.parse.unquote(src).strip()
        if "apis.naver.com/place/panorama/thumbnail" in decoded.lower():
            return raw
        if _is_probable_naver_place_photo(decoded):
            return decoded
    return raw


def _parse_naver_place_photo(raw_html: str) -> str | None:
    """Extract a place exterior photo URL from Naver HTML using multiple strategies."""
    # Normalize JSON-encoded forward slashes (\/) common in embedded script data
    normalized = raw_html.replace("\\/", "/")
    text = html.unescape(urllib.parse.unquote(normalized))

    # Strategy 1: og:image (set server-side, most reliable)
    for pat in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    ):
        m = re.search(pat, text, re.I)
        if m:
            candidate = html.unescape(m.group(1)).strip()
            if _is_probable_naver_place_photo(candidate):
                return candidate

    # Strategy 2: search.pstatic.net/common proxy — decode src= param → ldb-phinf direct URL
    # (appears in pcmap list-page thumbnails: <img src="https://search.pstatic.net/common/?...src=ldb-phinf...">)
    _first_proxy: str | None = None
    for m in re.finditer(r"https://search\.pstatic\.net/common/\?[^\s\"'<>]+", text):
        proxy_url = m.group(0)
        if _first_proxy is None:
            _first_proxy = proxy_url
        src_m = re.search(r"[?&]src=([^&\s\"'<>]+)", proxy_url)
        if src_m:
            decoded = urllib.parse.unquote(src_m.group(1))
            if "apis.naver.com/place/panorama/thumbnail" in decoded.lower():
                return proxy_url
            if _is_probable_naver_place_photo(decoded):
                return decoded  # direct ldb-phinf URL (higher quality)
    if _first_proxy:
        return _first_proxy  # proxy URL as fallback if src= decode failed

    # Strategy 3: direct ldb-phinf.pstatic.net URLs
    m = re.search(r"(https://ldb-phinf\.pstatic\.net/[^\s\"'<>\\]+\.(?:jpg|jpeg|png|webp))", text, re.I)
    if m:
        return m.group(1)

    # Strategy 4: broad pstatic/naver image scan (search normalized and raw)
    candidates: list[str] = []
    for pat in (
        r"https?://[^\s\"'\\<>]+pstatic[^\s\"'\\<>]+\.(?:jpg|jpeg|png|webp)",
        r"https?%3A%2F%2F[^\s\"'\\<>]+pstatic[^\s\"'\\<>]+?\.(?:jpg|jpeg|png|webp)",
    ):
        candidates += re.findall(pat, normalized, re.I)
        candidates += re.findall(pat, raw_html, re.I)
    for cand in candidates:
        img = urllib.parse.unquote(html.unescape(cand)).replace("\\/", "/")
        img = img.split("&quot;")[0].split("\\u0026")[0]
        if not _is_probable_naver_place_photo(img):
            continue
        return img

    return None


def _naver_search_headers() -> dict[str, str] | None:
    client_id = (os.getenv("NAVER_SEARCH_CLIENT_ID") or os.getenv("NAVER_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("NAVER_SEARCH_CLIENT_SECRET") or os.getenv("NAVER_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return None
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Accept": "application/json",
    }


def _photo_query_variants(query: str) -> list[str]:
    """Return progressively broader Naver image-search queries."""
    raw = " ".join(str(query or "").split()).strip()
    if not raw:
        return []

    variants: list[str] = []

    def add(value: str) -> None:
        value = " ".join(str(value or "").split()).strip(" -_/|,")
        if value and value not in variants:
            variants.append(value)

    add(raw)

    # Frontend often sends "place name + full address". Naver image search is
    # much more reliable when retried with only the place name.
    no_addr = _KOREAN_ADDR_SPLIT_RE.split(raw, 1)[0]
    add(no_addr)

    # If an address keyword was not present, trim obvious trailing road/lot/floor
    # fragments without touching normal branch names such as "강남점".
    no_detail = re.sub(
        r"\s+\S*(?:로|길|대로)\d*(?:번길)?(?:\s+\d+[^\s]*)?.*$",
        "",
        no_addr,
    )
    add(no_detail)

    tokens = no_addr.split()
    if len(tokens) > 2:
        add(" ".join(tokens[:2]))
    if len(tokens) > 1:
        add(tokens[0])

    return variants[:5]


def _image_candidate_score(url: str) -> int:
    lower = (url or "").lower()
    if not lower.startswith("http"):
        return -1
    if any(x in lower for x in ("favicon", "logo", "sprite")):
        return -1
    if "ldb-phinf.pstatic.net" in lower:
        return 100
    if "search.pstatic.net/common" in lower and "ldb-phinf" in lower:
        return 90
    if "apis.naver.com/place/panorama/thumbnail" in lower:
        return 80
    if "blogthumb" in lower or "postfiles.pstatic" in lower:
        return 50
    if "imgnews.naver.net" in lower:
        return 10
    return 20


def _fetch_naver_image_search_photo(query: str) -> str | None:
    headers = _naver_search_headers()
    if not query:
        return None
    if not headers:
        logger.debug("Naver image search skipped: NAVER_SEARCH_CLIENT_ID/SECRET not configured")
        return None
    best_candidate: tuple[int, str] | None = None
    for search_query in _photo_query_variants(query):
        try:
            resp = http_requests.get(
                NAVER_IMAGE_SEARCH_URL,
                params={"query": search_query, "display": 10, "sort": "sim", "filter": "all"},
                headers=headers,
                timeout=8,
            )
            resp.raise_for_status()
            items = resp.json().get("items") or []
        except (http_requests.RequestException, ValueError) as exc:
            logger.warning("Naver image search failed [%r]: %s", search_query[:80], exc)
            continue

        candidates: list[tuple[int, str]] = []
        for item in items:
            for key in ("thumbnail", "link"):
                candidate = html.unescape(str(item.get(key) or "")).strip()
                candidate = _normalize_direct_naver_photo_url(candidate)
                score = _image_candidate_score(candidate)
                if score >= 0:
                    candidates.append((score, candidate))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            top = candidates[0]
            if best_candidate is None or top[0] > best_candidate[0]:
                best_candidate = top
            if top[0] >= 90:
                return top[1]
    return best_candidate[1] if best_candidate else None


def _naver_place_photo_proxy(
    name: str,
    lat,
    lng,
    mapx: str = "",
    mapy: str = "",
    local_link: str = "",
    place_url: str = "",
) -> str:
    """Build /api/naver-photo/ URL for a NaverPlace result.

    Always includes q= (place name), but keeps image search fallback disabled by
    default so unrelated web images are not shown as place exterior photos.
    """
    _lat, _lng = lat, lng
    if _lat is None or _lng is None:
        try:
            rx, ry = float(mapx or 0), float(mapy or 0)
            if rx > 10_000 and ry > 10_000:
                _lng, _lat = rx / 1e7, ry / 1e7
        except (TypeError, ValueError):
            pass
    name_q = f"&q={urllib.parse.quote(name)}" if name else ""

    # Prefer individual place page (/place/{id}/home) when we have a place ID —
    # these pages have og:image set server-side, unlike list pages which require JS.
    for link in (local_link, place_url):
        if not link:
            continue
        pid_m = re.search(r"/place/(\d+)", link)
        if pid_m:
            individual = f"https://pcmap.place.naver.com/place/{pid_m.group(1)}/home"
            return f"/api/naver-photo/?url={urllib.parse.quote(individual)}{name_q}"

    if name and _lat is not None and _lng is not None:
        pcmap = (
            f"https://pcmap.place.naver.com/place/list"
            f"?query={urllib.parse.quote(name)}"
            f"&x={_lng:.7f}&y={_lat:.7f}&display=3"
        )
        return f"/api/naver-photo/?url={urllib.parse.quote(pcmap)}{name_q}"
    src = local_link or place_url or ""
    return f"/api/naver-photo/?url={urllib.parse.quote(src)}{name_q}" if src else ""


@require_GET
def api_naver_photo(request):
    """Best-effort Naver Map place-photo proxy.

    Accepts pcmap.place.naver.com list URLs (SSR, search.pstatic.net thumbnails)
    and map.naver.com place URLs (og:image strategy). Falls back gracefully to 404.
    """
    raw_url = (request.GET.get("url") or "").strip()
    query = (request.GET.get("q") or request.GET.get("name") or "").strip()
    allow_image_fallback = str(request.GET.get("image_fallback") or "").lower() in ("1", "true", "yes")
    lat = lng = None
    try:
        lat = float(request.GET.get("lat") or "")
        lng = float(request.GET.get("lng") or "")
    except (TypeError, ValueError):
        lat = lng = None
    if not raw_url and query:
        raw_url = "https://pcmap.place.naver.com/place/list?query=" + urllib.parse.quote(query)
        if lat is not None and lng is not None:
            raw_url += f"&x={lng:.7f}&y={lat:.7f}&display=5"
        else:
            raw_url += "&display=5"
    if not raw_url:
        return JsonResponse({"detail": "url or q required"}, status=400)
    parsed = urllib.parse.urlparse(raw_url)
    netloc = parsed.netloc.lower()
    if parsed.scheme not in ("http", "https") or netloc not in _NAVER_PHOTO_ALLOWED_DOMAINS:
        return JsonResponse({"detail": "only Naver map URLs are allowed"}, status=400)
    if not query and "/p/search/" in parsed.path:
        query = urllib.parse.unquote(parsed.path.split("/p/search/", 1)[1].split("/", 1)[0]).strip()

    stable_key = (
        "naver_photo_url5:"
        + ("img1:" if allow_image_fallback else "strict:")
        + re.sub(r"\W+", "_", f"{raw_url}|{query}")[:220]
    )
    cached = cache.get(stable_key)
    if cached:
        return redirect(cached)

    photo_url: str | None = None

    if netloc in _NAVER_DIRECT_PHOTO_DOMAINS and _is_probable_naver_place_photo(raw_url):
        photo_url = _normalize_direct_naver_photo_url(raw_url)
        cache.set(stable_key, photo_url, timeout=86400)
        return redirect(photo_url)

    if netloc == "pcmap.place.naver.com":
        # pcmap list pages no longer include thumbnail URLs in SSR HTML (loaded via JS).
        # Only attempt scraping for individual place pages (/place/{id}/).
        is_list_page = "/place/list" in parsed.path
        if not is_list_page:
            try:
                resp = http_requests.get(raw_url, headers=_NAVER_FETCH_HEADERS, timeout=6)
                resp.raise_for_status()
                photo_url = _parse_naver_place_photo(resp.text)
            except http_requests.RequestException as exc:
                logger.warning("Naver photo pcmap fetch failed [%s]: %s", raw_url[:120], exc)
    else:
        # map.naver.com — try pcmap individual page via place ID first (og:image strategy)
        place_id_m = _NAVER_PLACE_ID_RE.search(raw_url)
        if not place_id_m and query:
            # pcmap list pages don't have SSR thumbnails; skip to image fallback
            pass
        if place_id_m:
            place_id = place_id_m.group(1)
            for fetch_url in (
                f"https://pcmap.place.naver.com/place/{place_id}/home",
                f"https://map.naver.com/p/entry/place/{place_id}",
            ):
                try:
                    resp = http_requests.get(fetch_url, headers=_NAVER_FETCH_HEADERS, timeout=8)
                    resp.raise_for_status()
                    photo_url = _parse_naver_place_photo(resp.text)
                    if photo_url:
                        break
                except http_requests.RequestException:
                    continue

        # Fallback: original URL with placePath=/photo
        if not photo_url:
            fallback = raw_url
            if "placePath=/photo" not in fallback:
                joiner = "&" if "?" in fallback else "?"
                fallback = f"{fallback}{joiner}placePath=/photo"
            try:
                resp = http_requests.get(fallback, headers=_NAVER_FETCH_HEADERS, timeout=8)
                resp.raise_for_status()
                photo_url = _parse_naver_place_photo(resp.text)
            except http_requests.RequestException as exc:
                logger.warning("Naver photo fetch failed [%s]: %s", raw_url[:120], exc)

    if not photo_url and allow_image_fallback:
        if query:
            photo_url = _fetch_naver_image_search_photo(query)

    if not photo_url:
        logger.debug("Naver photo: no photo found for %s", raw_url[:120])
        return JsonResponse({"detail": "no naver photo found"}, status=404)

    cache.set(stable_key, photo_url, timeout=86400)
    return redirect(photo_url)


@require_GET
def api_photo(request):
    """Legacy place photo proxy. Disabled while Naver place mode is active."""
    if not _google_places_enabled():
        return JsonResponse({"detail": "Legacy place photos disabled"}, status=404)

    name = request.GET.get("name", "").strip()
    if not name or not name.startswith("places/"):
        return JsonResponse({"detail": "invalid name"}, status=400)

    api_key = os.getenv("GOOGLE_HOTELS_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return JsonResponse({"detail": "API key not configured"}, status=503)

    photo_url = f"https://places.googleapis.com/v1/{name}/media"
    try:
        resp = http_requests.get(
            photo_url,
            params={"maxWidthPx": 400, "key": api_key},
            timeout=10,
            allow_redirects=True,
        )
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg")
        response = HttpResponse(resp.content, content_type=content_type)
        response["Cache-Control"] = "public, max-age=86400"
        return response
    except Exception:
        return JsonResponse({"detail": "photo fetch failed"}, status=502)


def _norm_iata(code: str | None) -> str:
    return (code or "").strip().upper()


def _dedupe_flight_dicts(flight_dicts: list[dict]) -> list[dict]:
    """API 원본 행 중복 제거 (동일 편명·時刻·코드쉐어)."""
    seen: dict[tuple, dict] = {}
    for f in flight_dicts:
        key = (
            _norm_iata(f.get("flight_iata")),
            f.get("dep_scheduled") or "",
            f.get("arr_scheduled") or "",
            _norm_iata(f.get("codeshared_iata")),
        )
        if not key[0]:
            continue
        prev = seen.get(key)
        if prev is None:
            seen[key] = f
        elif not f.get("codeshared_iata") and prev.get("codeshared_iata"):
            seen[key] = f
    return list(seen.values())


def _dedupe_display_flights(flight_dicts: list[dict]) -> list[dict]:
    """표시용 1카드 = 편명 + 출발·도착 시각 (slave 통합 후)."""
    seen: dict[tuple, dict] = {}
    for f in flight_dicts:
        key = (
            _norm_iata(f.get("flight_iata")),
            f.get("dep_scheduled") or "",
            f.get("arr_scheduled") or "",
        )
        if not key[0]:
            continue
        prev = seen.get(key)
        if prev is None:
            seen[key] = f
        else:
            aliases = sorted(
                set(prev.get("codeshare_aliases") or [])
                | set(f.get("codeshare_aliases") or [])
            )
            seen[key] = {**prev, "codeshare_aliases": aliases}
    return list(seen.values())


def _merge_codeshares(flight_dicts: list[dict]) -> list[dict]:
    """코드쉐어 slave 편을 master 편에 통합하여 중복 제거.

    codeshared_iata 가 있으면 slave, 없으면 master.
    slave는 master의 codeshare_aliases 리스트에 편명만 추가하고 제거.
    master가 목록에 없는 경우 slave는 1건만 유지 (_dedupe_flight_dicts).
    """
    from collections import defaultdict

    flight_dicts = _dedupe_flight_dicts(flight_dicts)
    master_iatas = {
        _norm_iata(f.get("flight_iata"))
        for f in flight_dicts
        if not _norm_iata(f.get("codeshared_iata"))
    }
    slave_aliases: dict[str, list[str]] = defaultdict(list)
    for f in flight_dicts:
        master = _norm_iata(f.get("codeshared_iata"))
        if master and master in master_iatas:
            alias = _norm_iata(f.get("flight_iata"))
            if alias and alias not in slave_aliases[master]:
                slave_aliases[master].append(alias)

    result = []
    for f in flight_dicts:
        master = _norm_iata(f.get("codeshared_iata"))
        if master and master in master_iatas:
            continue
        iata = _norm_iata(f.get("flight_iata"))
        result.append({**f, "codeshare_aliases": slave_aliases.get(iata, [])})
    return _dedupe_display_flights(result)


def _flight_dep_sort_key(f: dict) -> tuple[int, str]:
    """출발 시각 오름차순 (HH:MM)."""
    raw = (f.get("dep_scheduled") or f.get("arr_scheduled") or "99:99").strip()
    try:
        h, m = raw.split(":", 1)
        return int(h) * 60 + int(m), raw
    except (ValueError, AttributeError):
        return 9999, raw


@require_GET
def api_flights(request):
    """노선·날짜별 항공편 목록 (마법사 Step 2: 到着便·帰国便 공용)."""
    import dataclasses, sys
    from pathlib import Path as _P
    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))
    from api.aviation_client import search_route_flights

    dep_iata    = (request.GET.get("dep") or "").upper() or None
    arr_iata    = (request.GET.get("arr") or "ICN").upper()
    flight_date = request.GET.get("date") or None
    if not dep_iata:
        return JsonResponse({"error": "dep is required"}, status=400)

    cache_key = f"flights:{dep_iata}:{arr_iata}:{flight_date}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    try:
        flights, warning, source = search_route_flights(
            dep_iata, arr_iata, flight_date=flight_date, limit=999
        )
        flight_dicts = [dataclasses.asdict(f) for f in flights]
        merged = _merge_codeshares(flight_dicts)
        merged.sort(key=_flight_dep_sort_key)
        payload: dict = {
            "flights": merged,
            "source": source,
        }
        if warning:
            payload["warning"] = warning
        cache.set(cache_key, payload, timeout=300)
        return JsonResponse(payload)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@require_GET
def api_health(request):
    return JsonResponse(
        {
            "ok": True,
            "openai_configured": get_client() is not None,
            "vector_backend": getattr(settings, "VECTOR_BACKEND", "faiss"),
            "database_engine": settings.DATABASES["default"]["ENGINE"],
        }
    )


def _session_key(request: HttpRequest) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def _latest_plan_snapshot(request: HttpRequest) -> TravelPlanSnapshot | None:
    qs = TravelPlanSnapshot.objects.all()
    if request.user.is_authenticated:
        snap = qs.filter(user=request.user).first()
        if snap:
            return snap
    key = request.session.session_key
    if key:
        return qs.filter(session_key=key).first()
    return None


def _chat_profile_from_snapshot(snapshot: TravelPlanSnapshot | None) -> dict | None:
    if not snapshot or not isinstance(snapshot.profile, dict):
        return None
    profile = dict(snapshot.profile)
    # 플랜 생성 전용 키 제거
    for key in (
        "plan_mode",
        "plan_reroll",
        "plan_variant_seed",
        "avoid_place_names",
        "plan_auto_defaults",
        "days",
        "nights",
    ):
        profile.pop(key, None)
    # 지역 관련 키 제거 — 챗봇 일반 질문에서 저장된 이전 여행지가
    # VisitKorea·KOPIS·Naver 검색의 지역 필터를 오염시키는 것을 방지.
    # 지역은 사용자의 현재 메시지에서 _infer_legacy_area_code 등으로 추론함.
    for key in (
        "regions",
        "regionAreaKeys",
        "regionCities",
        "regionCitiesOther",
        "accommodation",
    ):
        profile.pop(key, None)
    return profile


def _format_plan_snapshot_context(snapshot: TravelPlanSnapshot | None) -> str:
    if not snapshot:
        return ""
    profile = snapshot.profile if isinstance(snapshot.profile, dict) else {}
    parts: list[str] = []
    if snapshot.title:
        parts.append(f"Title: {snapshot.title}")
    days = profile.get("days")
    nights = profile.get("nights")
    if nights or days:
        parts.append(f"Trip length: {nights or '?'} nights / {days or '?'} days")
    regions = profile.get("regions") or []
    if regions:
        parts.append(f"Regions: {', '.join(map(str, regions[:3]))}")
    city = profile.get("regionCities") or profile.get("regionCitiesOther")
    if city:
        parts.append(f"Selected city/district: {city}")
    activities = profile.get("activities") or []
    if activities:
        parts.append(f"Interests: {', '.join(map(str, activities[:8]))}")
    add = profile.get("additional") or {}
    if isinstance(add, dict):
        prefs = add.get("foodPreferences") or []
        avoid = add.get("foodAvoid") or []
        styles = add.get("travelStyles") or []
        if prefs:
            parts.append(f"Food preferences: {', '.join(map(str, prefs[:8]))}")
        if avoid:
            parts.append(f"Food restrictions/avoid: {', '.join(map(str, avoid[:8]))}")
        if styles:
            parts.append(f"Travel styles: {', '.join(map(str, styles[:8]))}")
    budget = profile.get("budget") or {}
    if isinstance(budget, dict) and budget.get("total"):
        parts.append(
            f"Budget: {budget.get('currency') or ''} {budget.get('total')}"
            + (f" / daily {budget.get('daily')}" if budget.get("daily") else "")
        )
    plan_text = " ".join(str(snapshot.plan_text or "").split())
    if plan_text:
        parts.append(f"Latest generated plan excerpt: {plan_text[:1800]}")
    if not parts:
        return ""
    return (
        "[Recent Plan Context]\n"
        + "\n".join(f"- {p}" for p in parts)
        + "\nUse this only when it helps answer follow-up questions about the user's trip. "
        "Do not expose private account identifiers or say this context came from storage."
    )


def _should_attach_recent_plan_context(message: str) -> bool:
    text = (message or "").lower()
    if not text.strip():
        return False
    markers = (
        "내 플랜", "내 일정", "저장된", "저장 플랜", "방금", "아까", "위 플랜",
        "여행플랜", "여행 플랜", "몇일차", "며칠차", "일차", "수정", "불러온",
        "このプラン", "保存済み", "保存プラン", "さっき", "先ほど", "日目",
        "旅程", "旅行プラン", "修正", "読み込んだ",
    )
    return any(m in text for m in markers)


def _with_recent_plan_context(message: str, snapshot: TravelPlanSnapshot | None) -> str:
    if not _should_attach_recent_plan_context(message):
        return message
    context = _format_plan_snapshot_context(snapshot)
    if not context:
        return message
    return f"{context}\n\n[User Question]\n{message}"


_PLAN_SHARE_SIGNER = TimestampSigner(salt="travel-plan-share")


def _plan_share_token(snapshot_id: int) -> str:
    return urllib.parse.quote(_PLAN_SHARE_SIGNER.sign(str(snapshot_id)), safe="")


def _snapshot_from_share_token(token: str) -> TravelPlanSnapshot | None:
    try:
        raw = urllib.parse.unquote(token or "")
        snapshot_id = int(_PLAN_SHARE_SIGNER.unsign(raw, max_age=60 * 60 * 24 * 90))
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    return TravelPlanSnapshot.objects.filter(id=snapshot_id).first()


def _plan_snapshot_queryset_for_request(request: HttpRequest):
    qs = TravelPlanSnapshot.objects.all()
    if request.user.is_authenticated:
        return qs.filter(user=request.user)
    key = request.session.session_key
    if not key:
        return qs.none()
    return qs.filter(user=None, session_key=key)


def _serialize_plan_snapshot(snapshot: TravelPlanSnapshot, request: HttpRequest, *, detail: bool = False) -> dict:
    token = _plan_share_token(snapshot.id)
    profile = snapshot.profile if isinstance(snapshot.profile, dict) else {}
    metadata = snapshot.metadata if isinstance(snapshot.metadata, dict) else {}
    payload = {
        "id": snapshot.id,
        "title": snapshot.title or "韓国旅行プラン",
        "created_at": snapshot.created_at.isoformat(),
        "updated_at": snapshot.updated_at.isoformat(),
        "days": profile.get("days") or "",
        "nights": profile.get("nights") or "",
        "regions": profile.get("regionCities") or profile.get("regionCitiesOther") or profile.get("regions") or "",
        "share_url": request.build_absolute_uri(f"/share/plan/{token}/"),
    }
    if detail:
        payload.update({
            "profile": profile,
            "plan_text": snapshot.plan_text or "",
            "places": snapshot.places if isinstance(snapshot.places, list) else [],
            "metadata": metadata,
        })
    else:
        text = " ".join(str(snapshot.plan_text or "").split())
        payload["excerpt"] = text[:160]
    return payload


@require_POST
def api_plan_snapshot(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    profile = body.get("profile")
    plan_text = body.get("plan_text")
    places = body.get("places") or []
    metadata = body.get("metadata") or {}
    title = str(body.get("title") or "").strip()[:255]
    snapshot_id = body.get("snapshot_id")

    if not isinstance(profile, dict):
        return JsonResponse({"detail": "profile must be an object"}, status=400)
    if not isinstance(plan_text, str) or not plan_text.strip():
        return JsonResponse({"detail": "plan_text is required"}, status=400)
    if not isinstance(places, list):
        places = []
    if not isinstance(metadata, dict):
        metadata = {}

    session_key = _session_key(request)
    user = request.user if request.user.is_authenticated else None
    defaults = {
        "session_key": session_key,
        "title": title,
        "profile": profile,
        "plan_text": plan_text[:30000],
        "places": places[:80],
        "metadata": metadata,
    }
    snapshot = None
    if snapshot_id:
        try:
            snapshot = _plan_snapshot_queryset_for_request(request).filter(id=int(snapshot_id)).first()
        except (TypeError, ValueError):
            snapshot = None

    if snapshot:
        for field, value in defaults.items():
            setattr(snapshot, field, value)
        snapshot.save()
    elif user:
        snapshot = TravelPlanSnapshot.objects.create(
            user=user,
            **defaults,
        )
    else:
        snapshot = TravelPlanSnapshot.objects.create(
            user=None,
            **defaults,
        )
    token = _plan_share_token(snapshot.id)
    return JsonResponse({
        "ok": True,
        "snapshot_id": snapshot.id,
        "share_url": request.build_absolute_uri(f"/share/plan/{token}/"),
    })


@require_http_methods(["GET", "DELETE"])
def api_plan_snapshots(request):
    snapshots = _plan_snapshot_queryset_for_request(request)
    if request.method == "DELETE":
        count = snapshots.count()
        snapshots.delete()
        return JsonResponse({"ok": True, "deleted": count})
    return JsonResponse({
        "plans": [
            _serialize_plan_snapshot(snapshot, request, detail=False)
            for snapshot in snapshots[:50]
        ],
        "authenticated": request.user.is_authenticated,
    })


@require_http_methods(["GET", "DELETE"])
def api_plan_snapshot_detail(request, snapshot_id: int):
    snapshot = _plan_snapshot_queryset_for_request(request).filter(id=snapshot_id).first()
    if not snapshot:
        return JsonResponse({"detail": "plan not found"}, status=404)
    if request.method == "DELETE":
        snapshot.delete()
        return JsonResponse({"ok": True})
    return JsonResponse({
        "plan": _serialize_plan_snapshot(snapshot, request, detail=True),
    })


@require_GET
def serve_plan_share(request, token: str):
    snapshot = _snapshot_from_share_token(token)
    if not snapshot:
        return HttpResponse("Shared plan not found or expired.", status=404)
    title = html.escape(snapshot.title or "韓国旅行プラン")
    plan_text = html.escape(snapshot.plan_text or "")
    updated = snapshot.updated_at.strftime("%Y-%m-%d %H:%M")
    body = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #172033; background: #f6f7fb; }}
    main {{ max-width: 860px; margin: 0 auto; padding: 28px 18px 48px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.45rem; line-height: 1.3; }}
    .meta {{ margin: 0; color: #687085; font-size: .86rem; }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    button {{ border: 1px solid #cfd6e4; border-radius: 8px; background: #fff; padding: 8px 12px; font-weight: 700; cursor: pointer; }}
    article {{ white-space: pre-wrap; line-height: 1.75; background: #fff; border: 1px solid #dfe4ee; border-radius: 10px; padding: 20px; }}
    footer {{ margin-top: 14px; color: #687085; font-size: .78rem; }}
    @media print {{
      body {{ background: #fff; }}
      main {{ padding: 0; max-width: none; }}
      .actions {{ display: none; }}
      article {{ border: none; padding: 0; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{title}</h1>
        <p class="meta">Shared travel plan · {html.escape(updated)}</p>
      </div>
      <div class="actions">
        <button type="button" onclick="navigator.clipboard?.writeText(location.href); this.textContent='コピー済み';">リンクコピー</button>
        <button type="button" onclick="window.print()">PDF保存</button>
      </div>
    </header>
    <article>{plan_text}</article>
    <footer>施設の営業時間・チケット・交通情報は出発前に公式情報で確認してください。</footer>
  </main>
</body>
</html>"""
    return HttpResponse(body, content_type="text/html; charset=utf-8")


@require_POST
def api_chat(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    message = body.get("message")
    reply_language = body.get("reply_language")
    history = body.get("history") or []
    session_id = body.get("session_id")
    traveler_profile = body.get("traveler_profile")

    rl_err = _check_chat_rate(request)
    if rl_err:
        return rl_err

    if not isinstance(message, str) or not message.strip():
        return JsonResponse({"detail": "message is required"}, status=400)
    message = message.strip()
    if len(message) > 8000:
        return JsonResponse({"detail": "message too long"}, status=400)

    if reply_language not in ("日本語", "한국어"):
        return JsonResponse({"detail": "reply_language must be 「日本語」 or 「한국어」"}, status=400)

    if not isinstance(history, list) or len(history) > 50:
        return JsonResponse({"detail": "history must be a list with at most 50 items"}, status=400)

    clean_history = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        if len(content) > 32000:
            return JsonResponse({"detail": "history item content too long"}, status=400)
        clean_history.append({"role": role, "content": content})

    # 위치 정보 (선택, 장소 검색용)
    latitude: float | None = None
    longitude: float | None = None
    radius_meters: int = 1000
    if isinstance(body.get("latitude"), (int, float)):
        latitude = float(body["latitude"])
    if isinstance(body.get("longitude"), (int, float)):
        longitude = float(body["longitude"])
    if isinstance(body.get("radius_meters"), int):
        radius_meters = max(300, min(int(body["radius_meters"]), 10000))

    chat_session, _ = get_or_create_chat_session(
        session_id=session_id if isinstance(session_id, str) else None,
        reply_language=reply_language,
        latitude=latitude,
        longitude=longitude,
    )
    upsert_traveler_profile(chat_session, traveler_profile if isinstance(traveler_profile, dict) else None)

    profile_payload = traveler_profile if isinstance(traveler_profile, dict) else None
    recent_snapshot = None if profile_payload else _latest_plan_snapshot(request)
    chat_message = _with_recent_plan_context(message, recent_snapshot)
    if profile_payload is None:
        profile_payload = _chat_profile_from_snapshot(recent_snapshot)
    try:
        chat_result = run_chat(
            message=chat_message,
            reply_language=reply_language,
            history=clean_history,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            traveler_profile=profile_payload,
        )
    except Exception as exc:
        logger.exception("run_chat failed: %s", exc)
        err_msg = (
            "申し訳ありません、サーバーエラーが発生しました。しばらくしてから再度お試しください。"
            if reply_language == "日本語"
            else "죄송합니다, 서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        )
        return JsonResponse({"reply": err_msg, "detail": str(exc)}, status=500)

    save_chat_turn(
        session=chat_session,
        user_message=message,
        assistant_reply=chat_result.reply,
        translated_ko=chat_result.translated_ko,
        route_result=chat_result.route_result,
    )

    payload: dict = {
        "reply": chat_result.reply,
        "session_id": str(chat_session.id),
    }
    if chat_result.translated_ko is not None:
        payload["translated_ko"] = chat_result.translated_ko
    if chat_result.route_result is not None:
        rr = chat_result.route_result
        payload["category"] = rr.category
        payload["keyword"] = rr.keyword
        payload["sources_used"] = rr.sources_used
        payload["places_count"] = rr.places_count
        if rr.places_error:
            payload["places_error"] = rr.places_error
        if getattr(rr, "data_sparse", False):
            payload["data_sparse"] = True
        if getattr(rr, "alternative_regions", None):
            payload["alternative_regions"] = rr.alternative_regions
        logger.debug("category=%r keyword=%r places=%s error=%r",
                     rr.category, rr.keyword, rr.places_count, rr.places_error)
    if chat_result.places:
        payload["places"] = chat_result.places
    if chat_result.visitkorea_stays:
        payload["visitkorea_stays"] = chat_result.visitkorea_stays
    if chat_result.visitkorea_festivals:
        payload["visitkorea_festivals"] = chat_result.visitkorea_festivals
    if chat_result.visitkorea_attractions:
        payload["visitkorea_attractions"] = chat_result.visitkorea_attractions
    if chat_result.sports_events:
        payload["sports_events"] = chat_result.sports_events
    if getattr(chat_result, "gyeonggi_events", None):
        payload["gyeonggi_events"] = chat_result.gyeonggi_events
    if getattr(chat_result, "ticket_platform_events", None):
        payload["ticket_platform_events"] = chat_result.ticket_platform_events
    if chat_result.flights:
        payload["flights"] = chat_result.flights
        payload["flight_subtype"] = chat_result.flight_subtype
    if chat_result.airport:
        payload["airport"] = chat_result.airport
        payload["flight_subtype"] = chat_result.flight_subtype
    return JsonResponse(payload)


@require_POST
def api_chat_stream(request):
    """SSE 스트리밍 채팅 — LLM 첫 토큰부터 즉시 전송."""
    from django.http import StreamingHttpResponse

    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    message = body.get("message")
    reply_language = body.get("reply_language")
    history = body.get("history") or []
    session_id = body.get("session_id")
    traveler_profile = body.get("traveler_profile")

    rl_err = _check_chat_rate(request)
    if rl_err:
        return rl_err

    if not isinstance(message, str) or not message.strip():
        return JsonResponse({"detail": "message is required"}, status=400)
    message = message.strip()
    if len(message) > 8000:
        return JsonResponse({"detail": "message too long"}, status=400)
    if reply_language not in ("日本語", "한국어"):
        return JsonResponse({"detail": "reply_language must be 「日本語」 or 「한국어」"}, status=400)
    if not isinstance(history, list) or len(history) > 50:
        return JsonResponse({"detail": "history must be a list with at most 50 items"}, status=400)

    clean_history = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        if len(content) > 32000:
            return JsonResponse({"detail": "history item content too long"}, status=400)
        clean_history.append({"role": role, "content": content})

    latitude: float | None = None
    longitude: float | None = None
    radius_meters: int = 1000
    if isinstance(body.get("latitude"), (int, float)):
        latitude = float(body["latitude"])
    if isinstance(body.get("longitude"), (int, float)):
        longitude = float(body["longitude"])
    if isinstance(body.get("radius_meters"), int):
        radius_meters = max(300, min(int(body["radius_meters"]), 10000))

    chat_session, _ = get_or_create_chat_session(
        session_id=session_id if isinstance(session_id, str) else None,
        reply_language=reply_language,
        latitude=latitude,
        longitude=longitude,
    )
    profile_payload = traveler_profile if isinstance(traveler_profile, dict) else None
    recent_snapshot = None if profile_payload else _latest_plan_snapshot(request)
    chat_message = _with_recent_plan_context(message, recent_snapshot)
    if profile_payload is None:
        profile_payload = _chat_profile_from_snapshot(recent_snapshot)
    upsert_traveler_profile(chat_session, profile_payload)

    from tour_api.llm_service import run_chat_stream

    def _sse_gen():
        full_reply = ""
        try:
            for event_type, data in run_chat_stream(
                message=chat_message,
                reply_language=reply_language,
                history=clean_history,
                latitude=latitude,
                longitude=longitude,
                radius_meters=radius_meters,
                traveler_profile=profile_payload,
            ):
                if event_type == "meta":
                    payload = {"type": "meta", "session_id": str(chat_session.id)}
                    payload.update(data)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif event_type == "token":
                    full_reply += data
                    yield f"data: {json.dumps({'type': 'token', 'delta': data}, ensure_ascii=False)}\n\n"
                elif event_type == "done":
                    done_data = data or {}
                    translated_ko = done_data.get("translated_ko")
                    final_reply = done_data.get("reply", full_reply)
                    try:
                        save_chat_turn(
                            session=chat_session,
                            user_message=message,
                            assistant_reply=final_reply,
                            translated_ko=translated_ko,
                            route_result=None,
                        )
                    except Exception as _save_exc:
                        logger.warning("save_chat_turn (stream) failed: %s", _save_exc)
                    yield f"data: {json.dumps({'type': 'done', 'translated_ko': translated_ko}, ensure_ascii=False)}\n\n"
                elif event_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': str(data)}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("api_chat_stream SSE gen failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    response = StreamingHttpResponse(
        _sse_gen(),
        content_type="text/event-stream; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _serialize_auth_user(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "display_name": _user_display_name(u),
    }


def _resolve_login_username(identifier: str) -> str | None:
    """メールまたは従来のユーザー名でログイン用 username を解決。"""
    ident = (identifier or "").strip()
    if not ident:
        return None
    if "@" in ident:
        email = ident.lower()
        u = User.objects.filter(email__iexact=email).first()
        return u.username if u else None
    return ident


@require_POST
def api_register(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    display_name = (body.get("display_name") or body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    password_confirm = body.get("password_confirm") or body.get("password2") or ""
    # 旧クライアント: username のみ
    legacy_username = (body.get("username") or "").strip()

    if legacy_username and not email:
        username = legacy_username
        if len(username) > 150 or not re.match(r"^[\w.@+-]+$", username):
            return JsonResponse(
                {"detail": "ユーザー名は150文字以内の英数字・記号のみ使用できます"},
                status=400,
            )
        if len(password) < 8:
            return JsonResponse({"detail": "パスワードは8文字以上必要です"}, status=400)
        if User.objects.filter(username=username).exists():
            return JsonResponse({"detail": "このユーザー名はすでに使われています"}, status=409)
        user = User.objects.create_user(username=username, password=password, email="")
        django_login(request, user)
        return JsonResponse(
            {"ok": True, "user": _serialize_auth_user(user)},
            status=201,
        )

    if not display_name:
        return JsonResponse({"detail": "表示名を入力してください"}, status=400)
    if len(display_name) > 50:
        return JsonResponse({"detail": "表示名は50文字以内で入力してください"}, status=400)
    if not email:
        return JsonResponse({"detail": "メールアドレスを入力してください"}, status=400)
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return JsonResponse({"detail": "メールアドレスの形式が正しくありません"}, status=400)
    if len(password) < 8:
        return JsonResponse({"detail": "パスワードは8文字以上必要です"}, status=400)
    if len(password) > 128:
        return JsonResponse({"detail": "パスワードは128文字以内にしてください"}, status=400)
    if password != password_confirm:
        return JsonResponse({"detail": "パスワード（確認）が一致しません"}, status=400)
    if not body.get("terms_accepted"):
        return JsonResponse({"detail": "利用規約への同意が必要です"}, status=400)

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({"detail": "このメールアドレスはすでに登録されています"}, status=409)

    username = email
    if User.objects.filter(username=username).exists():
        return JsonResponse({"detail": "このメールアドレスはすでに登録されています"}, status=409)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=display_name[:150],
    )
    django_login(request, user)
    return JsonResponse(
        {"ok": True, "user": _serialize_auth_user(user)},
        status=201,
    )


@require_POST
def api_login(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    identifier = (body.get("email") or body.get("username") or "").strip()
    password = body.get("password") or ""

    login_name = _resolve_login_username(identifier)
    if not login_name:
        return JsonResponse(
            {"detail": "メールアドレスまたはパスワードが正しくありません"},
            status=401,
        )

    user = authenticate(request, username=login_name, password=password)
    if user is None:
        return JsonResponse(
            {"detail": "メールアドレスまたはパスワードが正しくありません"},
            status=401,
        )

    django_login(request, user)
    return JsonResponse({"ok": True, "user": _serialize_auth_user(user)})


@require_POST
def api_logout(request):
    django_logout(request)
    return JsonResponse({"ok": True})


@require_POST
def api_delete_account(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "ログインが必要です"}, status=401)

    user = request.user
    is_oauth = user.username.startswith("google_") or user.username.startswith("line_")

    if not is_oauth:
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"detail": "リクエスト形式が不正です"}, status=400)
        if not user.check_password(body.get("password", "")):
            return JsonResponse({"detail": "パスワードが正しくありません"}, status=400)

    django_logout(request)
    user.delete()
    return JsonResponse({"ok": True})


def _user_display_name(u: User) -> str:
    """OAuth 内部 username（google_* 等）をそのまま表示しない。"""
    first = (u.first_name or "").strip()
    if first:
        return first
    uname = (u.username or "").strip()
    if uname and not (uname.startswith("google_") or uname.startswith("line_")):
        return uname
    email = (u.email or "").strip()
    if email and "@" in email:
        local = email.split("@", 1)[0].strip()
        if local and not local.startswith("google"):
            return local
    return "ゲスト"


@ensure_csrf_cookie
@require_GET
def api_me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)
    u = request.user
    display_name = _user_display_name(u)
    return JsonResponse({
        "authenticated": True,
        "user": {
            "id": u.id,
            "username": u.username,
            "display_name": display_name,
            "email": u.email,
        },
    })


def _oauth_login(request, user: User) -> None:
    user.backend = "django.contrib.auth.backends.ModelBackend"
    django_login(request, user)
    request.session.modified = True


_OAUTH_STATE_SIGNER = TimestampSigner(salt="tour-oauth-state")


def _oauth_state_create() -> str:
    return _OAUTH_STATE_SIGNER.sign(secrets.token_urlsafe(16))


def _oauth_state_valid(state: str | None) -> bool:
    if not state:
        return False
    try:
        _OAUTH_STATE_SIGNER.unsign(state, max_age=600)
        return True
    except (BadSignature, SignatureExpired):
        return False


# ── Google OAuth2 ──────────────────────────────────────────────────────────
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_INFO = "https://www.googleapis.com/oauth2/v2/userinfo"


@require_GET
def oauth_google_start(request):
    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    if not cid:
        return JsonResponse({"detail": "GOOGLE_CLIENT_ID not configured"}, status=503)
    state = _oauth_state_create()
    params = {
        "client_id": cid,
        "redirect_uri": request.build_absolute_uri("/api/auth/oauth/google/callback/"),
        "scope": "email profile",
        "response_type": "code",
        "state": state,
    }
    return redirect(_GOOGLE_AUTH + "?" + urllib.parse.urlencode(params))


@require_GET
def oauth_google_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or not _oauth_state_valid(state):
        logger.warning("Google OAuth callback rejected (code=%s, state_ok=%s)", bool(code), _oauth_state_valid(state))
        return redirect("/?oauth_error=1")

    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    csecret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    try:
        tok = http_requests.post(_GOOGLE_TOKEN, data={
            "code": code,
            "client_id": cid,
            "client_secret": csecret,
            "redirect_uri": request.build_absolute_uri("/api/auth/oauth/google/callback/"),
            "grant_type": "authorization_code",
        }, timeout=10).json()
        access_token = tok.get("access_token", "")
        info = http_requests.get(_GOOGLE_INFO, headers={"Authorization": f"Bearer {access_token}"}, timeout=10).json()
    except Exception:
        logger.exception("Google OAuth token/profile failed")
        return redirect("/?oauth_error=1")

    google_id = info.get("id", "")
    email = info.get("email", "")
    if not google_id:
        return redirect("/?oauth_error=1")

    username = f"google_{google_id}"[:150]
    given = (info.get("given_name") or "").strip()
    full = (info.get("name") or "").strip()
    display = given or (full.split()[0] if full else "")
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "first_name": display[:150]},
    )
    if display and user.first_name != display[:150]:
        user.first_name = display[:150]
        user.save(update_fields=["first_name"])
    elif not created and email and not user.email:
        user.email = email
        user.save(update_fields=["email"])
    _oauth_login(request, user)
    return redirect("/?oauth_success=1")


# ── LINE OAuth2 ────────────────────────────────────────────────────────────
_LINE_AUTH = "https://access.line.me/oauth2/v2.1/authorize"
_LINE_TOKEN = "https://api.line.me/oauth2/v2.1/token"
_LINE_PROFILE = "https://api.line.me/v2/profile"


def _line_redirect_uri(request: HttpRequest) -> str:
    """LINE_REDIRECT_URI 환경변수 우선, 없으면 동적 생성."""
    fixed = os.getenv("LINE_REDIRECT_URI", "").strip()
    return fixed or request.build_absolute_uri("/api/auth/oauth/line/callback/")


@require_GET
def oauth_line_start(request):
    cid = os.getenv("LINE_CHANNEL_ID", "")
    if not cid:
        return JsonResponse({"detail": "LINE_CHANNEL_ID not configured"}, status=503)
    state = _oauth_state_create()
    params = {
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": _line_redirect_uri(request),
        "state": state,
        "scope": "profile openid",
    }
    return redirect(_LINE_AUTH + "?" + urllib.parse.urlencode(params))


@require_GET
def oauth_line_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or not _oauth_state_valid(state):
        logger.warning("LINE OAuth callback rejected (code=%s, state_ok=%s)", bool(code), _oauth_state_valid(state))
        return redirect("/?oauth_error=1")

    cid = os.getenv("LINE_CHANNEL_ID", "")
    csecret = os.getenv("LINE_CHANNEL_SECRET", "")
    redirect_uri = _line_redirect_uri(request)
    try:
        tok = http_requests.post(_LINE_TOKEN, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": cid,
            "client_secret": csecret,
        }, timeout=10).json()
        if tok.get("error") or not tok.get("access_token"):
            logger.warning("LINE token error: %s (redirect_uri=%s)", tok, redirect_uri)
            return redirect("/?oauth_error=1")
        access_token = tok["access_token"]
        profile = http_requests.get(
            _LINE_PROFILE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        ).json()
    except Exception:
        logger.exception("LINE OAuth token/profile failed")
        return redirect("/?oauth_error=1")

    line_id = profile.get("userId", "")
    if not line_id:
        logger.warning("LINE profile missing userId: %s", profile)
        return redirect("/?oauth_error=1")

    display_name = (profile.get("displayName") or "").strip()

    username = f"line_{line_id}"[:150]
    user, created = User.objects.get_or_create(username=username)
    if created:
        user.set_unusable_password()
    # 로그인할 때마다 LINE 표시 이름을 first_name에 동기화
    if display_name and user.first_name != display_name:
        user.first_name = display_name[:150]
    user.save()
    _oauth_login(request, user)
    return redirect("/?oauth_success=1")


@require_GET
def serve_home(request):
    path = _FRONTEND / "home.html"
    if not path.is_file():
        return JsonResponse({"detail": "frontend/home.html not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="text/html; charset=utf-8")


@require_GET
def serve_chat(request):
    path = _FRONTEND / "chat.html"
    if not path.is_file():
        return JsonResponse({"detail": "frontend/chat.html not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="text/html; charset=utf-8")


@require_GET
def serve_styles(request):
    path = _FRONTEND / "styles.css"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="text/css; charset=utf-8")


@require_GET
def serve_theme_bg(request):
    path = _FRONTEND / "assets" / "bg-korea-theme.svg"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="image/svg+xml")


@require_GET
def api_link_preview(request):
    """Interpark ticket URL Open Graph preview for link cards in plan/chat UI."""
    import sys
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.link_preview import fetch_link_preview

    url = (request.GET.get("url") or "").strip()
    if not url:
        return JsonResponse({"detail": "url required"}, status=400)
    try:
        preview = fetch_link_preview(url)
        return JsonResponse(preview)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    except Exception as exc:
        logger.warning("api_link_preview error: %s", exc)
        return JsonResponse({"detail": "preview failed", "error": str(exc)}, status=502)


@require_GET
def serve_app_js(request):
    path = _FRONTEND / "app.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    resp = FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


@require_GET
def serve_auth_js(request):
    path = _FRONTEND / "auth.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    resp = FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


@require_GET
def serve_wizard_js(request):
    path = _FRONTEND / "wizard.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    resp = FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


@require_GET
def serve_plan_map_js(request):
    path = _FRONTEND / "plan-map.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    resp = FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


@require_GET
def serve_link_preview_js(request):
    path = _FRONTEND / "link-preview.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    resp = FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


@require_GET
def serve_region_areas_js(request):
    path = _FRONTEND / "region-areas.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    resp = FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


@require_GET
def serve_maps_open_url_js(request):
    path = _FRONTEND / "maps-open-url.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    resp = FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


@require_GET
def api_naver_resolve(request):
    """장소명 → 네이버 지역검색 첫 번째 결과(공식명+좌표) 반환.

    GET /api/naver-resolve/?q=명동성당
    → {"canonical": "천주교 서울대교구 주교좌명동대성당", "lat": 37.xxx, "lng": 126.xxx, ...}
    """
    import sys
    from pathlib import Path as _P
    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))
    from src.api.naver_search_client import NaverSearchClient, _clean_html

    q = (request.GET.get("q") or "").strip()
    if not q or len(q) > 100:
        return JsonResponse({"error": "q required"}, status=400)

    import hashlib
    cache_key = f"naver_resolve_v1:{hashlib.md5(q.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    client = NaverSearchClient()
    if not client.is_configured:
        return JsonResponse({"canonical": None, "error": "not_configured"})

    items = client.search_local(q, display=1)
    if not items:
        result: dict = {"canonical": None}
        cache.set(cache_key, result, timeout=3600)
        return JsonResponse(result)

    item = items[0]
    name = _clean_html(item.get("title"))
    lat = lng = None
    try:
        raw_x = float(item.get("mapx") or 0)
        raw_y = float(item.get("mapy") or 0)
        if raw_x > 10_000 and raw_y > 10_000:
            lng = raw_x / 1e7
            lat = raw_y / 1e7
    except (TypeError, ValueError):
        pass

    result = {
        "canonical": name,
        "lat": lat,
        "lng": lng,
        "category": _clean_html(item.get("category") or ""),
        "address": _clean_html(item.get("roadAddress") or item.get("address") or ""),
    }
    cache.set(cache_key, result, timeout=86400)
    return JsonResponse(result)
