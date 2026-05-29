"""Shared destination region resolution helpers.

Keep UI city IDs, canonical itinerary areas, and address filters in one place so
the planner and the map-card enrichment endpoint make the same decision.
"""

from __future__ import annotations

from typing import Any


REGION_CITY_ID_TO_ITINERARY_AREA: dict[str, str] = {
    "seoul:jongno": "종로",
    "seoul:jung": "명동",
    "seoul:mapo": "홍대",
    "seoul:gangnam": "강남",
    "seoul:seongdong": "성수동",
    "seoul:yongsan": "이태원",
    "seoul:dongdaemun": "동대문",
    "seoul:songpa": "잠실",
    "seoul:yeongdeungpo": "여의도",
    "gyeonggi:goyang": "고양",
    "gyeonggi:suwon": "수원",
    "gyeonggi:seongnam": "성남",
    "gyeonggi:yongin": "용인",
    "gyeonggi:bucheon": "부천",
    "gyeonggi:anyang": "안양",
    "gyeonggi:paju": "파주",
    "gyeonggi:gwangju_si": "경기광주",
    "gyeonggi:gapyeong": "가평",
    "gyeonggi:hwaseong": "화성",
    "gyeonggi:ansan": "안산",
    "gyeonggi:ansan_danwon": "안산",
    "gyeonggi:ansan_sangnok": "안산",
    "gyeonggi:siheung": "시흥",
    "gyeonggi:namyangju": "남양주",
    "gyeonggi:pyeongtaek": "평택",
    "incheon:michuhol": "인천",
    "incheon:yeonsu": "송도",
    "incheon:bupyeong": "인천",
    "incheon:jung": "인천",
    "incheon:namdong": "인천",
    "incheon:seogu": "인천",
    "gangwon:gangneung": "강릉",
    "gangwon:sokcho": "속초",
    "gangwon:chuncheon": "춘천",
    "gangwon:pyeongchang": "평창",
    "gangwon:yangyang": "양양",
    "gangwon:goseong": "고성",
    "gangwon:wonju": "원주",
    "gangwon:hongcheon": "홍천",
    "chungcheong:daejeon": "대전",
    "chungcheong:yuseong": "유성",
    "chungcheong:cheonan": "천안",
    "chungcheong:gongju": "공주",
    "chungcheong:buyeo": "부여",
    "chungcheong:boryeong": "보령",
    "chungcheong:chungju": "충주",
    "chungcheong:cheongju": "청주",
    "chungcheong:sejong": "세종",
    "jeolla:jeonju": "전주",
    "jeolla:yeosu": "여수",
    "jeolla:mokpo": "목포",
    "jeolla:suncheon": "순천",
    "jeolla:damyang": "담양",
    "jeolla:gunsan": "군산",
    "jeolla:gwangju": "광주",
    "gyeongsang:busan_haeundae": "해운대",
    "gyeongsang:busan_jung": "부산",
    "gyeongsang:gyeongju": "경주",
    "gyeongsang:daegu": "대구",
    "gyeongsang:ulsan": "울산",
    "gyeongsang:changwon": "창원",
    "gyeongsang:geoje": "거제",
    "gyeongsang:goseong_gn": "경남고성",
    "gyeongsang:pohang": "포항",
    "gyeongsang:andong": "안동",
    "jeju:jeju_city": "제주",
    "jeju:seogwipo": "서귀포",
}


REGION_ADDR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gangwon": (
        "강원", "gangwon", "강릉", "속초", "평창", "고성군", "춘천", "원주", "정선", "태백", "동해",
        "gangneung", "sokcho", "chuncheon", "wonju", "pyeongchang", "goseong",
    ),
    "busan": ("부산", "busan", "해운대", "기장", "사하", "사상", "dongnae", "haeundae"),
    "jeju": ("제주", "jeju", "seogwipo", "서귀포"),
    "gyeonggi": (
        "경기", "gyeonggi", "고양", "수원", "성남", "용인", "안양", "과천", "의정부", "파주",
        "부천", "시흥", "안산", "대부도", "단원구", "상록구", "화성", "광주시", "경기도 광주", "곤지암", "남한산성",
        "goyang", "suwon", "seongnam", "yongin", "anyang", "bucheon", "paju", "ilsan",
        "namyangju", "hwaseong", "ansan", "daebudo", "danwon", "sangnok", "gwangju-si",
    ),
    "seoul": ("서울", "seoul", "mapo", "gangnam", "myeongdong", "jongno", "hongdae"),
    "incheon": ("인천", "incheon", "영종", "영종도", "songdo", "yeongjong", "yeongjongdo"),
    "chungcheong": (
        "충청", "chungcheong", "대전", "청주", "충주", "천안", "공주", "세종", "충북", "충남",
        "daejeon", "cheongju", "cheonan", "sejong", "chungju",
    ),
    "jeolla": (
        "전라", "jeolla", "전주", "광주광역시", "여수", "목포", "순천", "나주",
        "jeonju", "gwangju metropolitan", "yeosu", "mokpo", "suncheon",
    ),
    "gyeongsang": (
        "경상", "gyeongsang", "대구", "경주", "창원", "포항", "울산", "진주", "거제", "고성", "경북", "경남",
        "daegu", "gyeongju", "changwon", "pohang", "ulsan", "jinju", "geoje", "goseong",
    ),
}


