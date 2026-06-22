from __future__ import annotations

import unittest

from src.api.region_resolver import (
    address_matches_destination,
    areas_from_region_city_ids,
    destination_filter_from_text,
    region_city_ids_from_profile,
    selected_destination_context,
)

try:
    from src.api.google_places_client import NearbyPlace, is_suitable_meal_place
    from src.chain.router import (
        _build_itinerary_attraction_queries,
        _build_itinerary_food_queries,
        _combine_itinerary_place_candidates,
        _detect_itinerary_areas,
        _expanded_tourism_areas_for_plan,
        _fmt_itinerary_daily_area_binding,
        _has_itinerary_shopping_interest,
        _is_reliable_kpop_web_result,
        _is_cafe_candidate_place,
        _is_naver_attr_place,
        _is_naver_cafe_place,
        _is_naver_food_place,
        _merge_itinerary_places,
        _place_matches_destination_profile,
        _repair_wizard_itinerary_rules,
        _tourism_candidate_areas_for_plan,
    )
    from src.api.ticket_platform_events_client import _kopis_genres_for_profile
    from src.chain.itinerary_quality import _score_wizard_plan_quality
    from src.api.web_search_client import WebSearchResult
except ModuleNotFoundError as exc:
    NearbyPlace = None
    _build_itinerary_attraction_queries = None
    _build_itinerary_food_queries = None
    _combine_itinerary_place_candidates = None
    _detect_itinerary_areas = None
    _expanded_tourism_areas_for_plan = None
    _fmt_itinerary_daily_area_binding = None
    _has_itinerary_shopping_interest = None
    _is_reliable_kpop_web_result = None
    _is_cafe_candidate_place = None
    _is_naver_attr_place = None
    _is_naver_cafe_place = None
    _is_naver_food_place = None
    _merge_itinerary_places = None
    _place_matches_destination_profile = None
    _repair_wizard_itinerary_rules = None
    _tourism_candidate_areas_for_plan = None
    _kopis_genres_for_profile = None
    _score_wizard_plan_quality = None
    WebSearchResult = None
    _ROUTER_IMPORT_ERROR = exc
else:
    _ROUTER_IMPORT_ERROR = None


