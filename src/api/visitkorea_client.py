"""한국관광공사 관광정보 API (TourAPI 4.0 — JpnService2).

공공데이터포털 인증키: PUBLIC_API_KEY (.env, data.go.kr 계정 공통)
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

try:
    from django.core.cache import cache as _django_cache
    _CACHE_AVAILABLE = True
except ImportError:
    _django_cache = None  # type: ignore[assignment]
    _CACHE_AVAILABLE = False

_VK_CACHE_TTL = 7200  # 2시간 — TourAPI 관광지 데이터는 자주 바뀌지 않음

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B551011/JpnService2"
KTO_HUB_BASE_URL = "http://apis.data.go.kr/B551011/LocgoHubTarService1"
KTO_RELATED_BASE_URL = "http://apis.data.go.kr/B551011/TarRlteTarService1"
KTO_RESOURCE_DEMAND_BASE_URL = "http://apis.data.go.kr/B551011/AreaTarResDemService"
KTO_DIVERSITY_BASE_URL = "http://apis.data.go.kr/B551011/AreaTourDvsService"
KTO_GREEN_BASE_URL = "http://apis.data.go.kr/B551011/GreenTourService1"
KTO_ACCESSIBLE_BASE_URL = "http://apis.data.go.kr/B551011/KorWithService2"
KTO_KOR_BASE_URL = "http://apis.data.go.kr/B551011/KorService2"
KTO_PHOTO_BASE_URL = "http://apis.data.go.kr/B551011/PhotoGalleryService1"
MOBILE_OS = "ETC"
MOBILE_APP = "Japantour"

# 서울 areaCode (legacy) — ldongCode2 연동 전 기본값
SEOUL_AREA_CODE = "1"

# 위저드 sido 이름 → JpnService2 areaCode
WIZARD_SIDO_TO_AREA: dict[str, str] = {
    "서울특별시": "1",
    "인천광역시": "2",
    "대전광역시": "3",
    "대구광역시": "4",
    "광주광역시": "5",
    "부산광역시": "6",
    "울산광역시": "7",
    "세종특별자치시": "8",
    "경기도": "31",
    "강원특별자치도": "32",
    "강원도": "32",
    "충청북도": "33",
    "충청남도": "34",
    "경상북도": "35",
    "경상남도": "36",
    "전북특별자치도": "37",
    "전라북도": "37",
    "전라남도": "38",
    "제주특별자치도": "39",
    "제주도": "39",
}

# (area_code, 도시명 한글 키워드) → sigungu_code  (JpnService2 searchStay2)
_CITY_SIGUNGU: dict[tuple[str, str], str] = {
    ("31", "가평"): "1",  ("31", "고양"): "2",  ("31", "과천"): "3",
    ("31", "광명"): "4",  ("31", "광주"): "5",  ("31", "구리"): "6",
    ("31", "군포"): "7",  ("31", "남양주"): "9", ("31", "동두천"): "10",
    ("31", "부천"): "11", ("31", "성남"): "12", ("31", "수원"): "13",
    ("31", "시흥"): "14", ("31", "안산"): "15", ("31", "안성"): "16",
    ("31", "안양"): "17", ("31", "양주"): "18", ("31", "양평"): "19",
    ("31", "여주"): "20", ("31", "연천"): "21", ("31", "오산"): "22",
    ("31", "용인"): "23", ("31", "의왕"): "24", ("31", "의정부"): "25",
    ("31", "이천"): "26", ("31", "파주"): "27", ("31", "평택"): "28",
    ("31", "포천"): "29", ("31", "하남"): "30", ("31", "화성"): "31",
    ("32", "강릉"): "1",  ("32", "고성"): "2",  ("32", "동해"): "3",
    ("32", "삼척"): "4",  ("32", "속초"): "5",  ("32", "양구"): "6",
    ("32", "양양"): "7",  ("32", "영월"): "8",  ("32", "원주"): "9",
    ("32", "인제"): "10", ("32", "정선"): "11", ("32", "철원"): "12",
    ("32", "춘천"): "13", ("32", "태백"): "14", ("32", "평창"): "15",
    ("32", "홍천"): "16", ("32", "화천"): "17", ("32", "횡성"): "18",
    ("33", "괴산"): "1",  ("33", "단양"): "2",  ("33", "보은"): "3",
    ("33", "영동"): "4",  ("33", "옥천"): "5",  ("33", "음성"): "6",
    ("33", "제천"): "7",  ("33", "진천"): "8",  ("33", "청주"): "10",
    ("33", "충주"): "11", ("33", "증평"): "12",
    ("34", "공주"): "1",  ("34", "금산"): "2",  ("34", "논산"): "3",
    ("34", "당진"): "4",  ("34", "보령"): "5",  ("34", "부여"): "6",
    ("34", "서산"): "7",  ("34", "서천"): "8",  ("34", "아산"): "9",
    ("34", "예산"): "11", ("34", "천안"): "12", ("34", "청양"): "13",
    ("34", "태안"): "14", ("34", "홍성"): "15",
    ("35", "경산"): "1",  ("35", "경주"): "2",  ("35", "고령"): "3",
    ("35", "구미"): "4",  ("35", "김천"): "6",  ("35", "문경"): "7",
    ("35", "봉화"): "8",  ("35", "상주"): "9",  ("35", "성주"): "10",
    ("35", "안동"): "11", ("35", "영덕"): "12", ("35", "영양"): "13",
    ("35", "영주"): "14", ("35", "영천"): "15", ("35", "예천"): "16",
    ("35", "울릉"): "17", ("35", "울진"): "18", ("35", "의성"): "19",
    ("35", "청도"): "20", ("35", "청송"): "21", ("35", "칠곡"): "22",
    ("35", "포항"): "23",
    ("36", "거제"): "1",  ("36", "거창"): "2",  ("36", "고성"): "3",
    ("36", "김해"): "4",  ("36", "남해"): "5",  ("36", "밀양"): "7",
    ("36", "사천"): "8",  ("36", "산청"): "9",  ("36", "양산"): "10",
    ("36", "의령"): "12", ("36", "진주"): "13", ("36", "창녕"): "15",
    ("36", "창원"): "16", ("36", "통영"): "17", ("36", "하동"): "18",
    ("36", "함안"): "19", ("36", "함양"): "20", ("36", "합천"): "21",
    ("37", "고창"): "1",  ("37", "군산"): "2",  ("37", "김제"): "3",
    ("37", "남원"): "4",  ("37", "무주"): "5",  ("37", "부안"): "6",
    ("37", "순창"): "7",  ("37", "완주"): "8",  ("37", "익산"): "9",
    ("37", "임실"): "10", ("37", "장수"): "11", ("37", "전주"): "12",
    ("37", "정읍"): "13", ("37", "진안"): "14",
    ("38", "강진"): "1",  ("38", "고흥"): "2",  ("38", "곡성"): "3",
    ("38", "광양"): "4",  ("38", "구례"): "5",  ("38", "나주"): "6",
    ("38", "담양"): "7",  ("38", "목포"): "8",  ("38", "무안"): "9",
    ("38", "보성"): "10", ("38", "순천"): "11", ("38", "신안"): "12",
    ("38", "여수"): "13", ("38", "영광"): "16", ("38", "영암"): "17",
    ("38", "완도"): "18", ("38", "장성"): "19", ("38", "장흥"): "20",
    ("38", "진도"): "21", ("38", "함평"): "22", ("38", "해남"): "23",
    ("38", "화순"): "24",
    ("39", "서귀포"): "3", ("39", "제주"): "4",
}


def wizard_to_kto_codes(sido: str, sigungu: str) -> tuple[str, str]:
    """위저드 sido/sigungu 문자열 → (area_code, sigungu_code)."""
    area_code = WIZARD_SIDO_TO_AREA.get(sido.strip(), "")
    if not area_code:
        return "", ""
    sigungu_code = ""
    if sigungu and area_code:
        for (ac, city_kw), sgu in _CITY_SIGUNGU.items():
            if ac == area_code and city_kw in sigungu:
                sigungu_code = sgu
                break
    return area_code, sigungu_code

# TourAPI contentTypeId (JpnService2) — KorService2의 12/14와 다름
CONTENT_TYPE_ATTRACTION = "76"  # 관광지·명소
CONTENT_TYPE_CULTURE = "82"    # 음식점·카페 (JpnService2 A05)
CONTENT_TYPE_SHOPPING = "79"   # 쇼핑 (JpnService2 A04, 11,087건)


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
        """좌표 기반 Naver Map 링크 (mapx=경도, mapy=위도)."""
        if not self.mapx or not self.mapy:
            return ""
        return f"https://map.naver.com/p/search/{self.mapy},{self.mapx}?c={self.mapx},{self.mapy},16,0,0,0,dh"

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


@dataclass(frozen=True)
class KtoDataLabItem:
    """KTO 데이터랩/GW 계열 API의 유연한 행 포맷."""

    name: str
    area: str = ""
    address: str = ""
    code: str = ""
    related_name: str = ""
    related_code: str = ""
    rank: str = ""
    score: str = ""
    category: str = ""
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _service_key_from_env() -> str | None:
    return (
        os.getenv("PUBLIC_API_KEY")
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


def _pick(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _datalab_item_from_row(row: dict[str, Any]) -> KtoDataLabItem:
    name = _pick(
        row,
        "hubTatsNm",
        "hubTatsName",
        "tAtsNm",
        "trrsrtNm",
        "tourNm",
        "rlteTatsNm",
        "rlteTatsName",
        "galTitle",
        "galPhotographyLocation",
        "title",
        "name",
    )
    related_name = _pick(row, "rlteTatsNm", "rlteTatsName", "rlteTourNm")
    return KtoDataLabItem(
        name=name or related_name,
        area=_pick(row, "areaNm", "signguNm", "sigunguNm", "ldongSignguNm", "sidoNm"),
        address=_pick(row, "addr", "addr1", "address", "rdnmadr", "lnmadr"),
        code=_pick(row, "hubTatsCd", "tAtsCd", "contentid", "contentId", "trrsrtNo"),
        related_name=related_name,
        related_code=_pick(row, "rlteTatsCd", "rlteTatsId", "rlteContentId"),
        rank=_pick(row, "rank", "rnum", "rlteRank", "rn"),
        score=_pick(
            row,
            "score",
            "demand",
            "demandValue",
            "visitrNum",
            "touDivScore",
            "areaTourDemand",
            "tatsScre",
            "touDvsScore",
            "visitCount",
            "cnt",
        ),
        category=_pick(row, "ctgryNm", "cat1", "cat2", "cat3", "themeNm", "tatsSeNm"),
        raw=row,
    )


class KtoDataLabClient:
    """Optional KTO/Data.go.kr enrichment APIs used as itinerary context only."""

    def __init__(self, service_key: str | None = None, timeout: int = 20):
        self.service_key = service_key or _service_key_from_env()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.service_key)

    def _base_params(self) -> dict[str, str]:
        if not self.service_key:
            raise ValueError("KTO service key missing")
        return {
            "serviceKey": self.service_key,
            "MobileOS": MOBILE_OS,
            "MobileApp": MOBILE_APP,
            "_type": "json",
            "numOfRows": "10",
            "pageNo": "1",
        }

    def _get(
        self,
        base_url: str,
        operation: str,
        extra: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}/{operation}"
        params = {**self._base_params(), **(extra or {})}
        resp = requests.get(url, params=params, timeout=self.timeout)
        logger.info(
            "KTO DataLab %s HTTP %d - %s",
            operation,
            resp.status_code,
            {k: v for k, v in params.items() if k != "serviceKey"},
        )
        if not resp.ok:
            logger.warning("KTO DataLab %s body: %s", operation, resp.text[:400])
            resp.raise_for_status()
        data = resp.json()
        code, msg = _parse_header(data)
        if code and code not in ("00", "0000"):
            raise ValueError(f"KTO DataLab {operation} resultCode={code} msg={msg}")
        return data

    def _list(
        self,
        base_url: str,
        operations: tuple[str, ...],
        extra: dict[str, str] | None = None,
        *,
        page_no: int = 1,
        num_of_rows: int = 10,
    ) -> list[KtoDataLabItem]:
        last_error: Exception | None = None
        params = {
            "pageNo": str(page_no),
            "numOfRows": str(num_of_rows),
            **(extra or {}),
        }
        for operation in operations:
            try:
                raw = self._get(base_url, operation, params)
                return [
                    item
                    for item in (_datalab_item_from_row(r) for r in _parse_items(raw))
                    if item.name or item.related_name
                ]
            except Exception as exc:
                last_error = exc
                logger.info("KTO DataLab operation fallback %s failed: %s", operation, exc)
        if last_error:
            raise last_error
        return []

    def search_local_hub_attractions(
        self,
        *,
        area_code: str = "",
        sigungu_code: str = "",
        num_of_rows: int = 16,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if area_code:
            extra["areaCode"] = area_code
            extra["areaCd"] = area_code
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
            extra["signguCd"] = sigungu_code
        return self._list(
            KTO_HUB_BASE_URL,
            ("areaBasedList1", "areaBasedList"),
            extra,
            num_of_rows=num_of_rows,
        )

    def search_related_attractions(
        self,
        *,
        keyword: str = "",
        hub_code: str = "",
        area_code: str = "",
        num_of_rows: int = 16,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if keyword:
            extra["keyword"] = keyword
        if hub_code:
            extra["hubTatsCd"] = hub_code
            extra["tAtsCd"] = hub_code
        if area_code:
            extra["areaCode"] = area_code
            extra["areaCd"] = area_code
        return self._list(
            KTO_RELATED_BASE_URL,
            ("areaBasedList1", "areaBasedList", "searchKeyword1", "searchKeyword"),
            extra,
            num_of_rows=num_of_rows,
        )

    def search_resource_demand(
        self,
        *,
        area_code: str = "",
        num_of_rows: int = 10,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if area_code:
            extra["areaCode"] = area_code
            extra["areaCd"] = area_code
        return self._list(
            KTO_RESOURCE_DEMAND_BASE_URL,
            ("areaTarSvcDemList", "areaCulResDemList", "areaBasedList1", "areaBasedList"),
            extra,
            num_of_rows=num_of_rows,
        )

    def search_diversity(
        self,
        *,
        area_code: str = "",
        num_of_rows: int = 10,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if area_code:
            extra["areaCode"] = area_code
            extra["areaCd"] = area_code
        return self._list(
            KTO_DIVERSITY_BASE_URL,
            (
                "areaTouristDvsList",
                "areaTourCsmDvsList",
                "areaIntlDvsList",
                "areaBasedList1",
                "areaBasedList",
            ),
            extra,
            num_of_rows=num_of_rows,
        )

    def search_green_tour(
        self,
        *,
        area_code: str = "",
        sigungu_code: str = "",
        num_of_rows: int = 10,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if area_code:
            extra["areaCode"] = area_code
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        return self._list(
            KTO_GREEN_BASE_URL,
            ("areaBasedList1", "areaBasedSyncList1"),
            extra,
            num_of_rows=num_of_rows,
        )

    def search_accessible_tour(
        self,
        *,
        area_code: str = "",
        sigungu_code: str = "",
        keyword: str = "",
        num_of_rows: int = 10,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if area_code:
            extra["areaCode"] = area_code
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        if keyword:
            extra["keyword"] = keyword
        return self._list(
            KTO_ACCESSIBLE_BASE_URL,
            ("searchKeyword2", "areaBasedList2", "areaBasedSyncList2"),
            extra,
            num_of_rows=num_of_rows,
        )

    def search_kor_tour_info(
        self,
        *,
        area_code: str = "",
        sigungu_code: str = "",
        keyword: str = "",
        num_of_rows: int = 10,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if area_code:
            extra["areaCode"] = area_code
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        if keyword:
            extra["keyword"] = keyword
        return self._list(
            KTO_KOR_BASE_URL,
            ("searchKeyword2", "areaBasedList2", "areaBasedSyncList2"),
            extra,
            num_of_rows=num_of_rows,
        )

    def search_photo_gallery(
        self,
        *,
        keyword: str = "",
        num_of_rows: int = 8,
    ) -> list[KtoDataLabItem]:
        extra: dict[str, str] = {}
        if keyword:
            extra["keyword"] = keyword
        return self._list(
            KTO_PHOTO_BASE_URL,
            ("gallerySearchList1", "galleryList1"),
            extra,
            num_of_rows=num_of_rows,
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
            raise ValueError("PUBLIC_API_KEY가 설정되지 않았습니다.")
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

    def search_keyword(
        self,
        keyword: str,
        *,
        area_code: str = "",
        sigungu_code: str = "",
        content_type_id: str = "80",  # 80 = 숙박 (JpnService2)
        page_no: int = 1,
        num_of_rows: int = 10,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """searchKeyword2 — 키워드로 관광정보 검색."""
        extra: dict[str, str] = {"keyword": keyword}
        if content_type_id:
            extra["contentTypeId"] = content_type_id
        if area_code:
            extra["areaCode"] = area_code
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        return self._list(
            "searchKeyword2",
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
        cache_key = f"vk:abl2:{area_code}:{sigungu_code}:{content_type_id}:{num_of_rows}:{page_no}"
        if _CACHE_AVAILABLE:
            cached = _django_cache.get(cache_key)
            if cached is not None:
                logger.debug("VK cache hit: %s", cache_key)
                return cached  # type: ignore[return-value]
        extra: dict[str, str] = {
            "areaCode": area_code,
            "contentTypeId": content_type_id,
        }
        if sigungu_code:
            extra["sigunguCode"] = sigungu_code
        result = self._list(
            "areaBasedList2",
            extra,
            page_no=page_no,
            num_of_rows=num_of_rows,
        )
        if _CACHE_AVAILABLE:
            _django_cache.set(cache_key, result, _VK_CACHE_TTL)
        return result

    def search_attractions_mixed(
        self,
        *,
        area_code: str,
        sigungu_code: str = "",
        num_of_rows: int = 30,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """JpnService2 관광지·명소(76) 조회 — 전 페이지 수집 후 반환."""
        return self.search_attractions(
            area_code=area_code,
            sigungu_code=sigungu_code,
            content_type_id=CONTENT_TYPE_ATTRACTION,
            num_of_rows=num_of_rows,
        )

    def search_shopping(
        self,
        *,
        area_code: str,
        num_of_rows: int = 20,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """JpnService2 쇼핑(79) 조회 — 쇼핑몰·백화점·시장 등 A04 카테고리."""
        return self.search_attractions(
            area_code=area_code,
            content_type_id=CONTENT_TYPE_SHOPPING,
            num_of_rows=num_of_rows,
        )

    def search_green_spots(
        self,
        *,
        area_code: str,
        num_of_rows: int = 20,
    ) -> tuple[list[TourApiItem], str, str, int]:
        """GreenTourService1 생태관광지 조회 — 자연/힐링 관심사 선택 시 관광지 풀에 추가."""
        if not area_code:
            return [], "", "", 0
        if not self.service_key:
            raise ValueError("PUBLIC_API_KEY가 설정되지 않았습니다.")
        cache_key = f"vk:green:{area_code}:{num_of_rows}"
        if _CACHE_AVAILABLE:
            cached = _django_cache.get(cache_key)
            if cached is not None:
                logger.debug("VK green cache hit: %s", cache_key)
                return cached  # type: ignore[return-value]
        params: dict[str, str] = {
            "serviceKey": self.service_key,
            "MobileOS": MOBILE_OS,
            "MobileApp": MOBILE_APP,
            "_type": "json",
            "numOfRows": str(num_of_rows),
            "pageNo": "1",
            "areaCode": area_code,
        }
        url = f"{KTO_GREEN_BASE_URL}/areaBasedList1"
        resp = requests.get(url, params=params, timeout=self.timeout)
        logger.info(
            "GreenTour areaBasedList1 HTTP %d — areaCode=%s",
            resp.status_code,
            area_code,
        )
        if not resp.ok:
            logger.warning("GreenTour areaBasedList1 body: %s", resp.text[:400])
            resp.raise_for_status()
        raw = resp.json()
        code, msg = _parse_header(raw)
        if code and code not in ("00", "0000"):
            raise ValueError(f"GreenTour areaBasedList1 resultCode={code} msg={msg}")
        body = (raw.get("response") or {}).get("body") or {}
        total = int(body.get("totalCount") or 0)
        rows = _parse_items(raw)
        result = [_item_from_row(r) for r in rows], code, msg, total
        if _CACHE_AVAILABLE:
            _django_cache.set(cache_key, result, _VK_CACHE_TTL)
        return result

    def probe(self) -> dict[str, Any]:
        """searchFestival2 / searchStay2 연결·응답 요약 (디버그용)."""
        from datetime import timedelta

        today = date.today()
        # 프로브: 당해 연말까지 (짧은 구간은 행사 0건일 수 있음)
        end = date(today.year, 12, 31)
        out: dict[str, Any] = {"configured": self.is_configured}

        if not self.is_configured:
            out["error"] = "PUBLIC_API_KEY missing"
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