CITY_ID_ADDR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gyeonggi:gwangju_si": (
        "경기도 광주", "광주시", "gwangju-si", "gwangju si", "gonjiam", "곤지암", "남한산성",
    ),
    "gyeonggi:ansan": (
        "안산", "안산시", "대부도", "단원구", "상록구", "ansan", "daebudo", "danwon", "sangnok",
    ),
    "gyeonggi:ansan_danwon": (
        "안산", "안산시", "대부도", "단원구", "ansan", "daebudo", "danwon",
    ),
    "gyeonggi:ansan_sangnok": (
        "안산", "안산시", "상록구", "ansan", "sangnok",
    ),
    "gangwon:goseong": (
        "강원 고성", "강원도 고성", "강원특별자치도 고성", "강원", "gangwon-do",
        "gangwon do", "gangwon", "goseong-gun", "ganseong", "geojin", "toseong",
        "간성", "거진", "토성", "현내", "죽왕",
    ),
    "gyeongsang:goseong_gn": (
        "경남 고성", "경상남도 고성", "경남", "gyeongsangnam-do", "gyeongsangnam do",
        "gyeongnam", "goseong-eup", "dong-oe-ri", "songhak-ro", "고성읍", "동외리",
    ),
    "jeolla:gwangju": (
        "광주광역시", "gwangju metropolitan", "gwangju, south korea", "gwangju-si, gwangju",
        "gwangsan-gu", "buk-gu, gwangju", "dong-gu, gwangju", "seo-gu, gwangju", "nam-gu, gwangju",
    ),
}


CITY_ID_ADDR_NEGATIVE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "jeolla:gwangju": (
        "경기도 광주", "경기광주", "gyeonggi-do", "gyeonggi do", "gwangju-si, gyeonggi",
        "gwangju-si, gyeonggi-do", "gwangju si, gyeonggi", "gonjiam", "곤지암", "남한산성",
    ),
    "gyeonggi:gwangju_si": (
        "광주광역시", "gwangju metropolitan", "gwangju, south korea",
        "gwangsan-gu", "buk-gu, gwangju", "dong-gu, gwangju", "seo-gu, gwangju", "nam-gu, gwangju",
    ),
    "gangwon:goseong": (
        "경상남도", "경남", "gyeongsangnam-do", "gyeongsangnam do", "gyeongnam",
        "goseong-eup", "dong-oe-ri", "songhak-ro", "고성읍", "동외리",
    ),
    "gyeongsang:goseong_gn": (
        "강원도", "강원특별자치도", "gangwon-do", "gangwon do", "ganseong", "geojin",
        "toseong", "간성", "거진", "토성", "현내", "죽왕",
    ),
}


def region_city_ids_from_profile(profile: dict[str, Any] | None) -> list[str]:
    if not profile:
        return []
    raw = profile.get("regionCityIds") or profile.get("region_city_ids") or []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for item in raw:
        key = str(item or "").strip().lower()
        if key and key not in out:
            out.append(key)
    for meta in profile.get("regionCityMeta") or profile.get("region_city_meta") or []:
        if not isinstance(meta, dict):
            continue
        key = str(meta.get("key") or "").strip().lower()
        if not key and meta.get("region") and meta.get("id"):
            key = f"{str(meta.get('region')).lower()}:{str(meta.get('id')).lower()}"
        if key and key not in out:
            out.append(key)
    return out


def areas_from_region_city_ids(profile: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for key in region_city_ids_from_profile(profile):
        area = REGION_CITY_ID_TO_ITINERARY_AREA.get(key)
        if area and area not in seen:
            seen.add(area)
            out.append(area)
    return out


def address_matches_destination(
    address: str,
    *,
    region_city_ids: list[str] | None = None,
    dest_regions: list[str] | None = None,
) -> bool:
    a = (address or "").lower()
    ids = [str(x).strip().lower() for x in (region_city_ids or []) if str(x).strip()]
    if ids:
        negative_kws = [
            kw.lower()
            for cid in ids
            for kw in CITY_ID_ADDR_NEGATIVE_KEYWORDS.get(cid, ())
        ]
        if negative_kws and any(kw in a for kw in negative_kws):
            return False
        city_kws = [kw.lower() for cid in ids for kw in CITY_ID_ADDR_KEYWORDS.get(cid, ())]
        if city_kws:
            return any(kw in a for kw in city_kws)
    regions = [str(r).strip().lower() for r in (dest_regions or []) if str(r).strip()]
    if not regions:
        return True
    return any(any(kw.lower() in a for kw in REGION_ADDR_KEYWORDS.get(reg, ())) for reg in regions)


def selected_destination_context(profile: dict[str, Any] | None) -> str:
    ids = region_city_ids_from_profile(profile)
    if not ids:
        return ""
    lines = ["=== Selected destination IDs ==="]
    for key in ids:
        canonical = REGION_CITY_ID_TO_ITINERARY_AREA.get(key, "")
        if canonical:
            lines.append(f"- {key} => canonical itinerary area: {canonical}")
    if len(lines) == 1:
        return ""
    lines.append("Use these IDs as the source of truth before interpreting free-text area names.")
    lines.append("If a city name is ambiguous, follow the canonical area above.")
    return "\n".join(lines)
