"""Itinerary place query construction and candidate merging.

일정용 장소 쿼리 빌더, 후보 병합, 공통 place classifier.
router.py에서 추출한 함수 모음 — 동작은 완전히 동일하다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api.places_client import NearbyPlace


# ─── 지역별 고정 추천 장소 ─────────────────────────────────────────────────────
# region_cities_text 에 해당 키워드가 포함될 때 우선 검색에 추가됨
# 형식: { "감지 키워드": [("장소명", "검색보조어"), ...] }
_REGION_FEATURED_SPOTS: dict[str, list[tuple[str, str]]] = {
    "강북": [("안토리조트", "강북")],
}

# ─── Place classifier ─────────────────────────────────────────────────────────

def _is_cafe_candidate_place(place: NearbyPlace) -> bool:
    from src.chain.router import (  # lazy import
        _is_fortune_telling_place,
        _CAFE_EXCLUDE_BY_NAME_RE,
    )
    if _is_fortune_telling_place(place):
        return False
    place_name = (place.name or "").lower()
    if _CAFE_EXCLUDE_BY_NAME_RE.search(place_name):
        return False
    name_cat = f"{place.name} {place.category}".lower()
    return any(
        kw in name_cat
        for kw in ("카페", "커피", "coffee", "cafe", "베이커리", "디저트", "빙수", "スイーツ", "ベーカリー")
    )


def _is_meal_candidate_place(place: NearbyPlace) -> bool:
    from src.chain.router import meets_min_meal_rating, _place_blob  # lazy import
    if not meets_min_meal_rating(place):
        return False
    cat = (place.category or "").lower()
    if cat in ("tourist_attraction", "park", "museum", "shopping_mall"):
        return False
    blob = _place_blob(place).lower()
    if any(
        x in blob
        for x in (
            "公園", "파크", "마운트", "타워", "観光", "museum", "ワンマウント",
            "한우마을", "생선구이",
        )
    ):
        return False
    return True


# ─── 쿼리 빌더 ────────────────────────────────────────────────────────────────

def _build_itinerary_food_queries(
    user_message: str,
    keyword: str,
    traveler_profile: dict | None,
) -> list[str]:
    """일정용 맛집 Places Text Search 쿼리 목록 (서울 기본값은 비수도권 여행 시 생략)."""
    from src.chain.router import (  # lazy import
        _detect_itinerary_areas,
        _tourism_search_areas,
        _food_preferences_from_profile,
        _has_cafe_hopping_interest,
        _has_gourmet_interest,
        _food_queries_from_preferences,
        _food_queries_from_location_text,
        _food_queries_from_region_cities,
        _region_cities_text,
        _parse_region_city_tokens,
        _FOOD_PREF_SEARCH,
        _sort_food_queries_by_tourism_priority,
        _has_non_seoul_travel_intent,
        _SEOUL_DEFAULT_FOOD_AREAS,
        _plan_diversity_seed,
        _REROLL_EXTRA_FOOD_QUERIES,
        _shuffled_copy,
        _should_include_seongsimdang,
        logger,
    )
    areas = _detect_itinerary_areas(user_message, keyword, traveler_profile)
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = " ".join(q.split()).strip()
        if q and q not in seen:
            seen.add(q)
            queries.append(q)

    tourism_areas = _tourism_search_areas(traveler_profile)
    prefs, _ = _food_preferences_from_profile(traveler_profile)
    has_cafe_interest = _has_cafe_hopping_interest(
        traveler_profile, f"{user_message} {keyword}"
    )
    has_gourmet_interest = _has_gourmet_interest(
        traveler_profile, f"{user_message} {keyword}"
    )
    for q in _food_queries_from_preferences(traveler_profile, areas):
        add(q)

    if has_cafe_interest:
        cafe_areas = (tourism_areas or areas)[:4]
        for area in cafe_areas:
            add(f"{area} 유명 카페")
            add(f"{area} 로컬 카페")
            add(f"{area} 한옥 카페")
            add(f"{area} 디저트 카페")

    for area in tourism_areas or areas:
        add(f"{area} 한식 맛집")
        add(f"{area} 점심 맛집")
        add(f"{area} 저녁 맛집")
        if has_gourmet_interest:
            add(f"{area} 유명 맛집")
            add(f"{area} 현지인 맛집")
            add(f"{area} 대표 음식 맛집")
        if prefs or has_gourmet_interest:
            add(f"{area} 해장국 국밥")
            add(f"{area} 아침식사")
            add(f"{area} 브런치 카페")
        if not prefs and has_gourmet_interest:
            add(f"{area} 고기 맛집")
            add(f"{area} 한정식")
            add(f"{area} 분식")

    parts = [user_message, keyword]
    if traveler_profile:
        for reg in traveler_profile.get("regions") or []:
            parts.append(str(reg))
        cities = _region_cities_text(traveler_profile)
        if cities:
            parts.append(cities)
    blob = " ".join(parts)

    for q in _food_queries_from_location_text(blob):
        add(q)

    cities = _region_cities_text(traveler_profile)
    if cities:
        for q in _food_queries_from_region_cities(cities):
            add(q)
        if "가평" in cities:
            add("가평 맛집")
            add("가평 한식")
            add("가평 카페")
            add("남이섬 맛집")

    prefs, _ = _food_preferences_from_profile(traveler_profile)

    city_tokens = _parse_region_city_tokens(_region_cities_text(traveler_profile))
    for tok in city_tokens[:3]:
        add(f"{tok} 한식 맛집")
        if prefs:
            for pref in prefs[:2]:
                for template in (_FOOD_PREF_SEARCH.get(pref) or [])[:2]:
                    add(f"{tok} {template}")

    if "chicken" in prefs and traveler_profile:
        regs = [str(r).lower() for r in (traveler_profile.get("regions") or [])]
        if "gyeonggi" in regs:
            add("고양시 치킨 맛집")
            add("수원시 치킨 맛집")
        if "incheon" in regs:
            add("인천 미추홀 치킨 맛집")
            add("문학야구장 근처 치킨")
        if "seoul" in regs:
            add("명동 치킨 맛집")

    if not queries and not _has_non_seoul_travel_intent(blob):
        for a in _SEOUL_DEFAULT_FOOD_AREAS:
            add(f"{a} 맛집")

    acts = [str(a).lower() for a in (traveler_profile or {}).get("activities") or []]
    if "vacation" in acts and traveler_profile:
        for vt in traveler_profile.get("vacationTypes") or []:
            if vt == "poolvilla":
                add("가평 풀빌라")
                add("양평 풀빌라")
            elif vt == "pension":
                add("펜션 맛집")
                add("강원 펜션")

    reroll = int((traveler_profile or {}).get("plan_reroll") or 0)
    if reroll > 0 and traveler_profile:
        seed = _plan_diversity_seed(traveler_profile)
        for reg in traveler_profile.get("regions") or []:
            extras = _REROLL_EXTRA_FOOD_QUERIES.get(str(reg).lower(), [])
            for q in _shuffled_copy(extras, seed):
                add(q)
        acts = [str(a).lower() for a in (traveler_profile.get("activities") or [])]
        if "cafe" in acts:
            for area in _shuffled_copy(areas, seed + 1)[:2]:
                add(f"{area} 카페")

    if _should_include_seongsimdang(traveler_profile):
        add("대전 성심당")
        add("성심당 대전 본점")

    queries = _sort_food_queries_by_tourism_priority(queries, traveler_profile)
    queries = queries[:12]
    logger.info("itinerary food queries: %s", queries)
    return queries


def _build_itinerary_attraction_queries(
    user_message: str,
    keyword: str,
    traveler_profile: dict | None,
    priority_queries: list[str] | None = None,
) -> list[str]:
    """일정용 관광·카페 Places Text Search 쿼리."""
    from src.chain.router import (  # lazy import
        _detect_itinerary_areas,
        _attr_query_areas_for_plan,
        _has_itinerary_shopping_interest,
        _has_cafe_hopping_interest,
        _SHOPPING_MALL_TEXT_RE,
        _needs_accommodation_buffer_candidates,
        _accommodation_food_areas,
        _plan_diversity_seed,
        _REROLL_EXTRA_ATTR_QUERIES,
        _shuffled_copy,
        _vacation_types_from_profile,
    )
    areas = _detect_itinerary_areas(user_message, keyword, traveler_profile)
    expanded_areas = _attr_query_areas_for_plan(traveler_profile)
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = " ".join(q.split()).strip()
        if not has_shopping_interest and _SHOPPING_MALL_TEXT_RE.search(q):
            return
        if q and q not in seen:
            seen.add(q)
            queries.append(q)

    has_shopping_interest = _has_itinerary_shopping_interest(
        traveler_profile, f"{user_message} {keyword}"
    )
    has_cafe_interest = _has_cafe_hopping_interest(
        traveler_profile, f"{user_message} {keyword}"
    )

    for q in priority_queries or []:
        add(q)

    for area in expanded_areas or areas:
        add(f"{area} 관광")
        add(f"{area} 명소")
        add(f"{area} 관광지")
        acts = {str(a).lower() for a in (traveler_profile or {}).get("activities") or []}
        if "nature" in acts:
            add(f"{area} 공원")
            add(f"{area} 산책로")
            add(f"{area} 자연 명소")
            add(f"{area} 전망대")
        if "photo" in acts:
            add(f"{area} 포토스팟")
            add(f"{area} 사진 명소")
            add(f"{area} SNS 명소")
            add(f"{area} 야경 포토스팟")
        if "nightview" in acts:
            add(f"{area} 야경")
            add(f"{area} 야경 명소")
            add(f"{area} 야경 포인트")
            add(f"{area} 전망대")
        if "tradition" in acts:
            add(f"{area} 전통문화")
            add(f"{area} 한옥")
            add(f"{area} 박물관")
            add(f"{area} 문화예술")
        if any(a in acts for a in ("drama", "performance", "performances", "theater", "musical", "kpop")):
            add(f"{area} 공연장")
            add(f"{area} 문화공간")
            add(f"{area} 라이브 공연")
            add(f"{area} 뮤지컬")
            # 대학로는 서울 전용 공연 특구 — 서울 지역일 때만 추가
            _seoul_indicators = ("서울", "seoul", "종로", "홍대", "명동", "동대문", "마포", "강남")
            if any(si in area.lower() for si in _seoul_indicators):
                add(f"{area} 대학로 공연")
            else:
                add(f"{area} 예술의전당")
                add(f"{area} 콘서트")
        if "festival" in acts:
            add(f"{area} 축제")
            add(f"{area} 행사")
            add(f"{area} 페스티벌")
        if has_shopping_interest:
            add(f"{area} 쇼핑")
            add(f"{area} 쇼핑몰")
            add(f"{area} 전통시장")
        vacation_types = _vacation_types_from_profile(traveler_profile, f"{user_message} {keyword}")
        if "vacation" in acts or "beach" in vacation_types:
            add(f"{area} 해수욕장")
            add(f"{area} 해변")
            add(f"{area} 바다 전망")
            add(f"{area} 비치")
        if has_cafe_interest:
            add(f"{area} 유명 카페")
            add(f"{area} 로컬 카페")
            add(f"{area} 감성 카페")
            add(f"{area} 디저트 카페")

    if _needs_accommodation_buffer_candidates(traveler_profile, areas):
        for area in _accommodation_food_areas(traveler_profile)[:2]:
            add(f"{area} 산책")
            add(f"{area} 카페")
            if has_cafe_interest:
                add(f"{area} 유명 카페")
                add(f"{area} 로컬 카페")
            if has_shopping_interest:
                add(f"{area} 쇼핑")

    reroll = int((traveler_profile or {}).get("plan_reroll") or 0)
    if reroll > 0 and traveler_profile:
        seed = _plan_diversity_seed(traveler_profile)
        for reg in traveler_profile.get("regions") or []:
            for q in _shuffled_copy(_REROLL_EXTRA_ATTR_QUERIES.get(str(reg).lower(), []), seed):
                add(q)

    # 지역별 고정 추천 장소 — region_cities 에 키워드가 포함될 때 우선 쿼리에 삽입
    if traveler_profile:
        from src.chain.router import _region_cities_text  # lazy import
        cities_text = _region_cities_text(traveler_profile)
        for keyword_key, spots in _REGION_FEATURED_SPOTS.items():
            if keyword_key in cities_text:
                featured_queries = []
                for name, area in spots:
                    if area:
                        featured_queries.append(f"{name} {area}")
                    featured_queries.append(name)
                # 맨 앞에 삽입 (우선순위 최상위)
                for q in reversed(featured_queries):
                    q = q.strip()
                    if q and q not in seen:
                        seen.add(q)
                        queries.insert(0, q)

    if has_shopping_interest:
        return queries[:24]
    return queries[:16]


# ─── 후보 병합 ────────────────────────────────────────────────────────────────

def _merge_itinerary_places(
    batches: list[list[NearbyPlace]],
    *,
    max_total: int,
    shuffle_seed: int = 0,
    avoid_names: set[str] | None = None,
    min_keep: int = 0,
) -> list[NearbyPlace]:
    from src.chain.itinerary_repair import _norm_plan_place_name  # lazy import
    from src.chain.router import _shuffled_copy  # lazy import
    all_places: list[NearbyPlace] = []
    avoided_places: list[NearbyPlace] = []
    seen: set[str] = set()
    for results in batches:
        for p in results:
            key = f"{p.name}|{p.address}"
            if key not in seen:
                seen.add(key)
                name_key = _norm_plan_place_name(p.name)
                url_key = _norm_plan_place_name(p.google_maps_uri)
                if avoid_names and (name_key in avoid_names or url_key in avoid_names):
                    avoided_places.append(p)
                else:
                    all_places.append(p)
    if shuffle_seed:
        all_places = _shuffled_copy(all_places, shuffle_seed)
        avoided_places = _shuffled_copy(avoided_places, shuffle_seed + 17)
    if len(all_places) < min_keep:
        all_places.extend(avoided_places[: max(0, min_keep - len(all_places))])
    return all_places[:max_total]


def _combine_itinerary_place_candidates(
    food_places: list[NearbyPlace],
    attr_places: list[NearbyPlace],
    *,
    traveler_profile: dict | None,
    max_total: int,
) -> list[NearbyPlace]:
    from src.chain.router import (  # lazy import
        _has_cafe_hopping_interest,
        _itinerary_food_candidate_limit,
    )
    food_limit = _itinerary_food_candidate_limit(traveler_profile, max_total)
    cafe_limit = 0
    if _has_cafe_hopping_interest(traveler_profile):
        try:
            days = int((traveler_profile or {}).get("days") or 3)
        except (TypeError, ValueError):
            days = 3
        cafe_limit = min(12, max(4, days * 2))
    cafe_places = [p for p in food_places if _is_cafe_candidate_place(p)]
    meal_places = [p for p in food_places if not _is_cafe_candidate_place(p)]
    combined: list[NearbyPlace] = []
    seen: set[str] = set()

    def add(place: NearbyPlace) -> None:
        key = f"{place.name}|{place.address}"
        if key not in seen and len(combined) < max_total:
            seen.add(key)
            combined.append(place)

    for place in cafe_places[:cafe_limit]:
        add(place)
    for place in attr_places:
        add(place)
    for place in meal_places[:food_limit]:
        add(place)
    return combined
