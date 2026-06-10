"""Google Places API client for nearby travel recommendations."""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass, replace
from typing import Iterable

import requests

logger = logging.getLogger(__name__)


PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_GET_URL = "https://places.googleapis.com/v1/places/{place_id}"
PHOTO_BASE_URL = "https://places.googleapis.com/v1/{name}/media"

# 한국 영토 바운딩 박스 — Places API locationRestriction에 사용
# regionCode:"KR"은 soft bias일 뿐이므로 rectangle로 일본 결과를 완전 차단
KR_LOCATION_RESTRICTION: dict = {
    "rectangle": {
        "low": {"latitude": 33.0, "longitude": 124.0},
        "high": {"latitude": 39.5, "longitude": 132.0},
    }
}

DEFAULT_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.rating",
        "places.userRatingCount",
        "places.currentOpeningHours",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.priceLevel",
        "places.photos",
        "places.servesBreakfast",
        "places.dineIn",
    ]
)

_PRICE_DISPLAY: dict[str, str] = {
    "PRICE_LEVEL_FREE": "무료",
    "PRICE_LEVEL_INEXPENSIVE": "¥",
    "PRICE_LEVEL_MODERATE": "¥¥",
    "PRICE_LEVEL_EXPENSIVE": "¥¥¥",
    "PRICE_LEVEL_VERY_EXPENSIVE": "¥¥¥¥",
}


@dataclass(frozen=True)
class NearbyPlace:
    """Normalized place data returned by Google Places."""

    name: str
    category: str
    address: str
    latitude: float | None
    longitude: float | None
    rating: float | None
    user_rating_count: int | None
    google_maps_uri: str | None
    is_open_now: bool | None
    distance_meters: int | None
    place_id: str | None = None          # ChIJ… (Places API id)
    price_level: str | None = None       # e.g. "¥¥" (변환 후 표시용)
    photo_name: str | None = None        # places/.../photos/... (proxy용)
    serves_breakfast: bool | None = None
    has_restaurant: bool | None = None   # dineIn 필드
    search_area: str | None = None       # itinerary 검색 시 에리어 라벨


# 食事候補から除外（ウェディングホール・イベント会場など）
_MEAL_NAME_EXCLUDE_RE = re.compile(
    r"ウェディング|웨딩|婚礼|wedding|"
    r"コンベンション|컨벤션|convention|"
    r"結婚式|예식|식장|ウェディングホール|웨딩홀|"
    r"イベントホール|event\s*venue|宴会場|연회장|"
    r"葬儀|장례|funeral|チャペル|예식장|"
    r"휴게소|고속도로\s*휴게소|SA\b|highway\s*rest\s*stop",  # 고속도로 휴게소 제외
    re.IGNORECASE,
)
_DELIVERY_ONLY_RE = re.compile(
    r"배달\s*전용|배달전용|배달\s*만|デリバリー専門|delivery\s*only|"
    r"テイクアウト専門|포장\s*전문|出前専門|テイクアウトのみ|"
    r"takeaway\s*only|ghost\s*kitchen",
    re.IGNORECASE,
)
_CIVIC_OFFICE_RE = re.compile(
    r"구청|시청|군청|도청|읍사무소|면사무소|동사무소|주민센터|행정복지센터|"
    r"city\s*hall|district\s*office|community\s*service\s*center",
    re.IGNORECASE,
)
# 통신사 대리점·약국·부동산 등 명백한 비식음료 업종 (Naver 검색 오진 방지)
_NON_FOOD_SHOP_RE = re.compile(
    r"(SK\s*텔레콤|LG\s*유플러스|KT\s*플라자|KT\s*대리점|"
    r"삼성\s*디지털\s*프라자|갤럭시스토어|애플스토어|"
    r"다이소|올리브영|CU\s*편의점|GS\s*25|세븐일레븐|"
    r"약국|Pharmacy|부동산|공인중개사|헬스장|피트니스|"
    r"미용실|헤어샵|네일샵|마사지\s*숍|안경원|렌즈샵)",
    re.IGNORECASE,
)
# 여행 추천 불필요 — 전 세계 어디서나 있는 글로벌 패스트푸드 체인
_GLOBAL_FAST_FOOD_RE = re.compile(
    r"^(버거킹|맥도날드|McDonald|KFC|kfc|서브웨이|Subway|피자헛|Pizza\s*Hut|"
    r"도미노\s*피자|Domino|쉐이크쉑|Shake\s*Shack|파이브가이즈|Five\s*Guys|"
    r"웬디스?|Wendy|버거\s*킹|Burger\s*King)",
    re.IGNORECASE,
)
_MEAL_TYPE_EXCLUDE = frozenset({
    "wedding_venue",
    "event_venue",
    "convention_center",
    "conference_center",
    "banquet_hall",
    "church",
    "hindu_temple",
    "mosque",
    "cemetery",
    "corporate_office",
})
_MEAL_TYPE_ALLOW = frozenset({
    "restaurant",
    "cafe",
    "coffee_shop",
    "bakery",
    "bar",
    "meal_takeaway",
    "fast_food_restaurant",
    "korean_restaurant",
    "japanese_restaurant",
    "brunch_restaurant",
})

