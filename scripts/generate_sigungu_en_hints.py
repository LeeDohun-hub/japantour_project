"""Generate _SIGUNGU_EN_HINTS entries from wizard ADDR_DATA. Run to refresh hotel_area_filter.py block."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Revised Romanization stems (Places API 주소 표기 기준)
# fmt: off
_STEM: dict[str, tuple[str, ...]] = {
    # ── 광역·특별시 (구·군) ─────────────────────────────────────────────
    "계양구": ("gyeyang",),
    "강화군": ("ganghwa",),
    "옹진군": ("ongjin",),
    "광산구": ("gwangsan",),
    "울주군": ("ulju",),
    "세종시": ("sejong",),
    # ── 경기 ─────────────────────────────────────────────────────────
    "고양시 덕양구": ("deogyang", "goyang"),
    "고양시 일산동구": ("ilsandong", "goyang"),
    "고양시 일산서구": ("ilsanseo", "goyang"),
    "과천시": ("gwacheon",),
    "광명시": ("gwangmyeong",),
    "광주시": ("gwangju",),  # 경기 광주
    "구리시": ("guri",),
    "군포시": ("gunpo",),
    "김포시": ("gimpo",),
    "남양주시": ("namyangju",),
    "동두천시": ("dongducheon",),
    "부천시": ("bucheon",),
    "성남시 분당구": ("bundang", "seongnam"),
    "성남시 수정구": ("sujeong", "seongnam"),
    "성남시 중원구": ("jungwon", "seongnam"),
    "수원시 권선구": ("gwonseon", "suwon"),
    "수원시 영통구": ("yeongtong", "suwon"),
    "수원시 장안구": ("jangan", "suwon"),
    "수원시 팔달구": ("paldal", "suwon"),
    "시흥시": ("siheung",),
    "안산시 단원구": ("danwon", "ansan"),
    "안산시 상록구": ("sangnok", "ansan"),
    "안성시": ("anseong",),
    "안양시 동안구": ("dongan", "anyang"),
    "안양시 만안구": ("manan", "anyang"),
    "양주시": ("yangju",),
    "양평군": ("yangpyeong",),
    "여주시": ("yeoju",),
    "연천군": ("yeoncheon",),
    "오산시": ("osan",),
    "용인시 기흥구": ("giheung", "yongin"),
    "용인시 수지구": ("suji", "yongin"),
    "용인시 처인구": ("cheoin", "yongin"),
    "의왕시": ("uiwang",),
    "의정부시": ("uijeongbu",),
    "이천시": ("icheon",),
    "파주시": ("paju",),
    "평택시": ("pyeongtaek",),
    "포천시": ("pocheon",),
    "하남시": ("hanam",),
    "화성시": ("hwaseong",),
    # ── 강원 ─────────────────────────────────────────────────────────
    "강릉시": ("gangneung",),
    "고성군": ("goseong",),
    "동해시": ("donghae",),
    "삼척시": ("samcheok",),
    "속초시": ("sokcho",),
    "양구군": ("yanggu",),
    "양양군": ("yangyang",),
    "영월군": ("yeongwol",),
    "원주시": ("wonju",),
    "인제군": ("inje",),
    "정선군": ("jeongseon",),
    "철원군": ("cheorwon",),
    "춘천시": ("chuncheon",),
    "태백시": ("taebaek",),
    "평창군": ("pyeongchang",),
    "홍천군": ("hongcheon",),
    "화천군": ("hwacheon",),
    "횡성군": ("hoengseong",),
    # ── 충북 ─────────────────────────────────────────────────────────
    "괴산군": ("goesan",),
    "단양군": ("danyang",),
    "보은군": ("boeun",),
    "영동군": ("yeongdong",),
    "옥천군": ("okcheon",),
    "음성군": ("eumseong",),
    "제천시": ("jecheon",),
    "증평군": ("jeungpyeong",),
    "진천군": ("jincheon",),
    "청주시 서원구": ("seowon", "cheongju"),
    "청주시 상당구": ("sangdang", "cheongju"),
    "청주시 청원구": ("cheongwon", "cheongju"),
    "청주시 흥덕구": ("heungdeok", "cheongju"),
    "충주시": ("chungju",),
    # ── 충남 ─────────────────────────────────────────────────────────
    "계룡시": ("gyeryong",),
    "공주시": ("gongju",),
    "금산군": ("geumsan",),
    "논산시": ("nonsan",),
    "당진시": ("dangjin",),
    "보령시": ("boryeong",),
    "부여군": ("buyeo",),
    "서산시": ("seosan",),
    "서천군": ("seocheon",),
    "아산시": ("asan",),
    "예산군": ("yesan",),
    "천안시 동남구": ("dongnam", "cheonan"),
    "천안시 서북구": ("seobuk", "cheonan"),
    "청양군": ("cheongyang",),
    "태안군": ("taean",),
    "홍성군": ("hongseong",),
    # ── 전북 ─────────────────────────────────────────────────────────
    "고창군": ("gochang",),
    "군산시": ("gunsan",),
    "김제시": ("gimje",),
    "남원시": ("namwon",),
    "무주군": ("muju",),
    "부안군": ("buan",),
    "순창군": ("sunchang",),
    "완주군": ("wanju",),
    "익산시": ("iksan",),
    "임실군": ("imsil",),
    "장수군": ("jangsu",),
    "전주시 덕진구": ("deokjin", "jeonju"),
    "전주시 완산구": ("wansan", "jeonju"),
    "정읍시": ("jeongeup",),
    "진안군": ("jinan",),
    # ── 전남 ─────────────────────────────────────────────────────────
    "강진군": ("gangjin",),
    "고흥군": ("goheung",),
    "곡성군": ("gokseong",),
    "광양시": ("gwangyang",),
    "구례군": ("gurye",),
    "나주시": ("naju",),
    "담양군": ("damyang",),
    "목포시": ("mokpo",),
    "무안군": ("muan",),
    "보성군": ("boseong",),
    "순천시": ("suncheon",),
    "신안군": ("sinan",),
    "여수시": ("yeosu",),
    "영광군": ("yeonggwang",),
    "영암군": ("yeongam",),
    "완도군": ("wando",),
    "장성군": ("jangseong",),
    "장흥군": ("jangheung",),
    "진도군": ("jindo",),
    "함평군": ("hampyeong",),
    "해남군": ("haenam",),
    "화순군": ("hwasun",),
    # ── 경북 ─────────────────────────────────────────────────────────
    "경산시": ("gyeongsan",),
    "경주시": ("gyeongju",),
    "고령군": ("goryeong",),
    "구미시": ("gumi",),
    "김천시": ("gimcheon",),
    "문경시": ("mungyeong",),
    "봉화군": ("bonghwa",),
    "상주시": ("sangju",),
    "성주군": ("seongju",),
    "안동시": ("andong",),
    "영덕군": ("yeongdeok",),
    "영양군": ("yeongyang",),
    "영주시": ("yeongju",),
    "영천시": ("yeongcheon",),
    "예천군": ("yecheon",),
    "울릉군": ("ulleung",),
    "울진군": ("uljin",),
    "의성군": ("uiseong",),
    "청도군": ("cheongdo",),
    "청송군": ("cheongsong",),
    "칠곡군": ("chilgok",),
    "포항시 남구": ("nam", "pohang"),
    "포항시 북구": ("buk", "pohang"),
    # ── 경남 ─────────────────────────────────────────────────────────
    "거제시": ("geoje",),
    "거창군": ("geochang",),
    "김해시": ("gimhae",),
    "남해군": ("namhae",),
    "밀양시": ("miryang",),
    "사천시": ("sacheon",),
    "산청군": ("sancheong",),
    "양산시": ("yangsan",),
    "의령군": ("uiryeong",),
    "진주시": ("jinju",),
    "창녕군": ("changnyeong",),
    "창원시 마산합포구": ("masanhappo", "changwon"),
    "창원시 마산회원구": ("masanhoewon", "changwon"),
    "창원시 성산구": ("seongsan", "changwon"),
    "창원시 의창구": ("uichang", "changwon"),
    "창원시 진해구": ("jinhae", "changwon"),
    "통영시": ("tongyeong",),
    "하동군": ("hadong",),
    "함안군": ("haman",),
    "함양군": ("hamyang",),
    "합천군": ("hapcheon",),
    # ── 제주 ─────────────────────────────────────────────────────────
    "서귀포시": ("seogwipo",),
    "제주시": ("jeju",),
    # ── 대구 ─────────────────────────────────────────────────────────
    "달성군": ("dalseong",),
}
# fmt: on

# Manual overrides (Places 비표준 표기)
_OVERRIDES: dict[str, tuple[str, ...]] = {
    "강남구": ("gangnam-gu", "gangnam district", "gangnam"),
    "강동구": ("gangdong-gu", "gangdong district", "gangdong"),
    "강북구": ("gangbuk-gu", "gangbuk district", "gangbuk"),
    "강서구": ("gangseo-gu", "gangseo district", "gangseo"),
    "관악구": ("gwanak-gu", "gwanak district", "gwanak"),
    "광진구": ("gwangjin-gu", "gwangjin district", "gwangjin"),
    "구로구": ("guro-gu", "guro district", "guro"),
    "금천구": ("geumcheon-gu", "geumcheon district", "geumcheon"),
    "노원구": ("nowon-gu", "nowon district", "nowon"),
    "도봉구": ("dobong-gu", "dobong district", "dobong"),
    "동대문구": ("dongdaemun-gu", "dongdaemun district", "dongdaemun"),
    "동작구": ("dongjak-gu", "dongjak district", "dongjak"),
    "마포구": ("mapo-gu", "mapo district", "mapo"),
    "서대문구": ("seodaemun-gu", "seodaemun district", "seodaemun"),
    "서초구": ("seocho-gu", "seocho district", "seocho"),
    "성동구": ("seongdong-gu", "seongdong district", "seongdong"),
    "성북구": ("seongbuk-gu", "seongbuk district", "seongbuk"),
    "송파구": ("songpa-gu", "songpa district", "songpa"),
    "양천구": ("yangcheon-gu", "yangcheon district", "yangcheon"),
    "영등포구": ("yeongdeungpo-gu", "yeongdeungpo district", "yeongdeungpo"),
    "용산구": ("yongsan-gu", "yongsan district", "yongsan"),
    "은평구": ("eunpyeong-gu", "eunpyeong district", "eunpyeong"),
    "종로구": ("jongno-gu", "jongno district", "jongno", "jong-ro"),
    "중구": ("jung-gu", "jung district"),
    "중랑구": ("jungnang-gu", "jungnang district", "jungnang"),
    "미추홀구": ("michuhol-gu", "michuhol", "michuhol-gu"),
    "연수구": ("yeonsu-gu", "yeonsu district", "yeonsu"),
    "부평구": ("bupyeong-gu", "bupyeong district", "bupyeong"),
    "서구": ("seo-gu", "seo district"),
    "남동구": ("namdong-gu", "namdong district", "namdong"),
    "달서구": ("dalseo-gu", "dalseo district", "dalseo"),
    "수성구": ("suseong-gu", "suseong district", "suseong"),
    "금정구": ("geumjeong-gu", "geumjeong district", "geumjeong"),
    "기장군": ("gijang-gun", "gijang-eup", "gijang-gu", "gijang"),
    "남구": ("nam-gu", "nam district"),
    "동구": ("dong-gu", "dong district"),
    "동래구": ("dongnae-gu", "dongnae district", "dongnae"),
    "부산진구": ("busanjin district", "busanjin-gu", "busanjin"),
    "북구": ("buk-gu", "buk district"),
    "사상구": ("sasang-gu", "sasang district", "sasang"),
    "사하구": ("saha-gu", "saha district", "saha"),
    "수영구": ("suyeong-gu", "suyeong district", "suyeong"),
    "연제구": ("yeonje-gu", "yeonje district", "yeonje"),
    "영도구": ("yeongdo-gu", "yeongdo district", "yeongdo"),
    "해운대구": ("haeundae-gu", "haeundae district", "haeundae"),
    "대덕구": ("daedeok-gu", "daedeok district", "daedeok"),
    "유성구": ("yuseong-gu", "yuseong district", "yuseong"),
}


def _parse_addr_data() -> list[str]:
    text = (ROOT / "frontend" / "wizard.js").read_text(encoding="utf-8")
    start = text.index("const ADDR_DATA = {") + len("const ADDR_DATA = ")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                break
    items: list[str] = []
    for m in re.finditer(r'"([^"]+)":\s*\[([^\]]+)\]', blob):
        items.extend(re.findall(r'"([^"]+)"', m.group(2)))
    return sorted(set(items), key=lambda x: (len(x), x))


def _auto_hints(name: str, stems: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    # "○○시 △△구" — 구 힌트만 (시 힌트는 hotel_area_filter._CITY_SI_EN_HINTS + AND 매칭)
    if "시 " in name and name.endswith("구"):
        gu_stem = stems[0]
        out.extend((f"{gu_stem}-gu", f"{gu_stem} district", gu_stem))
    elif name.endswith("구"):
        gu_stem = stems[0]
        out.extend((f"{gu_stem}-gu", f"{gu_stem} district", gu_stem))
        for s in stems[1:]:
            out.extend((f"{s}-si", f"{s} city", s))
    elif name.endswith("군"):
        gun_stem = stems[0]
        out.extend((f"{gun_stem}-gun", f"{gun_stem} district", gun_stem))
    elif name.endswith("시"):
        si_stem = stems[0]
        out.extend((f"{si_stem}-si", f"{si_stem} city", si_stem))
    else:
        for s in stems:
            out.extend((s, f"{s}-gu", f"{s}-gun", f"{s}-si"))
    # dedupe preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for h in out:
        if h not in seen:
            seen.add(h)
            deduped.append(h)
    return tuple(deduped)


def build_hints_dict() -> dict[str, tuple[str, ...]]:
    all_names = _parse_addr_data()
    result: dict[str, tuple[str, ...]] = {}
    for name in all_names:
        if name in _OVERRIDES:
            result[name] = _OVERRIDES[name]
        elif name in _STEM:
            result[name] = _auto_hints(name, _STEM[name])
        elif name.endswith("구"):
            stem = name[:-1]  # fallback: not ideal
            result[name] = _auto_hints(name, (stem,))
        elif name.endswith("군"):
            result[name] = _auto_hints(name, (name[:-1],))
        elif name.endswith("시"):
            result[name] = _auto_hints(name, (name[:-1],))
        else:
            raise ValueError(f"No stem for {name!r}")
    return result


def format_dict(d: dict[str, tuple[str, ...]]) -> str:
    lines = ["_SIGUNGU_EN_HINTS: dict[str, tuple[str, ...]] = {"]
    for key in sorted(d.keys(), key=lambda k: (len(k), k)):
        hints = ", ".join(repr(h) for h in d[key])
        lines.append(f'    "{key}": ({hints}),')
    lines.append("}")
    return "\n".join(lines)


if __name__ == "__main__":
    hints = build_hints_dict()
    print(format_dict(hints))
    print(f"# total keys: {len(hints)}", file=__import__("sys").stderr)
