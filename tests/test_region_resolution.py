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
    )
except ModuleNotFoundError as exc:
    NearbyPlace = None
    _combine_itinerary_place_candidates = None
    _detect_itinerary_areas = None
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


if __name__ == "__main__":
    unittest.main()
