"""행정안전부 도로명주소 검색 API (juso.go.kr).

승인키: .env 의 ``JUSO_API_KEY`` (또는 ``ROAD_ADDR_API_KEY``)
영문주소 검색 API 승인키가 별도이면 ``JUSO_ENG_API_KEY`` 사용.
신청: https://www.juso.go.kr/addrlink/devAddrLinkRequest.do
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import Any
import requests

logger = logging.getLogger(__name__)

_JUSO_SEARCH_URL = "https://www.juso.go.kr/addrlink/addrLinkApi.do"
_JUSO_ENG_SEARCH_URL = "https://business.juso.go.kr/addrlink/addrEngApi.do"
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
    english_road_addr: str = ""
    english_jibun_addr: str = ""
    source: str = "juso"

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


def juso_eng_api_key_from_env() -> str | None:
    for name in (
        "JUSO_ENG_API_KEY",
        "JUSO_ENGLISH_API_KEY",
        "ROAD_ADDR_ENG_API_KEY",
        "ROAD_ADDR_ENGLISH_API_KEY",
    ):
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return juso_api_key_from_env()


def is_juso_configured() -> bool:
    return bool(juso_api_key_from_env())


def is_juso_eng_configured() -> bool:
    return bool(juso_eng_api_key_from_env())


def _normalize_juso_rows(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _has_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text or ""))


def _has_hangul(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def _latin_address_keyword(text: str) -> str:
    """한글 지역명과 섞인 로마자 주소에서 영문 검색용 키워드를 추출."""
    s = re.sub(r"[가-힣]+", " ", text or "")
    s = re.sub(r"\s+", " ", s).strip(" ,")
    return s


_CHOSEONG = {
    "": 11,  # ㅇ
    "g": 0, "kk": 1, "n": 2, "d": 3, "tt": 4, "r": 5, "l": 5,
    "m": 6, "b": 7, "pp": 8, "s": 9, "ss": 10, "j": 12, "jj": 13,
    "ch": 14, "k": 15, "t": 16, "p": 17, "h": 18,
}
_JUNGSEONG = {
    "a": 0, "ae": 1, "ya": 2, "yae": 3, "eo": 4, "e": 5, "yeo": 6,
    "ye": 7, "o": 8, "wa": 9, "wae": 10, "oe": 11, "yo": 12,
    "u": 13, "wo": 14, "we": 15, "wi": 16, "yu": 17, "eu": 18,
    "ui": 19, "i": 20,
}
_JONGSEONG = {
    "": 0, "g": 1, "k": 1, "n": 4, "d": 7, "t": 7, "s": 7,
    "l": 8, "r": 8, "m": 16, "b": 17, "p": 17, "ng": 21,
}
_INITIAL_KEYS = sorted((k for k in _CHOSEONG if k), key=len, reverse=True)
_VOWEL_KEYS = sorted(_JUNGSEONG, key=len, reverse=True)
_FINAL_KEYS = sorted((k for k in _JONGSEONG if k), key=len, reverse=True)


def _starts_roman_syllable(text: str) -> bool:
    if not text:
        return False
    for initial in ("", *_INITIAL_KEYS):
        if not text.startswith(initial):
            continue
        rest = text[len(initial):]
        if any(rest.startswith(v) for v in _VOWEL_KEYS):
            return True
    return False


def _roman_syllable_to_hangul(initial: str, vowel: str, final: str = "") -> str:
    code = 0xAC00 + (_CHOSEONG[initial] * 21 + _JUNGSEONG[vowel]) * 28 + _JONGSEONG[final]
    return chr(code)


def _roman_word_to_hangul(word: str) -> str:
    """간단한 국어 로마자 표기 역변환. 주소 fallback용이므로 보수적으로 실패 가능."""
    s = re.sub(r"[^a-z]", "", (word or "").lower())
    out: list[str] = []
    i = 0
    while i < len(s):
        initial = ""
        for key in _INITIAL_KEYS:
            if s.startswith(key, i):
                initial = key
                break
        pos = i + len(initial)
        vowel = ""
        for key in _VOWEL_KEYS:
            if s.startswith(key, pos):
                vowel = key
                break
        if not vowel:
            return ""
        pos += len(vowel)

        final = ""
        tail = s[pos:]
        for key in _FINAL_KEYS:
            if not tail.startswith(key):
                continue
            after = tail[len(key):]
            if not after:
                final = key
                break
            if key == "ng" and _starts_roman_syllable(after):
                final = key
                break
            if key != "ng" and not re.match(r"^[aeiouy]", after) and _starts_roman_syllable(after):
                final = key
                break
        pos += len(final)
        out.append(_roman_syllable_to_hangul(initial, vowel, final))
        i = pos
    return "".join(out)


def _korean_prefix_without_latin(text: str) -> str:
    s = re.sub(r"[A-Za-z0-9][A-Za-z0-9\s\-_]*", " ", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _romanized_juso_keywords(text: str) -> list[str]:
    """Todang-ro 104beon-gil 38 → 토당로104번길 38 후보 생성."""
    latin = _latin_address_keyword(text).lower()
    if not latin:
        return []
    normalized = re.sub(r"[,()]", " ", latin)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    prefix = _korean_prefix_without_latin(text)
    candidates: list[str] = []

    patterns = [
        re.compile(r"^(?P<road>[a-z]+)[-\s]*ro(?:\s+(?P<beon>\d+)\s*beon[-\s]*gil)?(?:\s+(?P<num>\d+))?$"),
        re.compile(r"^(?P<num>\d+)\s+(?P<road>[a-z]+)[-\s]*ro(?:\s+(?P<beon>\d+)\s*beon[-\s]*gil)?$"),
        re.compile(r"^(?P<road>[a-z]+)$"),
    ]
    for pattern in patterns:
        m = pattern.match(normalized)
        if not m:
            continue
        road = _roman_word_to_hangul(m.group("road") or "")
        if not road:
            continue
        beon = m.groupdict().get("beon") or ""
        num = m.groupdict().get("num") or ""
        if beon:
            core = f"{road}로{beon}번길"
            candidates.extend([f"{core} {num}".strip(), core])
        else:
            candidates.extend([f"{road}로 {num}".strip(), f"{road}로", road])
            if num:
                candidates.append(f"{road} {num}".strip())
        break

    out: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        for q in (f"{prefix} {c}".strip(), c):
            q = re.sub(r"\s+", " ", q).strip()
            if q and q not in seen:
                seen.add(q)
                out.append(q)
    return out


def _fetch_juso_payload(
    url: str,
    *,
    params: dict[str, str],
    keyword: str,
    timeout: int,
    label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    meta: dict[str, Any] = {"source": label}
    try:
        # juso.go.kr uses legacy TLS configuration that causes SSL EOF errors
        # in some environments — disable certificate verification as a workaround.
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.get(
            url,
            params=params,
            headers=_REQUEST_HEADERS,
            timeout=timeout,
            verify=False,
        )
        resp.raise_for_status()
        return resp.json(), meta
    except requests.RequestException as exc:
        logger.warning("%s request failed [%r]: %s", label, keyword[:40], exc)
        meta["error"] = str(exc)
        return None, meta
    except ValueError:
        logger.warning("%s JSON parse failed [%r]", label, keyword[:40])
        meta["error"] = "invalid_json_response"
        return None, meta


def search_english_road_addresses(
    keyword: str,
    *,
    page: int = 1,
    count_per_page: int = 20,
    timeout: int = 12,
) -> tuple[list[RoadAddress], dict[str, Any]]:
    """영문 도로명주소 검색 API.

    Juso 영문 API는 영문 도로명주소와 함께 한글 도로명주소(korAddr)를 반환한다.
    """
    key = juso_eng_api_key_from_env()
    meta: dict[str, Any] = {
        "configured": bool(key),
        "keyword": keyword,
        "page": page,
        "source": "juso_eng",
    }
    q = (keyword or "").strip()
    if not q:
        meta["error"] = "keyword_required"
        return [], meta
    if len(q) < 2:
        meta["error"] = "keyword_too_short"
        return [], meta
    if not key:
        meta["error"] = "JUSO_ENG_API_KEY or JUSO_API_KEY not configured"
        return [], meta

    page = max(1, page)
    count_per_page = min(max(count_per_page, 1), 100)
    params = {
        "confmKey": key,
        "currentPage": str(page),
        "countPerPage": str(count_per_page),
        "keyword": q,
        "resultType": "json",
    }
    payload, req_meta = _fetch_juso_payload(
        _JUSO_ENG_SEARCH_URL,
        params=params,
        keyword=q,
        timeout=timeout,
        label="juso_eng",
    )
    meta.update(req_meta)
    if payload is None:
        return [], meta

    results = payload.get("results") or {}
    common = results.get("common") or {}
    err_code = str(common.get("errorCode", "")).strip()
    err_msg = str(common.get("errorMessage", "")).strip()
    meta["error_code"] = err_code
    meta["error_message"] = err_msg
    meta["total_count"] = int(common.get("totalCount") or 0)

    if err_code and err_code != "0":
        meta["error"] = err_msg or f"juso_eng_error_{err_code}"
        logger.info("juso_eng API [%r] code=%s msg=%s", q[:40], err_code, err_msg)
        return [], meta

    out: list[RoadAddress] = []
    for row in _normalize_juso_rows(results.get("juso")):
        eng_road = (row.get("roadAddr") or "").strip()
        kor_road = (row.get("korAddr") or "").strip()
        if not (eng_road or kor_road):
            continue
        out.append(
            RoadAddress(
                road_addr=kor_road or eng_road,
                jibun_addr="",
                zip_no=(row.get("zipNo") or "").strip(),
                sido=(row.get("siNm") or "").strip(),
                sigungu=(row.get("sggNm") or "").strip(),
                eupmyeon=(row.get("emdNm") or "").strip(),
                building_name="",
                bd_mgt_sn=(row.get("rnMgtSn") or "").strip(),
                english_road_addr=eng_road,
                english_jibun_addr=(row.get("jibunAddr") or "").strip(),
                source="juso_eng",
            )
        )

    meta["count"] = len(out)
    logger.info("juso_eng search [%r] page=%d → %d rows", q[:40], page, len(out))
    return out, meta


def _parse_korean_juso_rows(results: dict[str, Any]) -> list[RoadAddress]:
    out: list[RoadAddress] = []
    for row in _normalize_juso_rows(results.get("juso")):
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
                english_road_addr=(row.get("engAddr") or "").strip(),
                source="juso",
            )
        )
    return out


def _search_korean_juso_once(
    keyword: str,
    *,
    key: str,
    page: int,
    count_per_page: int,
    timeout: int,
    source: str = "juso",
) -> tuple[list[RoadAddress], dict[str, Any]]:
    params = {
        "confmKey": key,
        "currentPage": str(page),
        "countPerPage": str(count_per_page),
        "keyword": keyword,
        "resultType": "json",
        "hstryYn": "N",
        "firstSort": "road",
        "addInfoYn": "N",
    }
    payload, req_meta = _fetch_juso_payload(
        _JUSO_SEARCH_URL,
        params=params,
        keyword=keyword,
        timeout=timeout,
        label=source,
    )
    meta: dict[str, Any] = {
        "configured": True,
        "keyword": keyword,
        "page": page,
        **req_meta,
    }
    if payload is None:
        return [], meta

    results = payload.get("results") or {}
    common = results.get("common") or {}
    err_code = str(common.get("errorCode", "")).strip()
    err_msg = str(common.get("errorMessage", "")).strip()
    meta["error_code"] = err_code
    meta["error_message"] = err_msg
    meta["total_count"] = int(common.get("totalCount") or 0)

    if err_code and err_code != "0":
        meta["error"] = err_msg or f"{source}_error_{err_code}"
        logger.info("%s API [%r] code=%s msg=%s", source, keyword[:40], err_code, err_msg)
        return [], meta

    out = _parse_korean_juso_rows(results)
    meta["count"] = len(out)
    return out, meta


def _search_romanized_korean_juso(
    keyword: str,
    *,
    key: str,
    page: int,
    count_per_page: int,
    timeout: int,
) -> tuple[list[RoadAddress], dict[str, Any]]:
    last_meta: dict[str, Any] = {"source": "juso_romanized", "keyword": keyword}
    for q in _romanized_juso_keywords(keyword):
        out, meta = _search_korean_juso_once(
            q,
            key=key,
            page=page,
            count_per_page=count_per_page,
            timeout=timeout,
            source="juso_romanized",
        )
        last_meta = meta
        if out:
            logger.info("juso romanized fallback [%r → %r] → %d rows", keyword[:40], q[:40], len(out))
            return out, meta
    return [], last_meta


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

    if _has_latin(q) and not _has_hangul(q):
        eng_out, eng_meta = search_english_road_addresses(
            q,
            page=page,
            count_per_page=count_per_page,
            timeout=timeout,
        )
        if eng_out:
            return eng_out, eng_meta

    out, meta = _search_korean_juso_once(
        q,
        key=key,
        page=page,
        count_per_page=count_per_page,
        timeout=timeout,
        source="juso",
    )
    if meta.get("error"):
        if _has_latin(q):
            roman_out, roman_meta = _search_romanized_korean_juso(
                q,
                key=key,
                page=page,
                count_per_page=count_per_page,
                timeout=timeout,
            )
            if roman_out:
                return roman_out, roman_meta
            eng_q = _latin_address_keyword(q) or q
            eng_out, eng_meta = search_english_road_addresses(
                eng_q,
                page=page,
                count_per_page=count_per_page,
                timeout=timeout,
            )
            if eng_out:
                return eng_out, eng_meta
        return [], meta

    if not out and _has_latin(q):
        roman_out, roman_meta = _search_romanized_korean_juso(
            q,
            key=key,
            page=page,
            count_per_page=count_per_page,
            timeout=timeout,
        )
        if roman_out:
            return roman_out, roman_meta
        eng_q = _latin_address_keyword(q) or q
        eng_out, eng_meta = search_english_road_addresses(
            eng_q,
            page=page,
            count_per_page=count_per_page,
            timeout=timeout,
        )
        if eng_out:
            return eng_out, eng_meta

    meta["count"] = len(out)
    logger.info("juso search [%r] page=%d → %d rows", q[:40], page, len(out))
    return out, meta
