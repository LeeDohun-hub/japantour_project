import pytest

from src.api.hotel_area_filter import address_matches_hotel_area
from src.api.visitkorea_client import wizard_to_kto_codes


def test_seoul_jung_gu_maps_to_tourapi_district_code() -> None:
    assert wizard_to_kto_codes("서울특별시", "중구") == ("1", "24")


def test_seoul_district_labels_with_suffix_map_correctly() -> None:
    assert wizard_to_kto_codes("서울특별시", "강남구") == ("1", "1")
    assert wizard_to_kto_codes("서울특별시", "종로구") == ("1", "23")


@pytest.mark.parametrize(
    ("sido", "sigungu", "expected"),
    [
        ("부산광역시", "해운대구", ("6", "16")),
        ("대구광역시", "수성구", ("4", "7")),
        ("인천광역시", "연수구", ("2", "8")),
        ("광주광역시", "광산구", ("5", "1")),
        ("대전광역시", "유성구", ("3", "4")),
        ("울산광역시", "울주군", ("7", "5")),
        ("세종특별자치시", "세종시", ("8", "1")),
        ("경기도", "김포시", ("31", "8")),
        ("충청남도", "계룡시", ("34", "10")),
        ("제주특별자치도", "서귀포시", ("39", "3")),
    ],
)
def test_nationwide_tourapi_district_codes(
    sido: str, sigungu: str, expected: tuple[str, str]
) -> None:
    assert wizard_to_kto_codes(sido, sigungu) == expected


def test_composite_city_district_address_is_strict() -> None:
    assert address_matches_hotel_area(
        "경기도 성남시 분당구 판교역로 1", "경기도", "성남시 분당구"
    )
    assert not address_matches_hotel_area(
        "경기도 성남시 수정구 산성대로 1", "경기도", "성남시 분당구"
    )


def test_metropolitan_district_address_is_strict() -> None:
    assert address_matches_hotel_area(
        "부산광역시 해운대구 달맞이길 1", "부산광역시", "해운대구"
    )
    assert not address_matches_hotel_area(
        "부산광역시 중구 남포동 1", "부산광역시", "해운대구"
    )