class RegionResolverTests(unittest.TestCase):
    def test_region_city_ids_accept_frontend_and_backend_shapes(self) -> None:
        profile = {
            "regionCityIds": ["gyeonggi:gwangju_si"],
            "region_city_meta": [{"region": "jeolla", "id": "gwangju"}],
        }

        self.assertEqual(
            region_city_ids_from_profile(profile),
            ["gyeonggi:gwangju_si", "jeolla:gwangju"],
        )

    def test_city_ids_resolve_to_canonical_itinerary_areas(self) -> None:
        self.assertEqual(
            areas_from_region_city_ids(
                {
                    "region_city_ids": [
                        "gyeonggi:gwangju_si",
                        "jeolla:gwangju",
                        "gyeonggi:ansan_danwon",
                    ]
                }
            ),
            ["경기광주", "광주", "안산"],
        )

    def test_gyeongsang_secondary_city_ids_resolve_to_itinerary_areas(self) -> None:
        self.assertEqual(
            areas_from_region_city_ids(
                {"region_city_ids": ["gyeongsang:yeongcheon", "gyeongsang:haman"]}
            ),
            ["영천", "함안"],
        )

    def test_province_city_ids_resolve_remote_counties(self) -> None:
        self.assertEqual(
            areas_from_region_city_ids(
                {
                    "region_city_ids": [
                        "jeonnam:jangseong",
                        "chungnam:cheongyang",
                        "gyeongbuk:bonghwa",
                        "gyeongnam:sancheong",
                    ]
                }
            ),
            ["장성", "청양", "봉화", "산청"],
        )

    def test_region_city_meta_query_fallback_is_canonicalized(self) -> None:
        self.assertEqual(
            areas_from_region_city_ids(
                {
                    "region_city_ids": ["jeonnam:new_county"],
                    "region_city_meta": [
                        {"region": "jeonnam", "id": "new_county", "query": "장성군"}
                    ],
                }
            ),
            ["장성"],
        )

    def test_address_filter_disambiguates_gwangju(self) -> None:
        self.assertTrue(
            address_matches_destination(
                "경기도 광주시 도척면 도척윗로 278 곤지암리조트",
                region_city_ids=["gyeonggi:gwangju_si"],
                dest_regions=["gyeonggi"],
            )
        )
        self.assertFalse(
            address_matches_destination(
                "광주광역시 동구 서석로 38",
                region_city_ids=["gyeonggi:gwangju_si"],
                dest_regions=["gyeonggi"],
            )
        )
        self.assertTrue(
            address_matches_destination(
                "광주광역시 동구 서석로 38",
                region_city_ids=["jeolla:gwangju"],
                dest_regions=["jeolla"],
            )
        )
        self.assertFalse(
            address_matches_destination(
                "경기도 광주시 남한산성면",
                region_city_ids=["jeolla:gwangju"],
                dest_regions=["jeolla"],
            )
        )

    def test_address_filter_disambiguates_goseong(self) -> None:
        self.assertTrue(
            address_matches_destination(
                "강원특별자치도 고성군 토성면",
                region_city_ids=["gangwon:goseong"],
                dest_regions=["gangwon"],
            )
        )
        self.assertFalse(
            address_matches_destination(
                "경상남도 고성군 고성읍 동외리",
                region_city_ids=["gangwon:goseong"],
                dest_regions=["gangwon"],
            )
        )
        self.assertTrue(
            address_matches_destination(
                "경상남도 고성군 고성읍 동외리",
                region_city_ids=["gyeongsang:goseong_gn"],
                dest_regions=["gyeongsang"],
            )
        )

    def test_address_filter_accepts_yeongcheon_and_haman(self) -> None:
        self.assertTrue(
            address_matches_destination(
                "경상북도 영천시 임고면 운주로",
                region_city_ids=["gyeongsang:yeongcheon"],
                dest_regions=["gyeongsang"],
            )
        )

    def test_address_filter_accepts_remote_county_ids(self) -> None:
        self.assertTrue(
            address_matches_destination(
                "전라남도 장성군 북하면 백양로",
                region_city_ids=["jeonnam:jangseong"],
                dest_regions=["jeolla"],
            )
        )
        self.assertTrue(
            address_matches_destination(
                "충청남도 청양군 대치면 장곡길",
                region_city_ids=["chungnam:cheongyang"],
                dest_regions=["chungcheong"],
            )
        )
        self.assertTrue(
            address_matches_destination(
                "경상남도 함안군 법수면 장백로",
                region_city_ids=["gyeongsang:haman"],
                dest_regions=["gyeongsang"],
            )
        )

    def test_selected_destination_context_is_explicit(self) -> None:
        context = selected_destination_context(
            {"region_city_ids": ["gyeonggi:gwangju_si"]}
        )

        self.assertIn("gyeonggi:gwangju_si", context)
        self.assertIn("경기광주", context)

    def test_free_text_destination_filter_narrows_ilsan_to_goyang(self) -> None:
        filt = destination_filter_from_text("일산 피자 맛집")

        self.assertIn("gyeonggi:goyang", filt["region_city_ids"])
        self.assertTrue(
            address_matches_destination(
                "경기도 고양시 일산동구 고양대로 1124",
                region_city_ids=filt["region_city_ids"],
                dest_regions=filt["dest_regions"],
            )
        )
        self.assertFalse(
            address_matches_destination(
                "경기도 파주시 지목로 17-7",
                region_city_ids=filt["region_city_ids"],
                dest_regions=filt["dest_regions"],
            )
        )
        self.assertFalse(
            address_matches_destination(
                "경기도 김포시 검단로 910",
                region_city_ids=filt["region_city_ids"],
                dest_regions=filt["dest_regions"],
            )
        )

    def test_free_text_destination_filter_uses_nationwide_city_labels(self) -> None:
        filt = destination_filter_from_text("포항 물회 맛집")

        self.assertTrue(
            any(cid.endswith(":pohang") for cid in filt["region_city_ids"])
        )
        self.assertTrue(
            address_matches_destination(
                "경상북도 포항시 북구 해안로",
                region_city_ids=filt["region_city_ids"],
                dest_regions=filt["dest_regions"],
            )
        )
        self.assertFalse(
            address_matches_destination(
                "경상북도 경주시 보문로",
                region_city_ids=filt["region_city_ids"],
                dest_regions=filt["dest_regions"],
            )
        )


class RouterRegionDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        if _detect_itinerary_areas is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")

    def test_detect_itinerary_areas_prefers_gyeonggi_gwangju_id(self) -> None:
        profile = {
            "regions": ["gyeonggi"],
            "regionCities": "광주시",
            "regionCityIds": ["gyeonggi:gwangju_si"],
        }

        areas = _detect_itinerary_areas("광주시 여행", "", profile)

        self.assertIn("경기광주", areas)
        self.assertNotIn("광주", areas)

    def test_detect_itinerary_areas_keeps_metropolitan_gwangju(self) -> None:
        profile = {
            "regions": ["jeolla"],
            "regionCities": "광주광역시",
            "regionCityIds": ["jeolla:gwangju"],
        }

        areas = _detect_itinerary_areas("광주광역시 여행", "", profile)

        self.assertIn("광주", areas)
        self.assertNotIn("경기광주", areas)

    def test_detect_itinerary_areas_uses_remote_county_city_ids(self) -> None:
        profile = {
            "regions": ["jeonnam"],
            "regionCities": "장성군",
            "regionCityIds": ["jeonnam:jangseong"],
        }

        areas = _detect_itinerary_areas("장성 여행", "", profile)

        self.assertEqual(areas[:1], ["장성"])

    def test_remote_county_uses_nearby_tourism_zone_for_candidates(self) -> None:
        if _tourism_candidate_areas_for_plan is None or _expanded_tourism_areas_for_plan is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["jeolla"],
            "regionAreaKeys": ["jeonnam"],
            "regionCities": "장성군",
            "regionCityIds": ["jeonnam:jangseong"],
        }

        self.assertEqual(
            _tourism_candidate_areas_for_plan(profile)[:3],
            ["장성", "담양", "광주"],
        )
        self.assertEqual(
            _expanded_tourism_areas_for_plan(profile)[:3],
            ["장성", "담양", "광주"],
        )

    def test_remote_county_area_binding_allows_only_named_fallbacks(self) -> None:
        if _fmt_itinerary_daily_area_binding is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "days": 4,
            "regions": ["jeolla"],
            "regionAreaKeys": ["jeonnam"],
            "regionCities": "장성군",
            "regionCityIds": ["jeonnam:jangseong"],
        }

        context = _fmt_itinerary_daily_area_binding(profile)

        self.assertIn("장성", context)
        self.assertIn("담양", context)
        self.assertIn("광주", context)
        self.assertIn("候補が少ない小規模市郡", context)