_NON_RESTAURANT_VENUE_RE = re.compile(
    r"(쇼핑몰|백화점|아울렛|복합쇼핑몰|패션몰|몰\b|스퀘어|스트리트|"
    r"shopping\s*mall|department\s*store|outlet|square|street)",
    re.I,
)


def _min_meal_place_rating() -> float:
    raw = os.getenv("MIN_MEAL_PLACE_RATING", "4.0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 4.0


def meets_min_meal_rating(place: NearbyPlace) -> bool:
    """Google rating below threshold → excluded.
    Naver-only places (no Google rating) are accepted when they have a
    naver_score quality signal instead of a Google-style star rating."""
    minimum = _min_meal_place_rating()
    if place.rating is not None:
        return float(place.rating) >= minimum
    # Naver Search results don't carry Google ratings; accept them when
    # naver_score is present (indicates at least some discoverability signal).
    naver_score = getattr(place, "naver_score", None)
    if naver_score is not None:
        return True
    return False


def is_suitable_meal_place(place: NearbyPlace) -> bool:
    """昼食・夕食に使える店か（ウェディングホール等を除外）。"""
    name = (place.name or "").strip()
    addr = (place.address or "").strip()
    blob = f"{name} {addr}"
    if _CIVIC_OFFICE_RE.search(blob):
        return False
    if _GLOBAL_FAST_FOOD_RE.search(name):
        return False
    if _NON_FOOD_SHOP_RE.search(name):
        return False
    if _MEAL_NAME_EXCLUDE_RE.search(blob) or _DELIVERY_ONLY_RE.search(blob):
        return False
    # Naver 검색 결과는 블로그 리뷰 최소치 미달 시 제외 (통신사/잡화점 오진 방지)
    naver_score = getattr(place, "naver_score", None)
    blog_count = getattr(place, "blog_review_count", None)
    if naver_score is not None and blog_count is not None and blog_count < 30:
        return False

    cat = (place.category or "").strip().lower()
    if cat in _MEAL_TYPE_EXCLUDE:
        return False
    if _NON_RESTAURANT_VENUE_RE.search(f"{name} {addr} {cat}") and cat not in _MEAL_TYPE_ALLOW:
        return False

    if cat and cat not in _MEAL_TYPE_ALLOW:
        if place.has_restaurant is False:
            return False
        if any(
            k in blob.lower()
            for k in ("wedding", "ウェディング", "웨딩", "컨벤션", "コンベンション")
        ):
            return False

    if place.has_restaurant is False and cat not in _MEAL_TYPE_ALLOW:
        return False

    return True


def filter_meal_places(places: list[NearbyPlace]) -> list[NearbyPlace]:
    return [
        p for p in places
        if is_suitable_meal_place(p) and meets_min_meal_rating(p)
    ]


def _resolve_api_key(explicit: str | None = None) -> str | None:
    """GOOGLE_HOTELS_API_KEY 우선, 없으면 GOOGLE_MAPS_API_KEY."""
    return (
        explicit
        or os.getenv("GOOGLE_HOTELS_API_KEY")
        or os.getenv("GOOGLE_MAPS_API_KEY")
    )


class GooglePlacesClient:
    """Small wrapper around Places API Nearby Search (New)."""

    def __init__(self, api_key: str | None = None, timeout: int = 12):
        self.api_key = _resolve_api_key(api_key)
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search_nearby(
        self,
        latitude: float,
        longitude: float,
        included_types: Iterable[str],
        radius_meters: int = 1000,
        max_results: int = 8,
        language_code: str = "ja",
    ) -> list[NearbyPlace]:
        """Search nearby places and normalize the response."""
        if not self.api_key:
            raise ValueError("Google API key is not configured.")

        radius = max(1, min(int(radius_meters), 50000))
        body = {
            "includedTypes": list(included_types),
            "maxResultCount": max(1, min(int(max_results), 20)),
            "rankPreference": "POPULARITY",
            "languageCode": language_code,
            "regionCode": "KR",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius),
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
        }

        response = requests.post(
            PLACES_NEARBY_URL, json=body, headers=headers, timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        return [
            self._normalize_place(place, origin_latitude=latitude, origin_longitude=longitude)
            for place in data.get("places", [])
        ]

    def search_by_text(
        self,
        text_query: str,
        max_results: int = 5,
        language_code: str = "ja",
        region_code: str = "KR",
        included_type: str | None = None,
        page_token: str | None = None,
        location_restriction: dict | None = None,
    ) -> tuple[list[NearbyPlace], str | None]:
        """텍스트 쿼리로 장소 검색 (예: '성수동 맛집', '명동 호텔').

        location_restriction: Places API locationRestriction dict (rectangle or circle).
          None → API default (regionCode bias only).
          KR_LOCATION_RESTRICTION → 한국 바운딩 박스로 결과를 한국으로 제한.

        Returns:
            (places, next_page_token) — next_page_token is None when no more pages.
        """
        if not self.api_key:
            raise ValueError("Google API key is not configured.")

        body: dict = {
            "textQuery": text_query,
            "maxResultCount": max(1, min(int(max_results), 20)),
            "languageCode": language_code,
            "regionCode": region_code,
        }
        if location_restriction:
            body["locationRestriction"] = location_restriction
        if included_type:
            body["includedType"] = included_type
        if page_token:
            body["pageToken"] = page_token

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
        }

        response = requests.post(
            PLACES_TEXT_SEARCH_URL, json=body, headers=headers, timeout=self.timeout
        )
        logger.info("Places textSearch HTTP %d — query=%r", response.status_code, text_query)
        if not response.ok:
            logger.warning("Places textSearch error body: %s", response.text[:400])
        response.raise_for_status()
        data = response.json()
        raw_places = data.get("places", [])
        next_token = data.get("nextPageToken") or None
        logger.info(
            "Places textSearch returned %d places (has_next=%s)",
            len(raw_places),
            bool(next_token),
        )
        places = [self._normalize_place(place) for place in raw_places]
        return places, next_token

    def search_by_text_all(
        self,
        text_query: str,
        *,
        max_total: int = 60,
        language_code: str = "ja",
        region_code: str = "KR",
        included_type: str | None = None,
        location_restriction: dict | None = None,
    ) -> list[NearbyPlace]:
        """Text Search 전 페이지 수집 (API 상한 약 60건)."""
        cap = max(1, min(int(max_total), 60))
        collected: list[NearbyPlace] = []
        seen: set[str] = set()
        page_token: str | None = None

        while len(collected) < cap:
            batch, page_token = self.search_by_text(
                text_query,
                max_results=20,
                language_code=language_code,
                region_code=region_code,
                included_type=included_type,
                page_token=page_token,
                location_restriction=location_restriction,
            )
            if not batch:
                break
            for place in batch:
                key = f"{place.name}|{place.address}"
                if key in seen:
                    continue
                seen.add(key)
                collected.append(place)
                if len(collected) >= cap:
                    break
            if not page_token:
                break

        return collected

    def get_place_by_id(
        self,
        place_id: str,
        language_code: str = "ja",
    ) -> NearbyPlace | None:
        """Places API (New) Place Details — ChIJ… place id."""
        if not self.is_configured or not place_id:
            return None
        pid = place_id.strip()
        if pid.startswith("places/"):
            pid = pid.split("/", 1)[1]
        url = PLACES_GET_URL.format(place_id=pid)
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
        }
        try:
            response = requests.get(
                url,
                headers=headers,
                params={"languageCode": language_code},
                timeout=self.timeout,
            )
            if not response.ok:
                logger.warning(
                    "get_place_by_id HTTP %s place_id=%r body=%s",
                    response.status_code,
                    pid[:24],
                    response.text[:200],
                )
                return None
            data = response.json()
            return self._normalize_place(data)
        except Exception as exc:
            logger.warning("get_place_by_id failed %r: %s", pid[:24], exc)
            return None

    def find_for_plan_item(
        self,
        maps_url: str,
        query: str = "",
        language_code: str = "ja",
        region_hint: str = "",
    ) -> NearbyPlace | None:
        """プラン内 Maps URL + 店名ラベルから Places 詳細を取得.

        한국 바운딩 박스(KR_LOCATION_RESTRICTION)를 항상 적용해
        일본 동일명 지점(예: 도쿄 신오쿠보 한국식당)이 반환되지 않도록 한다.
        """
        if not self.is_configured:
            return None
        target_cid = extract_maps_cid(maps_url)
        q = normalize_plan_query_label(query)
        place_id = extract_place_id_from_maps_url(maps_url)

        if place_id:
            found = self.get_place_by_id(place_id, language_code=language_code)
            if found:
                return _attach_request_maps_uri(found, maps_url)

        if not q and not target_cid:
            return None

        # CID is known but no text label — attempt CID-based lookup
        if not q and target_cid:
            return self._find_by_cid(target_cid, language_code=language_code, maps_url=maps_url)

        search_queries = _plan_item_search_queries(q, region_hint=region_hint)
        for tq in search_queries:
            try:
                results, _ = self.search_by_text(
                    text_query=tq,
                    max_results=10,
                    language_code=language_code,
                    location_restriction=KR_LOCATION_RESTRICTION,
                )
            except Exception as exc:
                logger.warning("find_for_plan_item search %r: %s", tq, exc)
                continue
            if not results:
                continue

            if target_cid:
                for place in results:
                    if maps_urls_same_cid(place.google_maps_uri, maps_url):
                        return _attach_request_maps_uri(place, maps_url)

            for place in results:
                if _place_matches_query_label(place, q):
                    return _attach_request_maps_uri(place, maps_url)

        return None

    def _find_by_cid(
        self,
        cid: str,
        language_code: str = "ja",
        maps_url: str = "",
    ) -> NearbyPlace | None:
        """CID のみで장소を検索 (クエリラベルがない場合のフォールバック)."""
        try:
            results, _ = self.search_by_text(
                text_query=f"cid:{cid}",
                max_results=3,
                language_code=language_code,
                location_restriction=KR_LOCATION_RESTRICTION,
            )
            if results:
                return _attach_request_maps_uri(results[0], maps_url)
        except Exception as exc:
            logger.warning("_find_by_cid cid=%s: %s", cid, exc)
        return None

    def _normalize_place(
        self,
        place: dict,
        origin_latitude: float | None = None,
        origin_longitude: float | None = None,
    ) -> NearbyPlace:
        location = place.get("location") or {}
        place_latitude = location.get("latitude")
        place_longitude = location.get("longitude")
        distance = None
        if (
            place_latitude is not None
            and place_longitude is not None
            and origin_latitude is not None
            and origin_longitude is not None
        ):
            distance = round(
                _haversine_meters(
                    origin_latitude, origin_longitude,
                    place_latitude, place_longitude,
                )
            )

        opening_hours = place.get("currentOpeningHours") or {}
        raw_price = place.get("priceLevel")

        # 첫 번째 사진 이름 추출
        photos = place.get("photos") or []
        photo_name = photos[0].get("name") if photos else None

        raw_id = str(place.get("id") or "")
        place_id = raw_id.split("/", 1)[-1] if raw_id else None

        return NearbyPlace(
            name=(place.get("displayName") or {}).get("text", "이름 없음"),
            category=place.get("primaryType", "place"),
            address=place.get("formattedAddress", ""),
            latitude=place_latitude,
            longitude=place_longitude,
            rating=place.get("rating"),
            user_rating_count=place.get("userRatingCount"),
            google_maps_uri=place.get("googleMapsUri"),
            place_id=place_id,
            is_open_now=opening_hours.get("openNow"),
            distance_meters=distance,
            price_level=_PRICE_DISPLAY.get(raw_price) if raw_price else None,
            photo_name=photo_name,
            serves_breakfast=place.get("servesBreakfast"),
            has_restaurant=place.get("dineIn"),
        )


