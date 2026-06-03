from __future__ import annotations

import unittest

from src.api.region_resolver import (
    address_matches_destination,
    areas_from_region_city_ids,
    region_city_ids_from_profile,
    selected_destination_context,
)

try:
    from src.api.google_places_client import NearbyPlace
    from src.chain.router import (
        _combine_itinerary_place_candidates,
        _detect_itinerary_areas,
        _expanded_tourism_areas_for_plan,
        _fmt_itinerary_daily_area_binding,
        _repair_wizard_itinerary_rules,
        _tourism_candidate_areas_for_plan,
    )
except ModuleNotFoundError as exc:
    NearbyPlace = None
    _combine_itinerary_place_candidates = None
    _detect_itinerary_areas = None
    _expanded_tourism_areas_for_plan = None
    _fmt_itinerary_daily_area_binding = None
    _repair_wizard_itinerary_rules = None
    _tourism_candidate_areas_for_plan = None
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


if __name__ == "__main__":
    unittest.main()
