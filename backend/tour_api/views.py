from __future__ import annotations

import dataclasses
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
from django.views.decorators.http import require_GET, require_POST

from tour_api.chat_persistence import (
    get_or_create_chat_session,
    save_chat_turn,
    upsert_traveler_profile,
)
from tour_api.llm_service import get_client, run_chat

_FRONTEND: Path = settings.FRONTEND_DIR

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

    from src.api.juso_client import is_juso_configured, search_road_addresses

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
        "source": "juso",
        "configured": is_juso_configured(),
    }
    if meta.get("error"):
        payload["error"] = meta["error"]
    if meta.get("total_count") is not None:
        payload["total_count"] = meta["total_count"]
    return JsonResponse(payload)


@require_GET
def api_places_search(request):
    """위저드 Step 3 숙박시설 검색 — Google Places Text Search."""
    import sys
    from pathlib import Path as _P
    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.google_places_client import GooglePlacesClient, KR_LOCATION_RESTRICTION
    from src.api.hotel_area_filter import build_hotel_search_query, filter_hotel_places

    sido = request.GET.get("sido", "").strip()
    sigungu = request.GET.get("sigungu", "").strip()
    query = request.GET.get("q", "").strip()
    if not query and (sido or sigungu):
        query = build_hotel_search_query(sido, sigungu)
    if not query:
        return JsonResponse({"places": []})
    fetch_all = request.GET.get("all", "").lower() in ("1", "true", "yes")
    try:
        limit = min(max(int(request.GET.get("limit", 5)), 1), 20)
    except (TypeError, ValueError):
        limit = 5
    try:
        pclient = GooglePlacesClient()
        if not pclient.is_configured:
            return JsonResponse({"places": [], "error": "Places API not configured"})
        search_kwargs: dict = {
            "text_query": query,
            "language_code": "ja",
            "included_type": "hotel",
            "location_restriction": KR_LOCATION_RESTRICTION,
        }
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


@require_POST
def api_places_enrich(request):
    """プラン本文の Google Maps URL を Places 詳細（写真・評価等）に変換."""
    import sys
    from pathlib import Path as _P

    _root = _P(settings.BASE_DIR).parent
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from src.api.google_places_client import GooglePlacesClient

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
    _REGION_ADDR_KW: dict[str, tuple[str, ...]] = {
        "gangwon": ("강원", "gangwon", "강릉", "속초", "평창", "고성", "춘천", "원주", "정선", "태백", "동해"),
        "busan": ("부산", "busan", "해운대", "기장", "사하", "사상", "동래"),
        "jeju": ("제주", "jeju"),
        "gyeonggi": ("경기", "gyeonggi", "고양", "수원", "성남", "용인", "안양", "과천", "의정부", "파주", "부천", "시흥", "안산", "화성"),
        "seoul": ("서울", "seoul"),
        "incheon": ("인천", "incheon"),
        "chungcheong": ("충청", "chungcheong", "대전", "청주", "충주", "천안", "공주", "세종", "충북", "충남"),
        "jeolla": ("전라", "jeolla", "전주", "광주", "여수", "목포", "순천", "나주"),
        "gyeongsang": ("경상", "gyeongsang", "대구", "경주", "창원", "포항", "울산", "진주", "거제", "경북", "경남"),
    }

    def _addr_matches_dest(addr: str) -> bool:
        if not dest_regions:
            return True
        a = addr.lower()
        return any(
            any(kw in a for kw in _REGION_ADDR_KW.get(reg, ()))
            for reg in dest_regions
        )

    try:
        pclient = GooglePlacesClient()
        if not pclient.is_configured:
            return JsonResponse({"places": {}, "error": "Places API not configured"})
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
        query = str(raw.get("query") or "").strip()
        if not url:
            continue
        try:
            place = pclient.find_for_plan_item(url, query, language_code=lang)
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
    """Places API 직접 테스트 (DEBUG=true 전용). 브라우저에서 /api/places-debug/?q=명동 호텔 로 호출."""
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
    """Google Maps JavaScript API 用キー（ブラウザ — HTTPリファラー制限必須）."""
    maps_key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    hotels_key = (os.getenv("GOOGLE_HOTELS_API_KEY") or "").strip()
    # ブラウザ地図は GOOGLE_MAPS_API_KEY 専用を推奨（HOTELS はサーバーIP制限のことが多い）
    if maps_key:
        api_key, source = maps_key, "GOOGLE_MAPS_API_KEY"
    elif hotels_key:
        api_key, source = hotels_key, "GOOGLE_HOTELS_API_KEY"
    else:
        api_key, source = "", ""
    return JsonResponse({
        "enabled": bool(api_key),
        "api_key": api_key,
        "source": source,
        "browser_note": (
            "Maps JavaScript API は HTTPリファラー制限のブラウザ用キーが必要です。"
            "Vertex/Gemini のサービスアカウントキー連携は対象外です。"
        ),
    })


@require_GET
def api_photo(request):
    """Google Places 사진 프록시 — API 키를 서버에서 처리해 클라이언트에 노출 방지."""
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

    # 위치 정보 (선택, Places API 연동용)
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
    try:
        chat_result = run_chat(
            message=message,
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
    return FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")


@require_GET
def serve_auth_js(request):
    path = _FRONTEND / "auth.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")


@require_GET
def serve_wizard_js(request):
    path = _FRONTEND / "wizard.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")


@require_GET
def serve_plan_map_js(request):
    path = _FRONTEND / "plan-map.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")


@require_GET
def serve_link_preview_js(request):
    path = _FRONTEND / "link-preview.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")


@require_GET
def serve_region_areas_js(request):
    path = _FRONTEND / "region-areas.js"
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="application/javascript; charset=utf-8")
