from __future__ import annotations

import json
import os
import re
import secrets
import urllib.parse
from pathlib import Path

import requests as http_requests
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.models import User
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from tour_api.chat_persistence import (
    get_or_create_chat_session,
    save_chat_turn,
    upsert_traveler_profile,
)
from tour_api.llm_service import get_client, run_chat

_FRONTEND: Path = settings.FRONTEND_DIR


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


@csrf_exempt
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

    chat_result = run_chat(
        message=message,
        reply_language=reply_language,
        history=clean_history,
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
    )

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
        # 진단용 — 원인 파악 후 제거
        print(f"[DIAG] category={rr.category!r} keyword={rr.keyword!r} "
              f"places={rr.places_count} error={rr.places_error!r}")
    if chat_result.places:
        payload["places"] = chat_result.places
    if chat_result.flights:
        payload["flights"] = chat_result.flights
        payload["flight_subtype"] = chat_result.flight_subtype
    if chat_result.airport:
        payload["airport"] = chat_result.airport
        payload["flight_subtype"] = chat_result.flight_subtype
    return JsonResponse(payload)


@csrf_exempt
@require_POST
def api_register(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    email = (body.get("email") or "").strip()

    if not username:
        return JsonResponse({"detail": "ユーザー名を入力してください"}, status=400)
    if len(username) > 150 or not re.match(r"^[\w.@+-]+$", username):
        return JsonResponse({"detail": "ユーザー名は150文字以内の英数字・記号のみ使用できます"}, status=400)
    if len(password) < 8:
        return JsonResponse({"detail": "パスワードは8文字以上必要です"}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({"detail": "このユーザー名はすでに使われています"}, status=409)

    user = User.objects.create_user(username=username, password=password, email=email)
    django_login(request, user)
    return JsonResponse(
        {"ok": True, "user": {"id": user.id, "username": user.username, "email": user.email}},
        status=201,
    )


@csrf_exempt
@require_POST
def api_login(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "ユーザー名またはパスワードが正しくありません"}, status=401)

    django_login(request, user)
    return JsonResponse({"ok": True, "user": {"id": user.id, "username": user.username, "email": user.email}})


@csrf_exempt
@require_POST
def api_logout(request):
    django_logout(request)
    return JsonResponse({"ok": True})


@require_GET
def api_me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)
    u = request.user
    return JsonResponse({
        "authenticated": True,
        "user": {"id": u.id, "username": u.username, "email": u.email},
    })


def _oauth_login(request, user: User) -> None:
    user.backend = "django.contrib.auth.backends.ModelBackend"
    django_login(request, user)


# ── Google OAuth2 ──────────────────────────────────────────────────────────
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_INFO = "https://www.googleapis.com/oauth2/v2/userinfo"


@require_GET
def oauth_google_start(request):
    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    if not cid:
        return JsonResponse({"detail": "GOOGLE_CLIENT_ID not configured"}, status=503)
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
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
    if not code or state != request.session.get("oauth_state"):
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
        return redirect("/?oauth_error=1")

    google_id = info.get("id", "")
    email = info.get("email", "")
    if not google_id:
        return redirect("/?oauth_error=1")

    username = f"google_{google_id}"[:150]
    user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
    _oauth_login(request, user)
    return redirect("/")


# ── LINE OAuth2 ────────────────────────────────────────────────────────────
_LINE_AUTH = "https://access.line.me/oauth2/v2.1/authorize"
_LINE_TOKEN = "https://api.line.me/oauth2/v2.1/token"
_LINE_PROFILE = "https://api.line.me/v2/profile"


@require_GET
def oauth_line_start(request):
    cid = os.getenv("LINE_CHANNEL_ID", "")
    if not cid:
        return JsonResponse({"detail": "LINE_CHANNEL_ID not configured"}, status=503)
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    params = {
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": request.build_absolute_uri("/api/auth/oauth/line/callback/"),
        "state": state,
        "scope": "profile openid",
    }
    return redirect(_LINE_AUTH + "?" + urllib.parse.urlencode(params))


@require_GET
def oauth_line_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or state != request.session.get("oauth_state"):
        return redirect("/?oauth_error=1")

    cid = os.getenv("LINE_CHANNEL_ID", "")
    csecret = os.getenv("LINE_CHANNEL_SECRET", "")
    try:
        tok = http_requests.post(_LINE_TOKEN, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": request.build_absolute_uri("/api/auth/oauth/line/callback/"),
            "client_id": cid,
            "client_secret": csecret,
        }, timeout=10).json()
        access_token = tok.get("access_token", "")
        profile = http_requests.get(_LINE_PROFILE, headers={"Authorization": f"Bearer {access_token}"}, timeout=10).json()
    except Exception:
        return redirect("/?oauth_error=1")

    line_id = profile.get("userId", "")
    display_name = profile.get("displayName", "LINE User")
    if not line_id:
        return redirect("/?oauth_error=1")

    username = f"line_{line_id}"[:150]
    user, created = User.objects.get_or_create(username=username)
    if created:
        user.set_unusable_password()
        user.save()
    _oauth_login(request, user)
    return redirect("/")


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
