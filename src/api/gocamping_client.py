"""한국관광공사 고캠핑 정보 조회서비스 클라이언트.

공공데이터포털 인증키: PUBLIC_API_KEY (.env, data.go.kr 계정 공통)
Base: https://apis.data.go.kr/B551011/GoCamping
엔드포인트: basedList (캠핑장 기본 정보 목록)
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B551011/GoCamping"
MOBILE_OS = "ETC"
MOBILE_APP = "Japantour"

# induty 업종 코드
INDUTY_GENERAL = "일반야영장"
INDUTY_AUTO = "자동차야영장"
INDUTY_GLAMPING = "글램핑"
INDUTY_CARAVAN = "카라반"

# region key → GoCamping doNm 매핑 (API 응답 doNm 필드 기준)
# 주의: API 데이터 내에 구 행정명(강원도, 전라북도)과 신 행정명(강원특별자치도, 전북특별자치도)이
# 혼재하므로 둘 다 포함합니다.
#   강원도 402건 + 강원특별자치도 128건 = 총 530건
#   전라북도 101건 + 전북특별자치도 23건 = 총 124건
_REGION_DO_MAP: dict[str, list[str]] = {
    "seoul":        ["서울특별시"],
    "incheon":      ["인천광역시"],
    "gyeonggi":     ["경기도"],
    "gangwon":      ["강원도", "강원특별자치도"],          # 구명·신명 혼재
    "chungcheong":  ["충청북도", "충청남도"],
    "chungnam":     ["충청남도"],
    "chungbuk":     ["충청북도"],
    "daejeon":      ["대전광역시"],
    "sejong":       ["세종특별자치시"],
    "jeolla":       ["전라북도", "전북특별자치도", "전라남도"],
    "jeonbuk":      ["전라북도", "전북특별자치도"],        # 구명·신명 혼재
    "jeonnam":      ["전라남도"],
    "gwangju":      ["광주광역시"],
    "gyeongsang":   ["경상북도", "경상남도"],
    "gyeongbuk":    ["경상북도"],
    "gyeongnam":    ["경상남도"],
    "daegu":        ["대구광역시"],
    "ulsan":        ["울산광역시"],
    "busan":        ["부산광역시"],
    "jeju":         ["제주특별자치도"],
}


@dataclass(frozen=True)
class CampingItem:
    """고캠핑 basedList API 항목."""

    content_id: str
    name: str           # facltNm
    line_intro: str     # lineIntro
    induty: str         # 업종 (글램핑/일반야영장/자동차야영장/카라반)
    do_nm: str          # 도명
    sigungu_nm: str     # 시군구명
    addr1: str
    mapx: str           # 경도 (mapX)
    mapy: str           # 위도 (mapY)
    tel: str
    resve_url: str      # 예약 URL
    homepage: str
    first_image_url: str
    lct_cl: str         # 입지구분 (산,숲,계곡,강,바다 등)
    sbrs_cl: str        # 부대시설 (전기,무선인터넷,장작판매 등)
    animal_cmg_cl: str  # 반려동물 가능 여부
    oper_pd_cl: str     # 운영기간 (봄,여름,가을,겨울)
    manage_sttus: str   # 운영상태

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["maps_uri"] = self.maps_uri()
        return d

    def maps_uri(self) -> str:
        if not self.mapx or not self.mapy:
            return ""
        return (
            f"https://map.naver.com/p/search/{self.mapy},{self.mapx}"
            f"?c={self.mapx},{self.mapy},16,0,0,0,dh"
        )

    def to_tour_api_item(self) -> "TourApiItem":
        """router.py 호환용 TourApiItem으로 변환."""
        from src.api.visitkorea_client import TourApiItem

        induty_short = self.induty.split(",")[0].strip() if self.induty else ""
        label = f"[{induty_short}] " if induty_short else ""
        return TourApiItem(
            content_id=f"camping-{self.content_id}",
            content_type_id="camping",
            title=f"{label}{self.name}",
            addr1=self.addr1,
            addr2=f"{self.do_nm} {self.sigungu_nm}".strip(),
            mapx=self.mapx,
            mapy=self.mapy,
            tel=self.tel,
            first_image=self.first_image_url,
        )


def _service_key() -> str | None:
    return os.getenv("PUBLIC_API_KEY")


def _parse_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
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


def _camping_item_from_row(row: dict[str, Any]) -> CampingItem:
    return CampingItem(
        content_id=str(row.get("contentId", "")),
        name=str(row.get("facltNm", "") or "").strip(),
        line_intro=str(row.get("lineIntro", "") or "").strip(),
        induty=str(row.get("induty", "") or "").strip(),
        do_nm=str(row.get("doNm", "") or "").strip(),
        sigungu_nm=str(row.get("sigunguNm", "") or "").strip(),
        addr1=str(row.get("addr1", "") or "").strip(),
        mapx=str(row.get("mapX", "") or ""),
        mapy=str(row.get("mapY", "") or ""),
        tel=str(row.get("tel", "") or "").strip(),
        resve_url=str(row.get("resveUrl", "") or "").strip(),
        homepage=str(row.get("homepage", "") or "").strip(),
        first_image_url=str(row.get("firstImageUrl", "") or "").strip(),
        lct_cl=str(row.get("lctCl", "") or "").strip(),
        sbrs_cl=str(row.get("sbrsCl", "") or "").strip(),
        animal_cmg_cl=str(row.get("animalCmgCl", "") or "").strip(),
        oper_pd_cl=str(row.get("operPdCl", "") or "").strip(),
        manage_sttus=str(row.get("manageSttus", "") or "").strip(),
    )


class GoCampingClient:
    """한국관광공사 고캠핑 정보 조회서비스 클라이언트.

    인증키: PUBLIC_API_KEY (data.go.kr 공통키)
    전국 캠핑장 약 2,900개 데이터 제공.
    """

    def __init__(self, service_key: str | None = None, timeout: int = 15):
        self.service_key = service_key or _service_key()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.service_key)

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.service_key:
            raise ValueError("PUBLIC_API_KEY가 설정되지 않았습니다.")
        url = f"{BASE_URL}/{endpoint}"
        merged = {
            "serviceKey": self.service_key,
            "MobileOS": MOBILE_OS,
            "MobileApp": MOBILE_APP,
            "_type": "json",
            **params,
        }
        resp = requests.get(url, params=merged, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def search_by_region(
        self,
        do_nm: str = "",
        sigungu_nm: str = "",
        induty: str = "",
        num_of_rows: int = 10,
        page_no: int = 1,
    ) -> tuple[list[CampingItem], int]:
        """지역·업종별 캠핑장 목록 조회.

        Returns:
            (items, total_count)
        """
        params: dict[str, Any] = {"numOfRows": num_of_rows, "pageNo": page_no}
        if do_nm:
            params["doNm"] = do_nm
        if sigungu_nm:
            params["sigunguNm"] = sigungu_nm
        if induty:
            params["induty"] = induty

        try:
            raw = self._get("basedList", params)
        except Exception as exc:
            logger.warning("GoCamping basedList 실패 [doNm=%s induty=%s]: %s", do_nm, induty, exc)
            return [], 0

        rows = _parse_items(raw)
        total = int(((raw.get("response") or {}).get("body") or {}).get("totalCount", 0))
        items = [_camping_item_from_row(r) for r in rows]
        return items, total

    def search_active(
        self,
        num_of_rows: int = 10,
        page_no: int = 1,
    ) -> list[CampingItem]:
        """운영 중인 캠핑장 반환 (전국, 로컬 필터).

        Note: basedList API는 doNm/induty 쿼리 파라미터 필터를 지원하지 않아
        전국 목록을 가져온 뒤 로컬 필터링합니다.
        """
        items, _ = self.search_by_region(num_of_rows=num_of_rows, page_no=page_no)
        return [i for i in items if i.manage_sttus == "운영"]

    def search_for_vacation(
        self,
        region_keys: list[str],
        vacation_types: list[str],
        num_of_rows: int = 10,
    ) -> list["TourApiItem"]:
        """바캉스 플랜용 캠핑장 검색 → TourApiItem 리스트 반환.

        GoCamping basedList API가 doNm 서버 필터를 지원하지 않으므로
        페이지 단위로 가져온 뒤 do_nm·induty·운영상태를 로컬 필터링합니다.
        결과가 부족하면 최대 MAX_PAGES 페이지까지 자동으로 추가 조회합니다.

        Args:
            region_keys: traveler_profile의 regionAreaKeys (e.g. ["gangwon", "gyeonggi"])
            vacation_types: ["camping", ...] — "glamping" 포함 시 글램핑 우선 필터
            num_of_rows: 반환 최대 건수
        """
        if not self.is_configured:
            logger.warning("GoCamping: PUBLIC_API_KEY not configured")
            return []

        MAX_PAGES = 5   # 최대 5페이지(500건) 조회 — 모든 지역 커버 가능
        PAGE_SIZE = 100

        # 글램핑 키워드 → induty 로컬 필터
        raw_blob = " ".join(vacation_types).lower()
        want_glamping = "글램핑" in raw_blob or "glamping" in raw_blob

        # region_keys → 도명 집합 (로컬 필터용, 구명·신명 모두 포함)
        target_do: set[str] = set()
        for key in region_keys:
            target_do.update(_REGION_DO_MAP.get(key.lower(), []))

        out: list[TourApiItem] = []
        seen: set[str] = set()

        for page in range(1, MAX_PAGES + 1):
            items, total = self.search_by_region(num_of_rows=PAGE_SIZE, page_no=page)
            if not items:
                break

            for item in items:
                if item.manage_sttus != "운영":
                    continue
                if target_do and item.do_nm not in target_do:
                    continue
                if want_glamping and item.induty != INDUTY_GLAMPING:
                    continue
                k = f"{item.name}|{item.addr1}"
                if k in seen:
                    continue
                seen.add(k)
                out.append(item.to_tour_api_item())

            if len(out) >= num_of_rows:
                break
            # 전체 페이지 소진 시 종료
            if page * PAGE_SIZE >= total:
                break

        return out[:num_of_rows]
