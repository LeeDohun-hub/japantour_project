"""한국관광공사 관광정보 API (TourAPI 4.0 — JpnService2).

공공데이터포털 인증키: INCHEONTRANSPORT_API_KEY (.env, data.go.kr 계정 공통)
Base: https://apis.data.go.kr/B551011/JpnService2/

주요 엔드포인트:
  - areaBasedList2   지역별 관광지·문화시설
  - searchFestival2  행사·축제
  - searchStay2      숙박
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B551011/JpnService2"
MOBILE_OS = "ETC"
MOBILE_APP = "Japantour"

# 서울 areaCode (legacy) — ldongCode2 연동 전 기본값
SEOUL_AREA_CODE = "1"

# TourAPI contentTypeId (JpnService2)
CONTENT_TYPE_ATTRACTION = "12"  # 관광지
CONTENT_TYPE_CULTURE = "14"  # 문화시설


@dataclass(frozen=True)
class TourApiItem:
    """목록 조회 공통 필드 (festival / stay 등)."""

    content_id: str
    content_type_id: str
    title: str
    addr1: str = ""
    addr2: str = ""
    mapx: str = ""
    mapy: str = ""
    tel: str = ""
    area_code: str = ""
    sigungu_code: str = ""
    first_image: str = ""
    first_image2: str = ""
    event_start_date: str = ""  # YYYYMMDD (festival)
    event_end_date: str = ""
    cat1: str = ""
    cat2: str = ""
    cat3: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["maps_uri"] = self.maps_uri()
        d["event_period"] = self.event_period_display()
        return d

    def maps_uri(self) -> str:
        """좌표 기반 Google Maps 링크 (mapx=경도, mapy=위도)."""
        if not self.mapx or not self.mapy:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={self.mapy},{self.mapx}"

    def event_period_display(self) -> str:
        """행사 기간 YYYYMMDD → YYYY-MM-DD 표시."""
        if not self.event_start_date:
            return ""
        s = self.event_start_date
        e = self.event_end_date or s
        fmt = lambda x: f"{x[:4]}-{x[4:6]}-{x[6:8]}" if len(x) >= 8 else x
        if s == e:
            return fmt(s)
        return f"{fmt(s)} 〜 {fmt(e)}"


def _service_key_from_env() -> str | None:
    return (
        os.getenv("INCHEONTRANSPORT_API_KEY")
        or os.getenv("INCHEONAIRPORT_API_KEY")
    )


def _parse_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """response.body.items.item → list[dict]."""
    body = (raw.get("response") or {}).get("body") or {}
    items_wrap = body.get("items")
    if not items_wrap or items_wrap == "":
        return []
    if not isinstance(items_wrap, dict):
        return []
    item = items_wrap.get("item")
    if item is None:
        return []
    if isinstance(item, list):
        return [x for x in item if isinstance(x, dict)]
    if isinstance(item, dict):
        return [item]
    return []


def _parse_header(raw: dict[str, Any]) -> tuple[str, str]:
    """표준(response.header) 및 오류(flat resultCode) 형식 모두 처리."""
    if "response" in raw:
        header = raw["response"].get("header") or {}
    else:
        header = raw
    return str(header.get("resultCode", "")), str(header.get("resultMsg", ""))


def _item_from_row(row: dict[str, Any]) -> TourApiItem:
    return TourApiItem(
        content_id=str(row.get("contentid", "")),
        content_type_id=str(row.get("contenttypeid", "")),
        title=str(row.get("title", "")).strip(),
        addr1=str(row.get("addr1", "") or "").strip(),
        addr2=str(row.get("addr2", "") or "").strip(),
        mapx=str(row.get("mapx", "") or ""),
        mapy=str(row.get("mapy", "") or ""),
        tel=str(row.get("tel", "") or "").strip(),
        area_code=str(row.get("areacode", "") or ""),
        sigungu_code=str(row.get("sigungucode", "") or ""),
        first_image=str(row.get("firstimage", "") or "").strip(),
        first_image2=str(row.get("firstimage2", "") or "").strip(),
        event_start_date=str(row.get("eventstartdate", "") or ""),
        event_end_date=str(row.get("eventenddate", "") or ""),
        cat1=str(row.get("cat1", "") or ""),
        cat2=str(row.get("cat2", "") or ""),
        cat3=str(row.get("cat3", "") or ""),
    )


class VisitKoreaClient:
    """한국관광공사 TourAPI (일문 JpnService2) 클라이언트."""

    def __init__(self, service_key: str | None = None, timeout: int = 20):
        self.service_key = service_key or _service_key_from_env()
        self.timeout = timeout
        self.base_url = BASE_URL.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.service_key)

    def _base_params(self) -> dict[str, str]:
        if not self.service_key:
            raise ValueError("INCHEONTRANSPORT_API_KEY가 설정되지 않았습니다.")
        return {
            "serviceKey": self.service_key,
            "MobileOS": MOBILE_OS,
            "MobileApp": MOBILE_APP,
            "_type": "json",
            "numOfRows": "10",
            "pageNo": "1",
        }

    def _get(self, operation: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{operation}"
        params = {**self._base_params(), **(extra or {})}
        resp = requests.get(url, params=params, timeout=self.timeout)
        logger.info(
            "VisitKorea %s HTTP %d — %s",
            operation,
            resp.status_code,
            {k: v for k, v in params.items() if k != "serviceKey"},
        )
        if not resp.ok:
            logger.warning("VisitKorea %s body: %s", operation, resp.text[:400])
            resp.raise_for_status()
        data = resp.json()
        code, msg = _parse_header(data)
        if code and code not in ("00", "0000"):
            raise ValueError(f"VisitKorea {operation} resultCode={code} msg={msg}")
        return data

    def _list(
        self,
        operation: str,
        extra: dict[str, str] | None = None,
        *,
        page_no: int = 1,
        num_of_rows: int = 10,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """Returns (items, result_code, result_msg, total_count)."""
        # TourAPI 4.0: listYN 미지원 (INVALID_REQUEST_PARAMETER_ERROR)
        params = {
            "pageNo": str(page_no),
            "numOfRows": str(num_of_rows),
            "arrange": "O",
            **(extra or {}),
        }
        raw = self._get(operation, params)
        code, msg = _parse_header(raw)
        body = (raw.get("response") or {}).get("body") or {}
        total = int(body.get("totalCount") or 0)
        rows = _parse_items(raw)
        return [_item_from_row(r) for r in rows], code, msg, total

    @staticmethod
    def _date_yyyymmdd(d: date) -> str:
        return d.strftime("%Y%m%d")

    def search_festival(
        self,
        *,
        start: date,
        end: date,
        area_code: str = "",
        sigungu_code: str = "",
        page_no: int = 1,
        num_of_rows: int = 10,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """searchFestival2 — 행사·축제 목록."""
        extra: dict[str, str] = {
            "eventStartDate": self._date_yyyymmdd(start),
            "eventEndDate": self._date_yyyymmdd(end),
        }
        if area_code:
            extra["areaCode"] = area_code
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        return self._list(
            "searchFestival2",
            extra,
            page_no=page_no,
            num_of_rows=num_of_rows,
        )

    def search_stay(
        self,
        *,
        area_code: str = SEOUL_AREA_CODE,
        sigungu_code: str = "",
        page_no: int = 1,
        num_of_rows: int = 10,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """searchStay2 — 숙박 목록."""
        extra: dict[str, str] = {"areaCode": area_code}
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        return self._list(
            "searchStay2",
            extra,
            page_no=page_no,
            num_of_rows=num_of_rows,
        )

    def search_attractions(
        self,
        *,
        area_code: str,
        sigungu_code: str = "",
        content_type_id: str = CONTENT_TYPE_ATTRACTION,
        page_no: int = 1,
        num_of_rows: int = 10,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """areaBasedList2 — 지역별 관광지·문화시설."""
        if not area_code:
            return [], "", "", 0
        extra: dict[str, str] = {
            "areaCode": area_code,
            "contentTypeId": content_type_id,
        }
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        return self._list(
            "areaBasedList2",
            extra,
            page_no=page_no,
            num_of_rows=num_of_rows,
        )

    def search_attractions_mixed(
        self,
        *,
        area_code: str,
        num_of_rows: int = 8,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """관광지(12) + 문화시설(14) 병합 (중복 content_id 제거)."""
        merged: list[TourApiItem] = []
        seen: set[str] = set()
        last_code, last_msg, total = "", "", 0
        per_type = max(4, num_of_rows // 2)
        for ctype in (CONTENT_TYPE_ATTRACTION, CONTENT_TYPE_CULTURE):
            batch, code, msg, count = self.search_attractions(
                area_code=area_code,
                content_type_id=ctype,
                num_of_rows=per_type,
            )
            last_code, last_msg = code, msg
            total += count
            for item in batch:
                if item.content_id and item.content_id in seen:
                    continue
                if item.content_id:
                    seen.add(item.content_id)
                merged.append(item)
                if len(merged) >= num_of_rows:
                    break
            if len(merged) >= num_of_rows:
                break
        return merged[:num_of_rows], last_code, last_msg, total

    def probe(self) -> dict[str, Any]:
        """searchFestival2 / searchStay2 연결·응답 요약 (디버그용)."""
        from datetime import timedelta

        today = date.today()
        # 프로브: 당해 연말까지 (짧은 구간은 행사 0건일 수 있음)
        end = date(today.year, 12, 31)
        out: dict[str, Any] = {"configured": self.is_configured}

        if not self.is_configured:
            out["error"] = "INCHEONTRANSPORT_API_KEY missing"
            return out

        try:
            # areaCode 생략 시 전국 검색 (서울만 지정하면 기간 내 0건일 수 있음)
            festivals, fc, fm, ft = self.search_festival(
                start=today, end=end, num_of_rows=5
            )
            out["searchFestival2"] = {
                "result_code": fc,
                "result_msg": fm,
                "total_count": ft,
                "sample_count": len(festivals),
                "samples": [i.to_dict() for i in festivals[:3]],
            }
        except Exception as exc:
            out["searchFestival2"] = {"error": str(exc)}

        try:
            stays, sc, sm, st = self.search_stay(
                area_code=SEOUL_AREA_CODE, num_of_rows=5
            )
            out["searchStay2"] = {
                "result_code": sc,
                "result_msg": sm,
                "total_count": st,
                "sample_count": len(stays),
                "samples": [i.to_dict() for i in stays[:3]],
            }
        except Exception as exc:
            out["searchStay2"] = {"error": str(exc)}

        try:
            attractions, ac, am, at = self.search_attractions_mixed(
                area_code=SEOUL_AREA_CODE, num_of_rows=5
            )
            out["areaBasedList2"] = {
                "result_code": ac,
                "result_msg": am,
                "total_count": at,
                "sample_count": len(attractions),
                "samples": [i.to_dict() for i in attractions[:3]],
            }
        except Exception as exc:
            out["areaBasedList2"] = {"error": str(exc)}

        return out
