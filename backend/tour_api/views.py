from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from tour_api.llm_service import get_client, run_chat

_FRONTEND: Path = settings.FRONTEND_DIR


@require_GET
def api_health(request):
    return JsonResponse({"ok": True, "openai_configured": get_client() is not None})


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

    reply, translated_ko = run_chat(
        message=message,
        reply_language=reply_language,
        history=clean_history,
    )
    payload: dict = {"reply": reply}
    if translated_ko is not None:
        payload["translated_ko"] = translated_ko
    return JsonResponse(payload)


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