def normalize_plan_query_label(query: str) -> str:
    """플랜 enrich용 — 昼食：성심당(…) → 성심당."""
    t = " ".join((query or "").split()).strip()
    t = re.sub(r"^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*", "", t)
    t = re.sub(
        r"^(?:"
        r"昼食|午後|午前|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事|"
        r"점심|저녁|아침|오전|오후|식사"
        r")[：:\s]+",
        "",
        t,
        flags=re.UNICODE,
    )
    t = re.sub(r"^【[^】]*】\s*", "", t)
    sports_venue_patterns = (
        "잠실야구장", "고척스카이돔", "사직야구장", "대구 삼성라이온즈파크",
        "삼성라이온즈파크", "NC파크", "엔씨파크", "광주기아챔피언스필드",
        "기아챔피언스필드", "한화생명볼파크", "수원KT위즈파크", "KT위즈파크",
        "SSG랜더스필드", "랜더스필드", "문학야구장",
        "잠실실내체육관", "서울월드컵경기장", "상암월드컵경기장",
    )
    compact = t.replace(" ", "")
    for venue in sports_venue_patterns:
        if venue.replace(" ", "") in compact:
            return venue
    if re.fullmatch(r"(?:KBO|KBL|KOVO|K[-\s]?リーグ|프로야구|プロ野球|野球観戦|スポーツ観戦).{0,20}", t, re.I):
        return ""
    m = re.match(r"^(.+?)[（(]([^）)]+)[）)]", t)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        if len(a) >= 2:
            t = a
        elif len(b) >= 2:
            t = b
    t = re.sub(r"[（(][^）)]*[）)]", "", t).strip()
    t = re.sub(r"\s*본점.*$", "", t).strip()
    t = re.sub(r"\s*本店.*$", "", t).strip()
    return t