class RouterItineraryPlaceBalanceTests(unittest.TestCase):
    def setUp(self) -> None:
        if _combine_itinerary_place_candidates is None or NearbyPlace is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")

    def _place(self, name: str, category: str) -> NearbyPlace:
        return NearbyPlace(
            name=name,
            category=category,
            address=f"Seoul {name}",
            latitude=37.5,
            longitude=127.0,
            rating=4.5,
            user_rating_count=100,
            google_maps_uri=f"https://maps.example/{name}",
            is_open_now=None,
            distance_meters=None,
        )

    def test_itinerary_candidates_put_attractions_before_food(self) -> None:
        food = [self._place(f"restaurant-{i}", "restaurant") for i in range(4)]
        attrs = [self._place(f"attraction-{i}", "tourist_attraction") for i in range(3)]

        combined = _combine_itinerary_place_candidates(
            food,
            attrs,
            traveler_profile={"days": 2},
            max_total=10,
        )

        self.assertEqual([p.name for p in combined[:3]], [p.name for p in attrs])

    def test_itinerary_candidates_cap_food_by_trip_length(self) -> None:
        food = [self._place(f"restaurant-{i}", "restaurant") for i in range(20)]

        combined = _combine_itinerary_place_candidates(
            food,
            [],
            traveler_profile={"days": 2},
            max_total=50,
        )

        self.assertEqual(len(combined), 8)

    def test_merge_itinerary_places_avoids_previous_plan_places_when_possible(self) -> None:
        if _merge_itinerary_places is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        places = [
            self._place("old-place", "restaurant"),
            self._place("new-place-1", "restaurant"),
            self._place("new-place-2", "restaurant"),
        ]

        merged = _merge_itinerary_places(
            [places],
            max_total=2,
            avoid_names={"old-place"},
            min_keep=2,
        )

        self.assertEqual([p.name for p in merged], ["new-place-1", "new-place-2"])

    def test_cafe_candidates_survive_food_candidate_cap(self) -> None:
        food = [self._place(f"restaurant-{i}", "restaurant") for i in range(20)]
        cafes = [self._place(f"강남 카페 {i}", "카페,디저트") for i in range(6)]
        attrs = [self._place(f"attraction-{i}", "tourist_attraction") for i in range(4)]

        combined = _combine_itinerary_place_candidates(
            food + cafes,
            attrs,
            traveler_profile={"days": 5, "activities": ["cafe"]},
            max_total=30,
        )

        self.assertTrue(any("카페" in p.name for p in combined))

    def test_cafe_candidates_are_reserved_when_total_cap_is_tight(self) -> None:
        food = [self._place(f"restaurant-{i}", "restaurant") for i in range(20)]
        cafes = [self._place(f"성수 카페 {i}", "카페,디저트") for i in range(6)]
        attrs = [self._place(f"attraction-{i}", "tourist_attraction") for i in range(12)]

        combined = _combine_itinerary_place_candidates(
            food + cafes,
            attrs,
            traveler_profile={"days": 5, "activities": ["cafe"]},
            max_total=10,
        )

        self.assertTrue(any("카페" in p.name for p in combined))

    def test_fortune_telling_place_is_not_cafe_or_activity_candidate(self) -> None:
        if _is_cafe_candidate_place is None or _is_naver_cafe_place is None or _is_naver_attr_place is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        bad = self._place("서울유명한점집,연화암", "점집")
        bad = bad.__class__(
            **{
                **bad.__dict__,
                "search_area": "강남 카페",
                "google_maps_uri": "https://map.naver.com/p/search/bad",
            }
        )
        good = self._place("로칼커피 삼성점", "카페,디저트")

        self.assertFalse(_is_cafe_candidate_place(bad))
        self.assertFalse(_is_naver_cafe_place(bad))
        self.assertFalse(_is_naver_attr_place(bad))
        self.assertTrue(_is_cafe_candidate_place(good))

    def test_shopping_square_is_not_meal_candidate(self) -> None:
        if _is_naver_food_place is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        mall = self._place("LF스퀘어 인천점", "쇼핑몰")
        mall = mall.__class__(
            **{
                **mall.__dict__,
                "address": "인천광역시 연수구 청능대로 23번길 11",
            }
        )
        self.assertFalse(is_suitable_meal_place(mall))
        self.assertFalse(_is_naver_food_place(mall))

    def test_selected_incheon_destination_rejects_jeju_place(self) -> None:
        if _place_matches_destination_profile is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regionAreaKeys": ["incheon"],
            "regions": ["incheon"],
            "regionCityIds": ["incheon:yeonsu"],
        }
        jeju = self._place("제주 카페", "카페")
        jeju = jeju.__class__(**{**jeju.__dict__, "address": "제주특별자치도 제주시 애월읍"})
        incheon = self._place("송도 식당", "음식점")
        incheon = incheon.__class__(**{**incheon.__dict__, "address": "인천광역시 연수구 송도동"})

        self.assertFalse(_place_matches_destination_profile(jeju, profile))
        self.assertTrue(_place_matches_destination_profile(incheon, profile))

    def test_kopis_kpop_uses_popular_music_genre(self) -> None:
        if _kopis_genres_for_profile is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")

        genres = _kopis_genres_for_profile({"activities": ["kpop"]})

        self.assertEqual([g[1] for g in genres], ["concert"])
        self.assertEqual([g[0] for g in genres], ["CCCD"])
        self.assertEqual([g[2] for g in genres], ["대중음악"])

    def test_kopis_performance_uses_play_and_musical_genres(self) -> None:
        if _kopis_genres_for_profile is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")

        genres = _kopis_genres_for_profile({"activities": ["drama"]})

        self.assertEqual([g[1] for g in genres], ["play", "musical"])

    def test_kpop_web_filter_rejects_generic_city_pages(self) -> None:
        if _is_reliable_kpop_web_result is None or WebSearchResult is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")

        bad_results = [
            WebSearchResult("동행·매력 특별시 서울 | 서울특별시", "https://www.seoul.go.kr", "주요뉴스 시민참여 행사 및 축제"),
            WebSearchResult("서울특별시 - 나무위키", "https://namu.wiki/w/서울특별시", "일상적으로 서울이라고 하면..."),
            WebSearchResult("Welcome to Seoul - Visit Seoul", "https://english.visitseoul.net", "Official Travel Guide"),
            WebSearchResult("서울특별시 - 위키백과", "https://ko.wikipedia.org/wiki/서울특별시", "위키백과"),
        ]
        good = WebSearchResult(
            "2026 Seoul K-pop Concert Tickets",
            "https://tickets.interpark.com/goods/123",
            "K-pop concert ticket schedule 2026",
        )

        self.assertTrue(_is_reliable_kpop_web_result(good))
        self.assertTrue(all(not _is_reliable_kpop_web_result(r) for r in bad_results))

    def test_kpop_without_shopping_does_not_add_mall_queries(self) -> None:
        if _build_itinerary_attraction_queries is None or _has_itinerary_shopping_interest is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["seoul"],
            "regionCities": "강남구",
            "activities": ["drama", "kpop", "cafe", "nature", "photo"],
            "additional": {"travelStyles": []},
        }

        self.assertFalse(_has_itinerary_shopping_interest(profile))
        queries = _build_itinerary_attraction_queries("K-pop 카페 자연 포토스팟", "", profile)
        joined = " ".join(queries)

        self.assertNotIn("쇼핑몰", joined)
        self.assertNotIn("코엑스몰", joined)
        self.assertNotIn("현대백화점", joined)

    def test_shopping_selection_allows_mall_queries(self) -> None:
        if _build_itinerary_attraction_queries is None or _has_itinerary_shopping_interest is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["seoul"],
            "regionCities": "강남구",
            "activities": ["kpop", "shopping"],
        }

        self.assertTrue(_has_itinerary_shopping_interest(profile))
        queries = _build_itinerary_attraction_queries("K-pop 쇼핑", "", profile)

        self.assertTrue(any("쇼핑" in q or "코엑스몰" in q for q in queries))

    def test_activity_selection_adds_location_queries_for_ui_refs(self) -> None:
        if _build_itinerary_attraction_queries is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["seoul"],
            "regionCities": "강북구",
            "activities": ["nature", "photo", "tradition", "kpop", "drama"],
        }

        queries = _build_itinerary_attraction_queries("자연 포토스팟 K-pop 공연", "", profile)
        joined = " ".join(queries)

        self.assertIn("공원", joined)
        self.assertIn("포토스팟", joined)
        self.assertIn("전통문화", joined)
        self.assertIn("공연장", joined)

    def test_vacation_beach_selection_adds_beach_attr_queries(self) -> None:
        if _build_itinerary_attraction_queries is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["gangwon"],
            "regionCities": "강릉",
            "regionCityIds": ["gangwon:gangneung"],
            "activities": ["vacation", "nature", "photo"],
            "vacationTypes": ["beach"],
        }

        queries = _build_itinerary_attraction_queries("바캉스 해수욕장 자연 포토스팟", "", profile)
        joined = " ".join(queries)

        self.assertIn("해수욕장", joined)
        self.assertIn("해변", joined)

    def test_quality_fails_when_selected_activities_are_missing(self) -> None:
        if _score_wizard_plan_quality is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "days": 3,
            "activities": ["food", "cafe", "nature", "photo", "tradition", "vacation"],
            "vacationTypes": ["beach"],
        }
        plan = "\n".join(
            [
                "1日目",
                "到着後、宿泊先へ移動",
                "2日目",
                "昼食",
                "강릉 식당",
                "https://map.naver.com/p/search/food",
                "午後",
                "市場を散策",
                "https://map.naver.com/p/search/market",
                "夕食",
                "강릉 저녁식당",
                "https://map.naver.com/p/search/dinner",
                "3日目",
                "帰国",
            ]
        )

        _score, failures = _score_wizard_plan_quality(plan, [], profile)

        self.assertIn("selected_activity_missing:cafe", failures)
        self.assertIn("selected_activity_missing:nature", failures)
        self.assertIn("selected_activity_missing:photo", failures)
        self.assertIn("selected_activity_missing:tradition", failures)
        self.assertIn("selected_activity_missing:vacation", failures)

    def test_no_candidate_text_does_not_satisfy_event_selections(self) -> None:
        if _score_wizard_plan_quality is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "days": 3,
            "activities": ["festival", "performance", "kpop", "sports"],
        }
        plan = "\n".join(
            [
                "1日目",
                "到着後、宿泊先へ移動",
                "2日目",
                "昼食",
                "식당",
                "https://map.naver.com/p/search/food",
                "午後",
                "祭り・公演・K-pop・スポーツ観戦は該当候補なし",
                "夕食",
                "저녁식당",
                "https://map.naver.com/p/search/dinner",
                "3日目",
                "帰国",
            ]
        )

        _score, failures = _score_wizard_plan_quality(plan, [], profile)

        self.assertIn("selected_activity_missing:festival", failures)
        self.assertIn("selected_activity_missing:performance", failures)
        self.assertIn("selected_activity_missing:K-pop", failures)
        self.assertIn("selected_activity_missing:sports", failures)

    def test_cafe_hopping_prioritizes_cafe_queries(self) -> None:
        if _build_itinerary_food_queries is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["seoul"],
            "regionCities": "성수",
            "activities": ["cafe"],
            "additional": {"foodPreferences": []},
        }

        queries = _build_itinerary_food_queries("카페순회 하고 싶어", "", profile)

        self.assertTrue(any("유명 카페" in q or "로컬 카페" in q for q in queries[:8]))

    def test_no_food_preference_does_not_inject_bossam_queries(self) -> None:
        if _build_itinerary_food_queries is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["seoul"],
            "regionCities": "강남구 송파구",
            "activities": ["shopping", "nightview", "tradition", "kpop", "cafe", "nature", "photo"],
            "additional": {"foodPreferences": [], "travelStyles": []},
        }

        queries = _build_itinerary_food_queries("쇼핑 야경 전통문화 K-pop 카페순회 자연 포토스팟", "", profile)
        joined = " ".join(queries)

        self.assertNotIn("보쌈", joined)
        self.assertNotIn("족발", joined)
        self.assertNotIn("돼지국밥", joined)
        self.assertTrue(any("카페" in q for q in queries))

    def test_no_gourmet_interest_keeps_food_queries_route_basic(self) -> None:
        if _build_itinerary_food_queries is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["seoul"],
            "regionCities": "강남구 송파구",
            "activities": ["shopping", "nightview", "tradition", "kpop", "cafe", "nature", "photo"],
            "additional": {"foodPreferences": [], "travelStyles": []},
        }

        queries = _build_itinerary_food_queries("쇼핑 야경 전통문화 K-pop 카페순회 자연 포토스팟", "", profile)
        joined = " ".join(queries)

        self.assertIn("점심 맛집", joined)
        self.assertIn("저녁 맛집", joined)
        self.assertNotIn("유명 맛집", joined)
        self.assertNotIn("현지인 맛집", joined)

    def test_gourmet_interest_adds_signature_food_queries(self) -> None:
        if _build_itinerary_food_queries is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")
        profile = {
            "regions": ["seoul"],
            "regionCities": "강남구 송파구",
            "activities": ["food", "shopping", "nightview"],
            "additional": {"foodPreferences": [], "travelStyles": []},
        }

        queries = _build_itinerary_food_queries("グルメとショッピングをしたい", "", profile)
        joined = " ".join(queries)

        self.assertIn("유명 맛집", joined)
        self.assertIn("현지인 맛집", joined)
        self.assertIn("대표 음식 맛집", joined)


