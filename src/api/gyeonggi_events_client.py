"""전국공연행사정보표준데이터 API 클라이언트.

공공데이터포털(data.go.kr) 기반 전국 공연·행사 정보.
인증키: PUBLIC_API_KEY (.env)
엔드포인트: http://api.data.go.kr/openapi/tn_pubr_public_cltur_event_api

응답 필드:
  fstvlNm        행사명
  signguNm       시군구명
  rdnmadr        도로명주소
  lttud / lngtd  위도 / 경도
  fstvlStartDate 시작일 YYYYMMDD
  fstvlEndDate   종료일 YYYYMMDD
  fstvlCo        행사내용
  hmpgUrl        홈페이지
  opar           운영여부 (Y/N)
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

_ENDPOINT = "http://api.data.go.kr/openapi/tn_pubr_public_cltur_event_api"

# 위저드 region 칩 → 주소 매칭 키워드 (rdnmadr 필드에서 검색)
# 일부 API 응답은 "경기도 고양시..." 대신 "고양시..."처럼 광역자치단체명 생략 → 시군명도 포함
_REGION_KEYWORDS: dict[str, list[str]] = {
    "seoul":        ["서울"],
    "gyeonggi":     ["경기", "고양", "수원", "성남", "용인", "안양", "부천", "의정부",
                     "파주", "김포", "화성", "광명", "평택", "안산", "시흥", "구리",
                     "남양주", "하남", "의왕", "군포", "오산", "이천", "안성", "양주"],
    "incheon":      ["인천"],
    "busan":        ["부산"],
    "jeju":         ["제주"],
    "gangwon":      ["강원", "춘천", "강릉", "속초", "원주", "동해", "삼척", "태백"],
    "chungcheong":  ["충남", "충북", "충청", "대전", "세종", "천안", "공주", "아산", "보령"],
    "jeolla":       ["전남", "전북", "전라", "광주", "전주", "여수", "순천", "목포"],
    "gyeongsang":   ["경남", "경북", "경상", "대구", "울산", "창원", "포항", "경주", "김해"],
}


@dataclass(frozen=True)
class GyeonggiEvent:
    """전국 공연·행사 정보 (클래스명은 하위호환성 유지)."""
    name: str
    start_date: str      # YYYY-MM-DD
    end_date: str        # YYYY-MM-DD
    city: str            # 시군구명
    venue: str           # 도로명주소 (장소)
    description: str     # 행사내용 (최대 200자)
    url: str             # 홈페이지 URL
    source_service: str  # 항상 "nationwide"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GyeonggiEventsClient:
    """전국공연행사정보표준데이터 API — 여행 기간·지역 내 행사 조회.

    클래스명은 router.py 하위호환성을 위해 유지.
    """

    def __init__(self, timeout: int = 10):
        self.api_key = (
            os.getenv("PUBLIC_API_KEY", "")
            or os.getenv("GYEONGGI_API_KEY", "")
        ).strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(
        self,
        start: date | None = None,
        end: date | None = None,
        *,
        regions: list[str] | None = None,
        city: str | None = None,
        max_results: int = 20,
        name_filter: list[str] | None = None,
    ) -> list[GyeonggiEvent]:
        """여행 기간에 열리는 행사 조회.

        regions: 위저드 region 칩 값 목록 (e.g. ["gyeonggi", "seoul"])
        city:    시군구 직접 지정 (e.g. "고양")
        """
        if not self.is_configured:
            logger.debug("PUBLIC_API_KEY not set — skipping nationwide events")
            return []
        if start is None:
            start = date.today()
        if end is None:
            end = start + timedelta(days=14)

        addr_keywords = self._build_addr_keywords(regions, city)

        try:
            rows = self._fetch(num_of_rows=300)
        except Exception as exc:
            logger.warning("nationwide events fetch failed: %s", exc)
            return []

        events = self._filter_and_parse(rows, start, end, addr_keywords, name_filter=name_filter)
        logger.info("nationwide events: %d total rows, %d matched", len(rows), len(events))
        return events[:max_results]

    def _fetch(self, num_of_rows: int = 100) -> list[dict]:
        """공공데이터포털 API 호출 — 최대 3페이지 조회 (날짜 필터는 로컬에서 수행)."""
        all_rows: list[dict] = []
        per_page = min(num_of_rows, 100)
        for page in range(1, 4):  # 최대 3페이지 (300건)
            params: dict[str, Any] = {
                "serviceKey": self.api_key,
                "pageNo": page,
                "numOfRows": per_page,
                "type": "json",
            }
            try:
                resp = requests.get(_ENDPOINT, params=params, timeout=self.timeout)
                resp.raise_for_status()
                rows = self._extract_rows(resp.json())
            except Exception:
                break
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < per_page:
                break  # 마지막 페이지
            if len(all_rows) >= num_of_rows:
                break
        return all_rows

    @staticmethod
    def _extract_rows(data: Any) -> list[dict]:
        """응답 구조에서 item 배열 추출 (형식 변동에 대응)."""
        if not isinstance(data, dict):
            return []
        # 표준 형식: {"response": {"body": {"items": {"item": [...]}}}}
        body = (data.get("response") or {}).get("body") or {}
        if not body:
            # 일부 API: {"response": {"header": ..., "body": [...]}}
            body = data.get("response", {})

        items = body.get("items") or body.get("item") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, list):
            return items
        # 단건 결과: dict 한 개
        if isinstance(items, dict):
            return [items]
        return []

    def _filter_and_parse(
        self,
        rows: list[dict],
        start: date,
        end: date,
        addr_keywords: list[str],
        name_filter: list[str] | None = None,
    ) -> list[GyeonggiEvent]:
        out: list[GyeonggiEvent] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            name = (row.get("fstvlNm") or "").strip()
            if not name:
                continue

            # 운영 종료된 행사 제외 (opar=N)
            if str(row.get("opar") or "Y").upper() == "N":
                continue

            ev_start = self._parse_date(str(row.get("fstvlStartDate") or ""))
            ev_end = self._parse_date(str(row.get("fstvlEndDate") or "")) or ev_start
            if not ev_start:
                continue
            # 여행 기간과 겹치지 않으면 제외
            if ev_start > end or (ev_end and ev_end < start):
                continue

            addr = (row.get("rdnmadr") or row.get("signguNm") or "").strip()
            city = (row.get("signguNm") or "").strip()

            # 지역 필터: addr_keywords 중 하나라도 주소에 포함되면 통과
            if addr_keywords:
                if not any(kw in addr for kw in addr_keywords):
                    continue

            desc = (row.get("fstvlCo") or "").strip()

            # 키워드 필터 (K-pop 콘서트 등)
            if name_filter:
                text = (name + " " + desc).lower()
                if not any(kw.lower() in text for kw in name_filter):
                    continue

            url = (row.get("hmpgUrl") or "").strip()

            out.append(GyeonggiEvent(
                name=name,
                start_date=ev_start.isoformat(),
                end_date=ev_end.isoformat() if ev_end else ev_start.isoformat(),
                city=city or addr[:20],
                venue=addr,
                description=desc[:200] if desc else "",
                url=url,
                source_service="nationwide",
            ))

        return out

    @staticmethod
    def _build_addr_keywords(regions: list[str] | None, city: str | None) -> list[str]:
        """region 칩·도시명 → 주소 매칭 키워드 목록."""
        keywords: list[str] = []
        for reg in (regions or []):
            keywords.extend(_REGION_KEYWORDS.get(reg, []))
        if city:
            keywords.append(city)
        return list(dict.fromkeys(keywords))  # 중복 제거, 순서 유지

    @staticmethod
    def _parse_date(raw: str) -> date | None:
        s = raw.strip().replace("-", "").replace(".", "")
        if len(s) >= 8:
            try:
                return datetime.strptime(s[:8], "%Y%m%d").date()
            except ValueError:
                pass
        return None

    def probe(self) -> dict[str, Any]:
        """API 연결 테스트 — probe_gyeonggi.py 에서 사용."""
        result: dict[str, Any] = {
            "api_key_set": self.is_configured,
            "api_key_prefix": self.api_key[:8] + "..." if self.is_configured else None,
            "endpoint": _ENDPOINT,
            "ok": False,
            "row_count": 0,
            "sample": [],
            "error": None,
        }
        if not self.is_configured:
            return result
        try:
            rows = self._fetch(num_of_rows=3)
            result["ok"] = True
            result["row_count"] = len(rows)
            result["sample"] = rows[:2]
            if rows:
                result["sample_fields"] = list(rows[0].keys())
        except Exception as exc:
            result["error"] = str(exc)
        return result


# ─── 경기데이터드림 KINTEX API ────────────────────────────────────────────

_KINTEX_ENDPOINT_BASE = "https://openapi.gg.go.kr"
_KINTEX_SERVICE_CANDIDATES = [
    "KintexEvent",
    "KintexEventInfo",
    "KintexSchedule",
    "KintexExhibition",
    "KintexFair",
    "KintexEvents",
    "KintexInfo",
    "Kintex",
    "KintexPerformance",
]


class _KintexServiceNotFound(Exception):
    """경기데이터드림 서비스명 오류(ERROR-310 등) — 후보 순환용."""


class KintexEventsClient:
    """경기데이터드림 KINTEX 행사 정보 API.

    서비스명이 미확정이므로 후보 목록을 순차 시도하여 첫 성공 서비스를 캐싱.
    반환 타입은 GyeonggiEvent (동일 파이프라인에 병합하기 위해).
    """

    _working_service: str | None = None  # 클래스 레벨 캐시

    def __init__(self, timeout: int = 8):
        self.api_key = (
            os.getenv("GYEONGGI_API_KEY", "")
            or os.getenv("PUBLIC_API_KEY", "")
        ).strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(
        self,
        start: date | None = None,
        end: date | None = None,
        max_results: int = 10,
    ) -> list[GyeonggiEvent]:
        if not self.is_configured:
            return []
        if start is None:
            start = date.today()
        if end is None:
            end = start + timedelta(days=30)

        # 캐시된 서비스명 먼저 시도
        if KintexEventsClient._working_service:
            try:
                rows = self._fetch(KintexEventsClient._working_service)
                return self._parse(rows, start, end)[:max_results]
            except Exception:
                KintexEventsClient._working_service = None

        # 후보 순차 시도
        for svc in _KINTEX_SERVICE_CANDIDATES:
            try:
                rows = self._fetch(svc)
                events = self._parse(rows, start, end)
                KintexEventsClient._working_service = svc
                logger.info("KINTEX service=%s → %d rows, %d matched", svc, len(rows), len(events))
                return events[:max_results]
            except _KintexServiceNotFound:
                continue
            except Exception as exc:
                logger.debug("KINTEX [%s]: %s", svc, exc)
                continue

        logger.info("KINTEX: no working service found among %d candidates", len(_KINTEX_SERVICE_CANDIDATES))
        return []

    def _fetch(self, service_name: str) -> list[dict]:
        url = f"{_KINTEX_ENDPOINT_BASE}/{service_name}"
        params: dict[str, Any] = {
            "KEY": self.api_key,
            "Type": "json",
            "pIndex": 1,
            "pSize": 100,
        }
        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return self._extract_rows(resp.json(), service_name)

    @staticmethod
    def _extract_rows(data: Any, service_name: str) -> list[dict]:
        if not isinstance(data, dict):
            raise _KintexServiceNotFound(f"non-dict response: {service_name}")

        # 경기데이터드림 표준 오류 체크
        result = data.get("RESULT") or {}
        if isinstance(result, dict):
            code = str(result.get("CODE", ""))
            if "ERROR" in code:
                raise _KintexServiceNotFound(f"{service_name}: {code}")

        # 표준 구조: {ServiceName: [{head:[...]}, {row:[...]}]}
        service_data = data.get(service_name)
        if service_data is None:
            for v in data.values():
                if isinstance(v, list):
                    service_data = v
                    break

        if not service_data or not isinstance(service_data, list):
            return []  # 빈 결과는 유효 (오류 아님)

        rows: list[dict] = []
        for block in service_data:
            if isinstance(block, dict):
                row_data = block.get("row")
                if isinstance(row_data, list):
                    rows.extend(row_data)
        return rows

    def _parse(
        self, rows: list[dict], start: date, end: date
    ) -> list[GyeonggiEvent]:
        out: list[GyeonggiEvent] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            name = (
                row.get("EVENT_NM") or row.get("FSTVL_NM") or row.get("TITLE")
                or row.get("title") or row.get("event_nm") or ""
            ).strip()
            if not name:
                continue

            start_raw = (
                row.get("HOLD_STRT_DE") or row.get("HOLD_BEGIN_DE") or row.get("START_DATE")
                or row.get("startDate") or row.get("start_date") or ""
            )
            end_raw = (
                row.get("HOLD_END_DE") or row.get("HOLD_FINISH_DE") or row.get("END_DATE")
                or row.get("endDate") or row.get("end_date") or start_raw
            )

            ev_start = self._parse_date(str(start_raw))
            ev_end = self._parse_date(str(end_raw)) or ev_start
            if not ev_start:
                continue
            if ev_start > end or (ev_end and ev_end < start):
                continue

            venue = (
                row.get("EVENT_PLACE") or row.get("HOLD_PLACE") or row.get("VENUE")
                or row.get("venue") or "킨텍스(KINTEX), 고양시"
            ).strip()
            desc = (
                row.get("EVENT_CNTN") or row.get("FSTVL_CO") or row.get("DESCRIPTION")
                or row.get("description") or ""
            ).strip()
            url = (row.get("HMPG_URL") or row.get("URL") or row.get("url") or "").strip()

            out.append(GyeonggiEvent(
                name=name,
                start_date=ev_start.isoformat(),
                end_date=ev_end.isoformat() if ev_end else ev_start.isoformat(),
                city="고양시",
                venue=venue,
                description=desc[:200] if desc else "",
                url=url,
                source_service=f"kintex:{KintexEventsClient._working_service or 'unknown'}",
            ))
        return out

    @staticmethod
    def _parse_date(raw: str) -> date | None:
        s = raw.strip().replace("-", "").replace(".", "").replace("/", "")
        if len(s) >= 8:
            try:
                return datetime.strptime(s[:8], "%Y%m%d").date()
            except ValueError:
                pass
        return None

    def probe(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "api_key_set": self.is_configured,
            "endpoint_base": _KINTEX_ENDPOINT_BASE,
            "candidates": _KINTEX_SERVICE_CANDIDATES,
            "working_service": None,
            "ok": False,
            "row_count": 0,
            "error": None,
        }
        if not self.is_configured:
            result["error"] = "GYEONGGI_API_KEY not set"
            return result
        for svc in _KINTEX_SERVICE_CANDIDATES:
            try:
                rows = self._fetch(svc)
                KintexEventsClient._working_service = svc
                result.update({"working_service": svc, "ok": True, "row_count": len(rows)})
                return result
            except _KintexServiceNotFound:
                continue
            except Exception as exc:
                result["error"] = str(exc)
                return result
        result["error"] = "No working service found among candidates"
        return result


def fmt_gyeonggi_events(events: list[GyeonggiEvent], lang: str = "ja") -> str:
    """LLM 컨텍스트용 행사 텍스트 포맷 (함수명 하위호환 유지)."""
    if not events:
        return ""
    lines: list[str] = []
    for i, ev in enumerate(events, 1):
        period = (
            ev.start_date
            if ev.start_date == ev.end_date
            else f"{ev.start_date}〜{ev.end_date}"
        )
        venue_part = f" | {ev.venue}" if ev.venue else ""
        url_part = f"\n    URL: {ev.url}" if ev.url else ""
        desc_part = f"\n    概要: {ev.description}" if ev.description else ""
        lines.append(
            f"[{i}] {ev.name} | {period} | {ev.city}{venue_part}{desc_part}{url_part}"
        )
    return "\n".join(lines)