def _normalize_label_key(s: str) -> str:
    return re.sub(r"[^\w\u3131-\uD79D぀-ヿ가-힣]", "", (s or ""), flags=re.UNICODE).lower()


def _place_matches_query_label(place: NearbyPlace, query: str) -> bool:
    ql = _normalize_label_key(normalize_plan_query_label(query))
    if len(ql) < 2:
        return False
    blob = _normalize_label_key(place.name)
    if not blob:
        return False
    return ql in blob or blob in ql or blob.startswith(ql[: max(4, len(ql) // 2)])


def _plan_item_search_queries(query: str, region_hint: str = "") -> list[str]:
    q = normalize_plan_query_label(query)
    if not q:
        return []
    variants: list[str] = [q]
    hint = normalize_plan_query_label(region_hint) or (region_hint or "").strip()
    if hint:
        for token in re.split(r"[,、·/\s]+", hint):
            token = token.strip()
            if len(token) >= 2:
                variants.append(f"{q} {token}")
    if "성심당" in q or "성심" in q:
        variants.extend(["성심당 대전", "성심당 본점"])
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out[:6]


def _attach_request_maps_uri(place: NearbyPlace, maps_url: str) -> NearbyPlace:
    """프론트가 본문 cid URL로 lookup — 요청 URL을 google_maps_uri에 유지."""
    uri = (maps_url or "").strip() or place.google_maps_uri
    return replace(place, google_maps_uri=uri)


def extract_place_id_from_maps_url(maps_url: str) -> str | None:
    """Map URL에서 ChIJ place id 추출."""
    if not maps_url:
        return None
    m = re.search(r"[?&]place_id=([A-Za-z0-9_-]+)", maps_url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"place_id[=:]([A-Za-z0-9_-]+)", maps_url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(ChIJ[A-Za-z0-9_-]{10,})", maps_url)
    if m:
        return m.group(1)
    return None


def extract_maps_cid(maps_url: str) -> str | None:
    """Map URL の cid パラメータを抽出 (十進数・十六進数両対応)."""
    if not maps_url:
        return None
    # Standard ?cid=DECIMAL
    match = re.search(r"[?&]cid=(\d+)", maps_url)
    if match:
        return match.group(1)
    # Modern data= URL: !1s0xLOC:0xCID! — second hex part is the decimal CID
    # Also handles /ftid=0xLOC:0xCID query param
    match = re.search(r"(?:!1s|ftid=)0x[0-9a-f]+:0x([0-9a-f]+)", maps_url, re.I)
    if match:
        try:
            return str(int(match.group(1), 16))
        except ValueError:
            pass
    return None


def maps_urls_same_cid(a: str | None, b: str | None) -> bool:
    ca, cb = extract_maps_cid(a or ""), extract_maps_cid(b or "")
    if ca and cb:
        return ca == cb
    if not a or not b:
        return False
    return a.split("&g_mp=")[0].rstrip("/") == b.split("&g_mp=")[0].rstrip("/")


def recommend_nearby_places(
    latitude: float,
    longitude: float,
    radius_meters: int = 1000,
    language_code: str = "ja",
) -> dict[str, list[NearbyPlace]]:
    """Return tourist attractions and food/cafe spots near the given coordinates."""
    client = GooglePlacesClient()
    attractions = client.search_nearby(
        latitude=latitude,
        longitude=longitude,
        included_types=["tourist_attraction"],
        radius_meters=radius_meters,
        max_results=6,
        language_code=language_code,
    )
    cafes = client.search_nearby(
        latitude=latitude,
        longitude=longitude,
        included_types=["restaurant", "cafe"],
        radius_meters=radius_meters,
        max_results=6,
        language_code=language_code,
    )
    return {
        "tourist_attractions": _rank_places(attractions),
        "cafes": _rank_places(cafes),
    }


def _rank_places(places: list[NearbyPlace]) -> list[NearbyPlace]:
    def score(place: NearbyPlace) -> tuple[float, int]:
        rating = place.rating or 0.0
        review_weight = min(place.user_rating_count or 0, 1000) / 1000
        distance_penalty = (place.distance_meters or 50000) / 50000
        open_bonus = 0.3 if place.is_open_now else 0.0
        return (rating + review_weight + open_bonus - distance_penalty, -(place.distance_meters or 50000))

    return sorted(places, key=score, reverse=True)


def _haversine_meters(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    earth_radius_meters = 6371000
    lat1 = math.radians(latitude1)
    lat2 = math.radians(latitude2)
    delta_lat = math.radians(latitude2 - latitude1)
    delta_lon = math.radians(longitude2 - longitude1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_meters * c