class RouterExplicitSubareaTests(unittest.TestCase):
    def setUp(self) -> None:
        if _expanded_tourism_areas_for_plan is None or _build_itinerary_attraction_queries is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")

    def test_seoul_jung_selection_does_not_expand_to_insadong(self) -> None:
        profile = {
            "regions": ["seoul"],
            "regionAreaKeys": ["seoul:jung"],
            "regionCityIds": ["seoul:jung"],
            "regionCities": "서울 중구",
            "activities": ["must_see"],
        }

        areas = _expanded_tourism_areas_for_plan(profile)
        queries = _build_itinerary_attraction_queries("", "", profile)
        joined = " ".join(areas + queries)

        self.assertIn("명동", areas)
        self.assertNotIn("인사동", joined)
        self.assertNotIn("쌈지길", joined)


class RouterItineraryRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        if _repair_wizard_itinerary_rules is None or NearbyPlace is None:
            self.skipTest(f"router dependencies unavailable: {_ROUTER_IMPORT_ERROR}")

    def _restaurant(self, name: str, address: str, url: str) -> NearbyPlace:
        return NearbyPlace(
            name=name,
            category="restaurant",
            address=address,
            latitude=37.5,
            longitude=127.0,
            rating=4.5,
            user_rating_count=100,
            google_maps_uri=url,
            is_open_now=None,
            distance_meters=None,
        )

    def _cafe(self, name: str, address: str, url: str) -> NearbyPlace:
        return NearbyPlace(
            name=name,
            category="카페,디저트",
            address=address,
            latitude=37.5,
            longitude=127.0,
            rating=4.5,
            user_rating_count=100,
            google_maps_uri=url,
            is_open_now=None,
            distance_meters=None,
        )

    def _attraction(self, name: str, address: str, url: str) -> NearbyPlace:
        return NearbyPlace(
            name=name,
            category="여행,명소",
            address=address,
            latitude=35.1,
            longitude=129.0,
            rating=None,
            user_rating_count=None,
            google_maps_uri=url,
            is_open_now=None,
            distance_meters=None,
        )

    def test_penultimate_return_day_removes_far_destination_dinner(self) -> None:
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["chungcheong"],
            "regionCities": "대전",
            "accommodation": {"address": "서울 중구 명동"},
        }
        far_url = "https://map.naver.com/p/search/daejeon-dinner"
        stay_url = "https://map.naver.com/p/search/myeongdong-dinner"
        places = [
            self._restaurant("동일갈국수", "대전광역시 중구 대흥동", far_url),
            self._restaurant("명동교자", "서울 중구 명동10길", stay_url),
        ]

        far_reply = "\n".join(["4日目", "夕食", "동일갈국수", far_url])
        stay_reply = "\n".join(["4日目", "夕食", "명동교자", stay_url])

        repaired_far = _repair_wizard_itinerary_rules(far_reply, places, profile, "旅行プラン")
        repaired_stay = _repair_wizard_itinerary_rules(stay_reply, places, profile, "旅行プラン")

        self.assertNotIn("동일갈국수", repaired_far)
        self.assertNotIn(far_url, repaired_far)
        self.assertIn("명동교자", repaired_stay)
        self.assertIn(stay_url, repaired_stay)

    def test_repair_removes_civic_office_tourism_block(self) -> None:
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["gyeonggi"],
            "regionCities": "고양시",
        }
        reply = "\n".join([
            "4日目",
            "午前",
            "고양특례시청",
            "https://www.goyang.go.kr/www/index.do",
            "고양시의 문화와 행정의 중심입니다.",
            "昼食",
            "명가원설농탕",
            "https://map.naver.com/p/search/%EB%AA%85%EA%B0%80%EC%9B%90%EC%84%A4%EB%86%8D%ED%83%95",
        ])
        places = [
            self._restaurant(
                "명가원설농탕",
                "경기도 고양시 일산동구 일산로 438",
                "https://map.naver.com/p/search/%EB%AA%85%EA%B0%80%EC%9B%90%EC%84%A4%EB%86%8D%ED%83%95",
            )
        ]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "旅行プラン")

        self.assertNotIn("고양특례시청", repaired)
        self.assertNotIn("goyang.go.kr", repaired)
        self.assertIn("명가원설농탕", repaired)

    def test_repair_fills_empty_cafe_time_with_candidate(self) -> None:
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["seoul"],
            "activities": ["cafe"],
        }
        cafe_url = "https://map.naver.com/p/search/%EC%84%B1%EC%88%98%EC%B9%B4%ED%8E%98"
        reply = "\n".join(["2日目", "午後", "カフェタイム", "夕食"])
        places = [self._cafe("성수카페", "서울 성동구 성수동", cafe_url)]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "カフェ巡り 旅行プラン")

        self.assertIn("성수카페", repaired)
        self.assertIn(cafe_url, repaired)
        self.assertLess(repaired.index("성수카페"), repaired.index("夕食"))

    def test_repair_replaces_attraction_in_lunch_slot(self) -> None:
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["gyeongsang"],
            "regionCities": "부산",
        }
        tae_url = "https://map.naver.com/p/search/%ED%83%9C%EC%A2%85%EB%8C%80"
        meal_url = "https://map.naver.com/p/search/%ED%95%B4%EC%9A%B4%EB%8C%80%EB%A7%9B%EC%A7%91"
        reply = "\n".join([
            "3日目(해운대 지역)",
            "昼食",
            "태종대",
            tae_url,
            "新鮮な海鮮料理を楽しめます。",
        ])
        places = [
            self._attraction("태종대", "부산광역시 영도구 전망로 24", tae_url),
            self._restaurant("해운대맛집", "부산광역시 해운대구 해운대로 1", meal_url),
        ]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "旅行プラン")

        self.assertNotIn("태종대", repaired)
        self.assertNotIn(tae_url, repaired)
        self.assertIn("해운대맛집", repaired)
        self.assertIn(meal_url, repaired)

    def test_repair_removes_far_cafe_from_focused_day(self) -> None:
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["gyeongsang"],
            "regionCities": "부산",
            "activities": ["cafe"],
        }
        far_url = "https://map.naver.com/p/search/%EB%AA%BB%EA%B3%A8%EC%8B%9C%EC%9E%A5%ED%98%B8%EB%91%90%EA%B3%BC%EC%9E%90"
        near_url = "https://map.naver.com/p/search/%EC%88%98%EC%9B%94%EA%B2%BD%ED%99%94"
        reply = "\n".join([
            "3日目(해운대 지역)",
            "午後",
            "못골시장 호두과자 냠",
            far_url,
            "散策途中に休憩しやすい候補。",
        ])
        places = [
            self._cafe("못골시장 호두과자 냠", "부산광역시 남구 못골번영로 22 1층", far_url),
            self._cafe("수월경화", "부산광역시 해운대구 송정중앙로6번길 188", near_url),
        ]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "カフェ巡り 旅行プラン")

        self.assertNotIn("못골시장 호두과자 냠", repaired)
        self.assertNotIn(far_url, repaired)

    def test_repair_removes_name_only_food_from_morning_slot(self) -> None:
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["gyeongsang"],
            "regionCities": "부산",
        }
        food_url = "https://map.naver.com/p/search/%EA%B3%A0%ED%96%A5%EC%97%B0%ED%99%94"
        reply = "\n".join([
            "3日目(해운대 지역)",
            "午前",
            "해동 용궁사 부산",
            "고향연화",
            "ショッピングと写真を組み合わせやすい立ち寄り場所。",
            "海を向いた絶景の寺院です。",
        ])
        places = [
            self._restaurant("고향연화", "부산광역시 기장군 기장읍 연화길 33-8", food_url),
        ]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "旅行プラン")

        self.assertIn("해동 용궁사 부산", repaired)
        self.assertNotIn("고향연화", repaired)
        self.assertNotIn("ショッピングと写真", repaired)

    def test_repair_removes_second_name_only_attraction_after_plain_stop(self) -> None:
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["gyeongsang"],
            "regionCities": "부산",
        }
        sea_url = "https://map.naver.com/p/search/%EC%94%A8%EB%9D%BC%EC%9D%B4%ED%94%84"
        reply = "\n".join([
            "3日目(해운대 지역)",
            "午後",
            "해운대 해수욕장",
            "씨라이프 부산 아쿠아리움",
            "この日の移動経路に組み込みやすい参照データで確認された場所。",
            "韓国屈指のビーチリゾートで散策を楽しめます。",
        ])
        places = [
            self._attraction("씨라이프 부산 아쿠아리움", "부산광역시 해운대구 해운대해변로 266", sea_url),
        ]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "旅行プラン")

        self.assertIn("해운대 해수욕장", repaired)
        self.assertNotIn("씨라이프 부산 아쿠아리움", repaired)
        self.assertNotIn("참조 데이터", repaired)

    def test_repair_removes_second_url_backed_attraction_after_url_backed_stop(self) -> None:
        """Production case: _repair_itinerary_place_urls injects URLs before repair runs,
        so companion attractions arrive with URLs — the url_match path must remove them."""
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["gyeongsang"],
            "regionCities": "부산",
        }
        beach_url = "https://map.naver.com/p/search/%ED%95%B4%EC%9A%B4%EB%8C%80%ED%95%B4%EC%88%98%EC%9A%95%EC%9E%A5"
        sea_url = "https://map.naver.com/p/search/%EC%94%A8%EB%9D%BC%EC%9D%B4%ED%94%84"
        # Simulates the state AFTER _repair_itinerary_place_urls has injected URLs
        reply = "\n".join([
            "3日目(해운대 지역)",
            "午後",
            "해운대 해수욕장",
            beach_url,
            "씨라이프 부산 아쿠아리움",
            sea_url,
            "韓国屈指のビーチリゾートで散策を楽しめます。",
        ])
        places = [
            self._attraction("해운대 해수욕장", "부산광역시 해운대구 해운대해변로", beach_url),
            self._attraction("씨라이프 부산 아쿠아리움", "부산광역시 해운대구 해운대해변로 266", sea_url),
        ]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "旅行プラン")

        self.assertIn("해운대 해수욕장", repaired)
        self.assertIn(beach_url, repaired)
        self.assertNotIn("씨라이프 부산 아쿠아리움", repaired)
        self.assertNotIn(sea_url, repaired)

    def test_repair_removes_food_with_url_from_morning_slot(self) -> None:
        """Production case: food card WITH injected URL must be removed from 午前 slot."""
        profile = {
            "plan_mode": True,
            "days": 5,
            "regions": ["gyeongsang"],
            "regionCities": "부산",
        }
        food_url = "https://map.naver.com/p/search/%EA%B3%A0%ED%96%A5%EC%97%B0%ED%99%94"
        # After _repair_itinerary_place_urls injects URL for 고향연화
        reply = "\n".join([
            "3日目(해운대 지역)",
            "午前",
            "해동 용궁사 부산",
            "고향연화",
            food_url,
            "海を向いた絶景の寺院です。",
        ])
        places = [
            self._restaurant("고향연화", "부산광역시 기장군 기장읍 연화길 33-8", food_url),
        ]

        repaired = _repair_wizard_itinerary_rules(reply, places, profile, "旅行プラン")

        self.assertIn("해동 용궁사 부산", repaired)
        self.assertNotIn("고향연화", repaired)
        self.assertNotIn(food_url, repaired)


if __name__ == "__main__":
    unittest.main()
