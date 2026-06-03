"""행정안전부 도로명주소 검색 API (juso.go.kr).

승인키: .env 의 ``JUSO_API_KEY`` (또는 ``ROAD_ADDR_API_KEY``)
신청: https://www.juso.go.kr/addrlink/devAddrLinkRequest.do
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Any
import requests

logger = logging.getLogger(__name__)

_JUSO_SEARCH_URL = "https://www.juso.go.kr/addrlink/addrLinkApi.do"
_REQUEST_HEADERS = {
    "User-Agent": "Japantour/1.0 (+https://github.com/japantour)",
    "Accept": "application/json",
}


@dataclass(frozen=True)
class RoadAddress:
    """도로명주소 API 검색 결과 1건."""

    road_addr: str
    jibun_addr: str
    zip_no: str
    sido: str
    sigungu: str
    eupmyeon: str
    building_name: str
    bd_mgt_sn: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def display_name(self) -> str:
        if self.building_name:
            return f"{self.road_addr} ({self.building_name})"
        return self.road_addr


def juso_api_key_from_env() -> str | None:
    for name in ("JUSO_API_KEY", "ROAD_ADDR_API_KEY", "MOIS_JUSO_API_KEY"):
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return None


def is_juso_configured() -> bool:
    return bool(juso_api_key_from_env())


def _normalize_juso_rows(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def search_road_addresses(
    keyword: str,
    *,
    page: int = 1,
    count_per_page: int = 20,
    timeout: int = 12,
) -> tuple[list[RoadAddress], dict[str, Any]]:
    """도로명·지번 주소 검색.

    Returns:
        (addresses, meta) — meta 에 error, total_count, page 등 포함
    """
    key = juso_api_key_from_env()
    meta: dict[str, Any] = {
        "configured": bool(key),
        "keyword": keyword,
        "page": page,
    }
    q = (keyword or "").strip()
    if not q:
        meta["error"] = "keyword_required"
        return [], meta
    if len(q) < 2:
        meta["error"] = "keyword_too_short"
        return [], meta
    if not key:
        meta["error"] = "JUSO_API_KEY not configured"
        return [], meta

    page = max(1, page)
    count_per_page = min(max(count_per_page, 1), 100)

    params = {
        "confmKey": key,
        "currentPage": str(page),
        "countPerPage": str(count_per_page),
        "keyword": q,
        "resultType": "json",
        "hstryYn": "N",
        "firstSort": "road",
        "addInfoYn": "N",
    }

    try:
        # juso.go.kr uses legacy TLS configuration that causes SSL EOF errors
        # in some environments — disable certificate verification as a workaround.
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.get(
            _JUSO_SEARCH_URL,
            params=params,
            headers=_REQUEST_HEADERS,
            timeout=timeout,
            verify=False,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        logger.warning("juso request failed [%r]: %s", q[:40], exc)
        meta["error"] = str(exc)
        return [], meta
    except ValueError as exc:
        logger.warning("juso JSON parse failed [%r]: %s", q[:40], exc)
        meta["error"] = "invalid_json_response"
        return [], meta

    results = payload.get("results") or {}
    common = results.get("common") or {}
    err_code = str(common.get("errorCode", "")).strip()
    err_msg = str(common.get("errorMessage", "")).strip()
    meta["error_code"] = err_code
    meta["error_message"] = err_msg
    meta["total_count"] = int(common.get("totalCount") or 0)

    if err_code and err_code != "0":
        meta["error"] = err_msg or f"juso_error_{err_code}"
        logger.info("juso API [%r] code=%s msg=%s", q[:40], err_code, err_msg)
        return [], meta

    rows = _normalize_juso_rows(results.get("juso"))
    out: list[RoadAddress] = []
    for row in rows:
        road = (row.get("roadAddr") or row.get("roadAddrPart1") or "").strip()
        if not road:
            continue
        out.append(
            RoadAddress(
                road_addr=road,
                jibun_addr=(row.get("jibunAddr") or "").strip(),
                zip_no=(row.get("zipNo") or "").strip(),
                sido=(row.get("siNm") or "").strip(),
                sigungu=(row.get("sggNm") or "").strip(),
                eupmyeon=(row.get("emdNm") or "").strip(),
                building_name=(row.get("bdNm") or "").strip(),
                bd_mgt_sn=(row.get("bdMgtSn") or "").strip(),
            )
        )

    meta["count"] = len(out)
    logger.info("juso search [%r] page=%d → %d rows", q[:40], page, len(out))
    return out, meta
