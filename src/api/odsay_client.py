"""ODsay public transit routing API client."""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ODsayAuthError(Exception):
    """Raised when ODsay returns API key authentication failure."""

ODSAY_BASE_URL = "https://api.odsay.com/v1/api"


def odsay_api_key() -> str:
    raw = (os.getenv("ODSAY_API_KEY") or "").strip()
    # .env 에 URL 인코딩된 키가 저장된 경우 원본으로 복원
    if raw and "%" in raw:
        try:
            raw = urllib.parse.unquote(raw)
        except Exception:
            pass
    return raw


def _parse_linestring(linestring: str) -> list[dict[str, float]]:
    """Parse 'lng,lat lng,lat ...' into [{lat, lng}, ...] list."""
    points = []
    for pair in linestring.split():
        parts = pair.split(",")
        if len(parts) == 2:
            try:
                points.append({"lat": float(parts[1]), "lng": float(parts[0])})
            except ValueError:
                continue
    return points


def transit_route(
    start_lng: float,
    start_lat: float,
    goal_lng: float,
    goal_lat: float,
    *,
    timeout: int = 12,
) -> dict[str, Any] | None:
    """Call ODsay searchPubTransPathT and return best route path + summary."""
    api_key = odsay_api_key()
    if not api_key:
        logger.warning("ODsay: ODSAY_API_KEY not set — restart server after adding to .env")
        return None

    # requests params 딕셔너리로 전달 (자동 URL 인코딩)
    params: dict[str, str] = {
        "apiKey": api_key,
        "SX": f"{start_lng:.6f}",
        "SY": f"{start_lat:.6f}",
        "EX": f"{goal_lng:.6f}",
        "EY": f"{goal_lat:.6f}",
        "OPT": "0",
        "output": "json",
    }

    try:
        resp = requests.get(
            f"{ODSAY_BASE_URL}/searchPubTransPathT",
            params=params,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
    except Exception as exc:
        logger.warning("ODsay: network error: %s", exc)
        return None

    # HTTP 오류 여부 확인 (예외 없이 status_code로 처리)
    if resp.status_code != 200:
        logger.warning("ODsay: HTTP %s — %s", resp.status_code, resp.text[:200])
        return None

    try:
        data = resp.json()
    except Exception:
        logger.warning("ODsay: non-JSON response: %s", resp.text[:200])
        return None

    # 에러 응답 (단일 dict 또는 list 형식 모두 처리)
    if "error" in data:
        err_raw = data["error"]
        err = err_raw[0] if isinstance(err_raw, list) and err_raw else err_raw
        code = err.get("code", "") if isinstance(err, dict) else str(err_raw)
        msg = err.get("message", "") if isinstance(err, dict) else ""
        logger.warning("ODsay API error code=%s msg=%s", code, msg)
        if "ApiKeyAuthFailed" in msg or code in ("500", "-99"):
            raise ODsayAuthError(f"ODsay key authentication failed: {msg}")
        return None

    result = data.get("result")
    if result is None:
        logger.warning(
            "ODsay: result=null for (%.5f,%.5f)→(%.5f,%.5f). "
            "Possible causes: (1) key quota exceeded, (2) no transit route for these coords, "
            "(3) key auth issue returning null instead of error. full_response=%s",
            start_lng, start_lat, goal_lng, goal_lat,
            str(data)[:600],
        )
        return None

    paths = result.get("path") or []
    if not paths:
        logger.debug("ODsay: no path in result")
        return None

    best = paths[0]
    info = best.get("info") or {}
    combined: list[dict[str, float]] = []

    for sub in best.get("subPath") or []:
        linestring = (sub.get("passShape") or {}).get("linestring") or ""
        if not linestring:
            continue
        points = _parse_linestring(linestring)
        if not points:
            continue
        if combined:
            combined.extend(points[1:] if points[0] == combined[-1] else points)
        else:
            combined.extend(points)

    if len(combined) < 2:
        logger.warning(
            "ODsay: only %d coords extracted — subPaths may lack passShape",
            len(combined),
        )
        return None

    return {
        "path": combined,
        "summary": {
            "totalTime": info.get("totalTime"),
            "totalFare": info.get("payment"),
            "subwayTransitCount": info.get("subwayTransitCount", 0),
            "busTransitCount": info.get("busTransitCount", 0),
        },
    }
