from __future__ import annotations

import unittest

from src.api.region_resolver import (
    address_matches_destination,
    areas_from_region_city_ids,
    region_city_ids_from_profile,
    selected_destination_context,
)

try:
    from src.chain.router import _detect_itinerary_areas
except ModuleNotFoundError as exc:
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


if __name__ == "__main__":
    unittest.main()
