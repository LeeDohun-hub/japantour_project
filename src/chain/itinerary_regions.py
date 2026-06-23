"""Region/area resolution helpers.

숙소 위치 판별, 장소-에리어 매칭, 에리어 집합 결정, 일정 에리어 바인딩 등.
router.py에서 추출한 함수 모음 — 동작은 완전히 동일하다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api.places_client import NearbyPlace


# ─── 숙소 기반 맛집 에리어 ────────────────────────────────────────────────────

def _accommodation_food_areas(traveler_profile: dict | None) -> list[str]:
    """宿泊先近郊 맛집 검색용 에리어 (到着日夕食用)."""
    if not traveler_profile:
        return []
    accom = traveler_profile.get("accommodation") or {}
    if accom.get("type") not in ("friend", "decided", "undecided"):
        return []
    text = " ".join(
        str(accom.get(k) or "")
        for k in ("address", "detail", "name", "region")
    ).lower()
    areas: list[str] = []
    if any(k in text for k in ("고양", "goyang", "高陽", "コヤン", "일산", "화정", "대화", "덕양")):
        areas.append("고양")
    if any(k in text for k in ("인천", "incheon", "仁川")):
        areas.append("인천")
    if any(k in text for k in ("수원", "suwon")):
        areas.append("수원")
    if any(k in text for k in ("부천", "bucheon")):
        areas.append("부천")
    if any(k in text for k in ("대전", "daejeon", "大田", "テジョン", "デジョン", "유성", "儒城", "yuseong")):
        areas.append("대전")
    if any(k in text for k in ("충청", "忠清", "chungcheong")):
        areas.append("대전")
    return areas


_SUDOGWON_ACCOM_KWS: tuple[str, ...] = (
    "서울", "seoul", "고양", "goyang", "일산", "ilsan", "화정", "행신",
    "인천", "incheon", "수원", "suwon", "경기", "gyeonggi",
    "부천", "bucheon", "안양", "성남", "용인", "의정부",
    "김포", "gimpo", "파주", "paju", "남양주", "과천",
)

# 수도권 에리어 집합 — _accom_is_sudogwon에서 사용하기 위해 여기에 정의
_SUDOGWON_AREAS: frozenset[str] = frozenset({
    "명동", "홍대", "강남", "동대문", "인사동", "이태원",
    "성수동", "압구정", "한강", "광장시장",
    "고양", "인천", "수원", "송도", "화정",
})


def _accom_is_sudogwon(traveler_profile: dict | None) -> bool:
    """숙소가 수도권(서울·경기·인천)인지 확인."""
    if not traveler_profile:
        return False
    accom_areas = _accommodation_food_areas(traveler_profile)
    if accom_areas:
        return any(a in _SUDOGWON_AREAS for a in accom_areas)
    accom = traveler_profile.get("accommodation") or {}
    text = " ".join(
        str(accom.get(k) or "") for k in ("address", "detail", "name", "region")
    ).lower()
    if not text.strip():
        return False
    return any(k in text for k in _SUDOGWON_ACCOM_KWS)


# ─── 지역 판별 키워드 ─────────────────────────────────────────────────────────

_GOYANG_LOCATION_KEYWORDS: tuple[str, ...] = (
    "고양", "goyang",
    "일산", "ilsan", "ilsandong", "ilsanseo", "화정", "덕양", "deokyang",
    "hosu-ro", "호수", "todang", "토당", "능곡", "행신", "대화", "탄현",
    "주엽", "킨텍스", "kintex", "高陽", "コヤン",
)

_GYEONGGI_NON_GOYANG_KEYWORDS: tuple[str, ...] = (
    "화성", "hwaseong",
    "부천", "bucheon",
    "수원", "suwon",
    "성남", "seongnam",
    "안양", "anyang",
    "안산", "ansan",
    "의정부", "uijeongbu",
    "평택", "pyeongtaek",
    "시흥", "siheung",
    "하남", "hanam",
    "용인", "yongin",
    "광명", "gwangmyeong",
    "군포", "gunpo",
    "오산", "osan",
    "이천", "icheon-si",
    "안성", "anseong",
    "포천", "pocheon",
    "양주", "yangju",
    "동두천", "dongducheon",
    "과천", "gwacheon",
    "의왕", "uiwang",
)
_INCHEON_LOCATION_KEYWORDS: tuple[str, ...] = (
    "인천", "incheon", "미추홀", "michuhol", "연수", "yeonsu", "부평", "bupyeong",
    "문학", "munhak", "송도", "songdo", "랜더스", "landers", "仁川",
)
_SEOUL_LOCATION_KEYWORDS: tuple[str, ...] = (
    "서울", "seoul", "jung district", "명동", "myeongdong", "홍대", "hongdae",
    "강남", "gangnam", "동대문", "dongdaemun", "弘大", "明洞", "江南",
)
_SEOUL_SUB_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "명동": ("명동", "myeongdong", "明洞", "jung district", "중구"),
    "홍대": ("홍대", "hongdae", "弘大", "mapo", "마포", "상수", "합정", "연남", "망원"),
    "강남": ("강남", "gangnam", "江南", "역삼", "신논현", "삼성동"),
    "동대문": ("동대문", "dongdaemun", "東大門", "ddp", "을지로"),
    "인사동": ("인사동", "insadong", "仁寺洞", "종로", "jongno"),
    "이태원": ("이태원", "itaewon", "梨泰院", "용산", "yongsan"),
    "성수동": ("성수", "성수동", "seongsu", "城東", "seongdong"),
    "압구정": ("압구정", "apgujeong", "청담", "cheongdam"),
    "여의도": ("여의도", "yeouido", "汝矣島", "ifc", "더현대"),
    "잠실": ("잠실", "jamsil", "蚕室", "송파", "songpa"),
}

_SEOUL_SUB_AREAS: frozenset[str] = frozenset({
    *_SEOUL_SUB_AREA_KEYWORDS.keys(),
    "한강", "광장시장",
})


# ─── 장소 blob helpers ────────────────────────────────────────────────────────

def _place_location_blob(place: NearbyPlace) -> str:
    return f"{place.name or ''} {place.address or ''} {place.search_area or ''}".lower()


def _place_geo_blob(place: NearbyPlace) -> str:
    """실제 장소 자체의 이름·주소만 사용. 검색어 라벨(search_area)은 지역 판정에서 제외."""
    return f"{place.name or ''} {place.address or ''}".lower()


def _place_address_blob(place: NearbyPlace) -> str:
    """체인명에 들어간 지명(예: 홍대개미 용산점)을 지역 판정 신호로 쓰지 않기 위한 주소 전용 blob."""
    return f"{place.address or ''}".lower()


def _blob_has_any(blob: str, keywords: tuple[str, ...]) -> bool:
    return any(k.lower() in blob for k in keywords)


# ─── 장소 zone 판별 ──────────────────────────────────────────────────────────

def _place_in_goyang_zone(place: NearbyPlace) -> bool:
    blob = _place_geo_blob(place)
    if _blob_has_any(blob, _GYEONGGI_NON_GOYANG_KEYWORDS):
        return False
    return _blob_has_any(blob, _GOYANG_LOCATION_KEYWORDS)


def _place_in_incheon_zone(place: NearbyPlace) -> bool:
    blob = _place_geo_blob(place)
    if _blob_has_any(blob, _GOYANG_LOCATION_KEYWORDS):
        return False
    return _blob_has_any(blob, _INCHEON_LOCATION_KEYWORDS)


def _place_in_seoul_zone(place: NearbyPlace) -> bool:
    blob = _place_geo_blob(place)
    if _blob_has_any(blob, _GOYANG_LOCATION_KEYWORDS + _INCHEON_LOCATION_KEYWORDS):
        return False
    return _blob_has_any(blob, _SEOUL_LOCATION_KEYWORDS)


def _place_in_seoul_sub_area(place: NearbyPlace, area: str) -> bool:
    blob = _place_address_blob(place)
    keywords = _SEOUL_SUB_AREA_KEYWORDS.get(area)
    if not keywords:
        return _place_in_seoul_zone(place)
    if not _place_in_seoul_zone(place):
        return False
    return _blob_has_any(blob, keywords)


def _place_in_stay_zone(place: NearbyPlace, stay_areas: list[str]) -> bool:
    if not stay_areas:
        return False
    for area in stay_areas:
        if area in _SEOUL_SUB_AREAS and _place_in_seoul_sub_area(place, area):
            return True
        if area in _SUDOGWON_AREAS and area.lower() in _place_location_blob(place):
            return True
    if "고양" in stay_areas and _place_in_goyang_zone(place):
        return True
    if "인천" in stay_areas and _place_in_incheon_zone(place):
        return True
    if "수원" in stay_areas and "수원" in _place_location_blob(place):
        return True
    if "대전" in stay_areas and "대전" in _place_location_blob(place):
        return True
    return False


def _needs_accommodation_buffer_candidates(
    traveler_profile: dict | None,
    travel_areas: list[str],
) -> bool:
    """遠方観光＋首都圏宿泊時、帰還日・予備日に宿泊周辺候補が必要."""
    if not traveler_profile or not travel_areas:
        return False
    if not _accom_is_sudogwon(traveler_profile):
        return False
    from src.chain.router import _NON_SUDOGWON_AREAS  # lazy import
    return any(a in _NON_SUDOGWON_AREAS for a in travel_areas)


# ─── 희망 에리어 결정 ─────────────────────────────────────────────────────────

def _tourism_search_areas(traveler_profile: dict | None) -> list[str]:
    """🗺希望エリア（regions・重点都市）から Places 검색・일정의 주에리어를 결정."""
    from src.chain.router import (  # lazy import
        _MAX_ITINERARY_AREAS,
        _areas_from_region_city_ids,
        _region_area_keys,
        _REGION_AREA_KEY_TO_AREAS,
        _region_cities_text,
        _areas_from_region_cities,
        _profile_has_landers_focus,
        _REGION_CHIP_TO_AREAS,
        _REGION_DEFAULT_AREAS,
    )
    if not traveler_profile:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(area: str) -> None:
        a = area.strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)

    for a in _areas_from_region_city_ids(traveler_profile):
        add(a)
    if out:
        return out[:_MAX_ITINERARY_AREAS]

    for key in _region_area_keys(traveler_profile):
        for area in _REGION_AREA_KEY_TO_AREAS.get(key, []):
            add(area)
    if out:
        return out[:_MAX_ITINERARY_AREAS]

    cities = _region_cities_text(traveler_profile)
    if cities:
        for a in _areas_from_region_cities(cities):
            add(a)
        if _profile_has_landers_focus(traveler_profile):
            add("인천")
        if out:
            return out[:_MAX_ITINERARY_AREAS]

    for reg in traveler_profile.get("regions") or []:
        key = str(reg).lower()
        for area in _REGION_CHIP_TO_AREAS.get(key, _REGION_DEFAULT_AREAS.get(key, [])):
            add(area)

    return out[:_MAX_ITINERARY_AREAS]


def _detect_itinerary_areas(
    user_message: str,
    keyword: str,
    traveler_profile: dict | None,
) -> list[str]:
    """프롬프트·프로필에서 일정용 에리어 목록 추출（🗺希望エリア優先）."""
    from src.chain.router import (  # lazy import
        _ITINERARY_AREAS,
        _region_cities_text,
        _REGION_DEFAULT_AREAS,
        _prefers_gyeonggi_gwangju,
        _prioritize_itinerary_areas,
    )
    areas: list[str] = []
    if traveler_profile:
        for a in _tourism_search_areas(traveler_profile):
            if a not in areas:
                areas.append(a)

    parts = [user_message, keyword]
    if traveler_profile:
        cities = _region_cities_text(traveler_profile)
        if cities:
            parts.append(cities)
        for reg in traveler_profile.get("regions") or []:
            parts.append(str(reg))

    text = " ".join(parts).lower()
    gyeonggi_gwangju = _prefers_gyeonggi_gwangju(traveler_profile, text)
    for kw, area in _ITINERARY_AREAS.items():
        if area == "광주" and gyeonggi_gwangju:
            continue
        if kw.lower() in text and area not in areas:
            areas.append(area)

    if not areas and traveler_profile:
        for reg in traveler_profile.get("regions") or []:
            for area in _REGION_DEFAULT_AREAS.get(str(reg).lower(), []):
                if area not in areas:
                    areas.append(area)
        accom = traveler_profile.get("accommodation") or {}
        accom_text = " ".join(
            str(accom.get(k) or "") for k in ("address", "detail", "name", "region")
        )
        if accom_text.strip():
            for kw, area in _ITINERARY_AREAS.items():
                if kw.lower() in accom_text.lower() and area not in areas:
                    areas.append(area)

    return _prioritize_itinerary_areas(areas, traveler_profile)


def _fmt_itinerary_daily_area_binding(traveler_profile: dict | None) -> str:
    """LLM向け: 🗺希望エリアを日別に割当（宿泊先の市区だけで決めない）."""
    from src.chain.router import (  # lazy import
        _region_area_keys,
        _region_cities_text,
        _profile_has_landers_focus,
        _REGION_CHIP_LABELS_JA,
        _areas_from_region_city_ids,
        _tourism_candidate_areas_for_plan,
        _NON_SUDOGWON_AREAS,
        _profile_has_daejeon_focus,
        _should_include_seongsimdang,
        _areas_for_region_bucket,
    )
    if not traveler_profile:
        return ""
    region_order = _region_area_keys(traveler_profile) or [
        str(r).lower() for r in (traveler_profile.get("regions") or [])
    ]
    if not region_order:
        return ""

    cities = _region_cities_text(traveler_profile)
    landers = _profile_has_landers_focus(traveler_profile)

    hope_labels = [
        _REGION_CHIP_LABELS_JA.get(r, r) for r in region_order
    ]
    lines = [
        "=== 日程×エリア割当（🗺希望エリア最優先 — 宿泊先だけで観光・食事を決めない）===",
        f"【希望エリア】{'・'.join(hope_labels)}",
    ]
    if cities:
        lines.append(f"【重点都市・区】{cities}（この指定を各日の中心にする）")
    accom = traveler_profile.get("accommodation") or {}
    if accom.get("address") or accom.get("name"):
        lines.append(
            "【宿泊先】移動・チェックインの到着地点のみ。"
            "宿泊エリアと異なる希望エリアの観光・食事は2日目以降に配置する。"
        )

    lines.append(
        "1日目: 空港到着・入国・宿泊先へ移動・チェックイン・休息。"
        "観光スポット・レストラン名は原則書かない（深夜到着は宿泊先で休息のみ）。"
    )
    selected_city_areas = _areas_from_region_city_ids(traveler_profile)
    total_days = int(traveler_profile.get("days") or 0) if traveler_profile else 0
    if selected_city_areas:
        city_label = "・".join(selected_city_areas[:3])
        fallback_areas = [
            a for a in _tourism_candidate_areas_for_plan(traveler_profile)
            if a not in selected_city_areas
        ]
        fallback_label = "・".join(fallback_areas[:4])
        usable_scope = (
            f"{city_label}（候補不足時のみ近接観光圏: {fallback_label}）"
            if fallback_label else city_label
        )
        last_regular_day = max(2, total_days - 1) if total_days else 4
        lines.extend(
            [
                f"【選択都市中心】ユーザーは下位地域として {city_label} を選択済み。"
                "旅行の中心地名はこの選択都市のまま維持する。",
                (
                    f"候補が少ない小規模市郡のため、{city_label} 内候補を最優先し、"
                    f"不足時だけ {fallback_label} の近接観光圏候補を補助利用可。"
                    if fallback_label else
                    "広域名から他都市へ拡張せず、観光・食事はこの選択都市を中心に組む。"
                ),
                f"2日目: 宿泊先から {city_label} へ移動し、到着後は {usable_scope} の具体スポット・昼食・夕食を配置する。",
            ]
        )
        if last_regular_day > 3:
            lines.append(
                f"3日目〜{last_regular_day - 1}日目: {usable_scope} 内でエリアを分けて観光・食事。"
                "同じ店・同じスポットの再利用は禁止。"
            )
        lines.append(
            f"{last_regular_day}日目: 午前〜昼食までは {usable_scope} で具体スポット1件＋具体昼食1件を配置し、"
            "午後に宿泊先へ戻る移動ブロックを置く。帰還日を抽象的な休息だけで終わらせない。"
            f"【帰還日夕食厳禁】午後に宿泊先へ戻った後は、 {usable_scope} （観光目的地）の飲食店候補を夕食に使わない。"
            "帰還後の夕食ブロックは丸ごと省略して「夜: 宿泊先で休息」で締めること（観光目的地の食事候補は昼食までで打ち切り）。"
        )
        lines.append(
            "※ 代替時も、まず選択都市内で再検索・代替する。"
            "それでも候補が足りない場合だけ、明示された近接観光圏を使う。"
        )
        return "\n".join(lines) + "\n"

    travel_areas = _tourism_search_areas(traveler_profile)
    non_sudo_targets = [a for a in travel_areas if a in _NON_SUDOGWON_AREAS]
    if non_sudo_targets and _accom_is_sudogwon(traveler_profile):
        dest_label = "・".join(non_sudo_targets[:4])
        last_regular_day = max(2, total_days - 1) if total_days else 4
        lines.extend(
            [
                f"【遠方目的地滞在固定】ユーザーは {dest_label} を観光目的地に選択済み。",
                "2日目に宿泊先から目的地エリアへ移動した後、帰還日午後までは目的地側に滞在している前提で組む。",
                "この滞在期間中の観光・昼食・夕食は目的地エリア候補のみ。ソウル・京畿・宿泊エリア候補は絶対に混ぜない。",
                f"2日目: 宿泊先→{non_sudo_targets[0]} への広域移動を最初に置き、到着後は {non_sudo_targets[0]} 周辺の具体スポット・昼食・夕食。",
            ]
        )
        middle_days = list(range(3, last_regular_day))
        for offset, d in enumerate(middle_days):
            area = non_sudo_targets[min(offset + 1, len(non_sudo_targets) - 1)]
            lines.append(
                f"{d}日目: {area} 周辺に滞在。朝に首都圏宿泊先へ戻らず、"
                f"{area} 周辺の具体スポット・昼食・夕食だけで構成する。"
            )
        if last_regular_day >= 3:
            return_area = non_sudo_targets[min(len(middle_days) + 1, len(non_sudo_targets) - 1)]
            lines.append(
                f"{last_regular_day}日目: 午前〜昼食は {return_area} 周辺で具体スポット1件＋具体昼食1件。"
                "午後に首都圏宿泊先または空港圏へ戻る移動ブロックを置き、帰還後の夕食だけ宿泊エリア候補を使用可。"
            )
        lines.append(
            "※ 遠方滞在中に「宿泊先周辺」「帰還日・宿泊エリア」「ソウル/京畿の店」を挿入するのは禁止。"
            "代替時も目的地エリア内で件数を減らすか、移動・休息に置き換える。"
        )
        return "\n".join(lines) + "\n"

    day = 2
    for reg in region_order:
        if reg == "incheon":
            extra = "（ランダースフィールド・文鶴・スポーツ観戦）" if landers else ""
            lines.append(
                f"{day}日目: 仁川エリアの観光・食事{extra}。"
                "食事は【仁川・希望エリア】の候補のみ。京畿・ソウルの店は禁止。"
            )
            day += 1
        elif reg == "gyeonggi":
            areas = "・".join(_areas_for_region_bucket(reg, _tourism_search_areas(traveler_profile))[:3]) or "京畿道"
            lines.append(
                f"{day}日目: 京畿道（{areas}）の観光・食事。"
                "食事は【京畿・希望エリア】の候補のみ。仁川・ソウルの店は禁止。"
            )
            day += 1
        elif reg == "seoul":
            lines.append(
                f"{day}日目: ソウル（明洞・弘大など）の観光・食事。"
                "食事は【ソウル・希望エリア】の候補のみ。"
            )
            day += 1
        elif reg == "chungcheong":
            label = _REGION_CHIP_LABELS_JA.get(reg, reg)
            areas = "・".join(_areas_for_region_bucket(reg, _tourism_search_areas(traveler_profile))[:3]) or "大田・忠清"
            sd = ""
            if _profile_has_daejeon_focus(traveler_profile) and _should_include_seongsimdang(
                traveler_profile
            ):
                sd = "（大田名物 **성심당（ソンシムダン）** をカフェ・軽食またはお土産で必ず1回）"
            lines.append(
                f"{day}日目: {label}（{areas}）の観光・食事{sd}。"
                "食事は【忠清・希望エリア】の候補のみ。"
            )
            day += 1
        else:
            label = _REGION_CHIP_LABELS_JA.get(reg, reg)
            lines.append(
                f"{day}日目: {label} の観光・食事（該当希望エリアの候補のみ）。"
            )
            day += 1

    lines.append(
        "※ 2日目以降は上記の希望エリア順に日程を組む。"
        "各日の食事は該当セクションの地図URLのみ。他エリアの候補を別日に流用しない。"
    )
    return "\n".join(lines) + "\n"


# ─── 리전 시티 텍스트 및 토큰 파싱 ────────────────────────────────────────────

def _region_cities_text(traveler_profile: dict | None) -> str:
    if not traveler_profile:
        return ""
    return str(traveler_profile.get("regionCities") or "").strip()


def _parse_region_city_tokens(text: str) -> list[str]:
    from src.chain.router import _RE_REGION_CITY_SPLIT  # lazy import
    if not text:
        return []
    tokens: list[str] = []
    for part in _RE_REGION_CITY_SPLIT.split(text):
        t = " ".join(part.split()).strip()
        if len(t) >= 2:
            tokens.append(t)
    return tokens
