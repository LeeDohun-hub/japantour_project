"""Itinerary quality scoring and vacation section fallback.

router.py에서 추출한 함수 모음 — 동작은 완전히 동일하다.
"""

from __future__ import annotations

import math
import re
from typing import Any

# itinerary_repair에서 공통 심볼 import
from src.chain.itinerary_repair import (
    _ITINERARY_DAY_RE,
    _ITINERARY_BAD_PLACEHOLDER_RE,
    _MAPS_URL_IN_TEXT_RE,
    _norm_plan_place_name,
    _plan_maps_url_key,
    _itinerary_slot_from_line,
    _itinerary_day_number,
    _late_arrival_blocks_meals,
    _early_departure_blocks_meals,
)

_ACTIVITY_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "gourmet": {
        "label": "gourmet",
        "aliases": ("food", "gourmet", "\u30b0\u30eb\u30e1", "\ubbf8\uc2dd", "\uad6c\ub8e8\uba54", "\ub9db\uc9d1"),
        "markers": (r"\u663c\u98df", r"\u5915\u98df", r"\u30b0\u30eb\u30e1", r"\ub9db\uc9d1", r"\u98df\u4e8b"),
    },
    "shopping": {
        "label": "shopping",
        "aliases": ("shopping", "shop_hard", "\u30b7\u30e7\u30c3\u30d4\u30f3\u30b0", "\u8cb7\u3044\u7269", "\uc1fc\ud551"),
        "markers": (r"\u30b7\u30e7\u30c3\u30d4\u30f3\u30b0", r"\u8cb7\u3044\u7269", r"\u5e02\u5834", r"\u5546\u5e97\u8857", r"\uc1fc\ud551", r"\uc2dc\uc7a5", r"\ubc31\ud654\uc810", r"\ubab0"),
    },
    "nightview": {
        "label": "nightview",
        "aliases": ("nightview", "night_view", "night", "\u591c\u666f", "\uc57c\uacbd"),
        "markers": (r"\u591c\u666f", r"\u30e9\u30a4\u30c8\u30a2\u30c3\u30d7", r"\u5c55\u671b", r"\uc57c\uacbd", r"\uc804\ub9dd"),
    },
    "tradition": {
        "label": "tradition",
        "aliases": ("tradition", "traditional", "culture", "\u4f1d\u7d71\u6587\u5316", "\uc804\ud1b5\ubb38\ud654"),
        "markers": (r"\u4f1d\u7d71", r"\u97d3\u5c4b", r"\u5bae", r"\u6587\u5316", r"\u535a\u7269\u9928", r"\uc804\ud1b5", r"\ud55c\uc625", r"\ubb38\ud654", r"\ubc15\ubb3c\uad00"),
    },
    "festival": {
        "label": "festival",
        "aliases": ("festival", "fest", "\u796d\u308a", "\u796d", "\ucd95\uc81c", "\ud398\uc2a4\ud2f0\ubc8c"),
        "markers": (r"\u796d\u308a", r"\u30d5\u30a7\u30b9", r"\u30a4\u30d9\u30f3\u30c8", r"\ucd95\uc81c", r"\ud398\uc2a4\ud2f0\ubc8c", r"\ud589\uc0ac"),
    },
    "performance": {
        "label": "performance",
        "aliases": ("performance", "performances", "drama", "theater", "musical", "\u516c\u6f14", "\uacf5\uc5f0"),
        "markers": (r"\u516c\u6f14", r"\u30df\u30e5\u30fc\u30b8\u30ab\u30eb", r"\u5287\u5834", r"\u30e9\u30a4\u30d6", r"\ucf58\uc11c\ud2b8", r"\uacf5\uc5f0", r"\ubba4\uc9c0\uceec"),
    },
    "kpop": {
        "label": "K-pop",
        "aliases": ("kpop", "hallyu", "k-pop", "K-pop", "\ucf00\uc774\ud31d"),
        "markers": (r"K-?pop", r"\u30a2\u30a4\u30c9\u30eb", r"\u30b3\u30f3\u30b5\u30fc\u30c8", r"\ucf00\uc774\ud31d", r"\uc544\uc774\ub3cc", r"\ucf58\uc11c\ud2b8"),
    },
    "cafe": {
        "label": "cafe",
        "aliases": ("cafe", "coffee", "\u30ab\u30d5\u30a7", "\u30ab\u30d5\u30a7\u5de1\u308a", "\uce74\ud398", "\ucee4\ud53c"),
        "markers": (r"\u30ab\u30d5\u30a7", r"\u30b3\u30fc\u30d2\u30fc", r"\uce74\ud398", r"\ucee4\ud53c"),
    },
    "nature": {
        "label": "nature",
        "aliases": ("nature", "healing", "eco", "outdoor", "\u81ea\u7136", "\uc790\uc5f0", "\ud790\ub9c1"),
        "markers": (r"\u81ea\u7136", r"\u516c\u5712", r"\u6d77\u5cb8", r"\u68ee\u6797", r"\u30d3\u30fc\u30c1", r"\uc790\uc5f0", r"\uacf5\uc6d0", r"\ud574\ubcc0"),
    },
    "photo": {
        "label": "photo",
        "aliases": ("photo", "photos", "photo_spot", "\u30d5\u30a9\u30c8", "\u30d5\u30a9\u30c8\u30b9\u30dd\u30c3\u30c8", "\uc0ac\uc9c4", "\ud3ec\ud1a0"),
        "markers": (r"\u30d5\u30a9\u30c8", r"\u5199\u771f", r"SNS", r"\u64ae\u5f71", r"\ud3ec\ud1a0", r"\uc0ac\uc9c4"),
    },
    "sports": {
        "label": "sports",
        "aliases": ("sports", "sport", "baseball", "soccer", "\u30b9\u30dd\u30fc\u30c4", "\u30b9\u30dd\u30fc\u30c4\u89b3\u6226", "\uc2a4\ud3ec\uce20"),
        "markers": (r"\u30b9\u30dd\u30fc\u30c4", r"\u89b3\u6226", r"\u8a66\u5408", r"\u30b9\u30bf\u30b8\u30a2\u30e0", r"\uc57c\uad6c", r"\ucd95\uad6c", r"\uacbd\uae30"),
    },
    "vacation": {
        "label": "vacation",
        "aliases": ("vacation", "resort", "poolvilla", "pension", "camping", "beach", "\u30d0\u30ab\u30f3\u30b9", "\ud734\uc591"),
        "markers": (r"\u30d0\u30ab\u30f3\u30b9", r"\u30d7\u30fc\u30eb", r"\u30da\u30f3\u30b7\u30e7\u30f3", r"\u30ad\u30e3\u30f3\u30d7", r"\u6d77\u6c34\u6d74", r"\u30d3\u30fc\u30c1", r"\ud574\uc218\uc695", r"\ud574\ubcc0", r"\ud480\ube4c\ub77c", r"\ud39c\uc158", r"\ucea0\ud551"),
    },
}


def _selected_activity_requirements(traveler_profile: dict | None) -> list[tuple[str, str, tuple[str, ...]]]:
    profile = traveler_profile or {}
    additional = profile.get("additional") or {}
    raw_tokens: list[str] = []
    raw_tokens.extend(str(a) for a in profile.get("activities") or [])
    raw_tokens.extend(str(v) for v in profile.get("vacationTypes") or [])
    raw_tokens.extend(str(v) for v in profile.get("hallyu") or [])
    raw_tokens.extend(str(v) for v in additional.get("travelStyles") or [])
    blob = " ".join(raw_tokens).lower()
    out: list[tuple[str, str, tuple[str, ...]]] = []
    for key, cfg in _ACTIVITY_REQUIREMENTS.items():
        aliases = tuple(str(a).lower() for a in cfg["aliases"])
        if any(alias and alias.lower() in blob for alias in aliases):
            out.append((key, str(cfg["label"]), tuple(cfg["markers"])))
    return out


def _missing_selected_activity_labels(plan_text: str, traveler_profile: dict | None) -> list[str]:
    effective_text = "\n".join(
        line
        for line in (plan_text or "").splitlines()
        if not re.search(r"\u5019\u88dc\u306a\u3057|\u8a72\u5f53\u306a\u3057|no\s+candidates?|no\s+events?", line, re.I)
    )
    missing: list[str] = []
    for _key, label, markers in _selected_activity_requirements(traveler_profile):
        if not any(re.search(marker, effective_text, re.I) for marker in markers):
            missing.append(label)
    return missing


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 WGS-84 좌표 간 거리(미터) 근사."""
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _append_vacation_section_fallback(plan_text: str, stays: list) -> str:
    """バカンス候補セクションがLLM出力に含まれていない場合、stays データで補完する。"""
    import re as _re
    if _re.search(r'##\s*バカンス宿泊候補', plan_text):
        return plan_text  # 이미 있음
    if not stays:
        return plan_text  # 데이터 없음 → 그대로
    lines = ["\n\n## バカンス宿泊候補"]
    cat_map: dict[str, list[str]] = {}
    for s in stays[:20]:
        if hasattr(s, "get"):
            title = (s.get("title") or "").strip()
            cat = (s.get("cat3") or s.get("cat2") or "풀빌라").strip()
            addr = (s.get("addr1") or "").strip()
        else:
            title = (getattr(s, "title", "") or "").strip()
            cat = (getattr(s, "cat3", "") or getattr(s, "cat2", "") or "풀빌라").strip()
            addr = (getattr(s, "addr1", "") or "").strip()
        if not title:
            continue
        cat_map.setdefault(cat, [])
        entry = f"{title}" + (f" | {addr}" if addr else "")
        cat_map[cat].append(entry)
    for cat, items in cat_map.items():
        lines.append(f"\n**{cat}**")
        for i, item in enumerate(items[:5], 1):
            lines.append(f"{i}. {item}")
    return plan_text + "\n".join(lines)


def _score_wizard_plan_quality(
    plan_text: str,
    places: list,
    traveler_profile: dict | None,
) -> tuple[int, list[str]]:
    """wizard 플랜 품질을 0-100으로 채점. 실패 사유 리스트도 반환.

    검사 항목 (가중치 비율):
    1. [60%] 각 관광 가능일(입출국일 제외)의 昼食/夕食 슬롯 존재 여부
    2. [60%] 식사 슬롯 안에 Naver 지도 URL 또는 food candidate 명칭 유무
    3. [60%] 식사 슬롯에 attr 명소가 쓰였으면 실격 처리
    4. [60%] 입국 당일 저녁, 출국 당일 점심/저녁은 면제 (현실적으로 어려움)
    5. [25%] 관광 Day마다 지도 URL(map.naver.com / maps.google.com) 최소 1개 존재
    6. [10%] 후보군이 있는데 식사 슬롯에 URL·food명 모두 없으면 실격 (item 2와 별도)
    7. [5%]  plan Day 수가 traveler_profile.days와 일치하는가
    8. [bonus] 일자 헤더에 ★·지역명 등 추가 텍스트가 있으면 실격 패널티
    9. [bonus] 관광 슬롯에 식사 후보 URL이 삽입되면 실격 (카드 불일치)
    10. [bonus] 플랜 URL 좌표가 후보군 중심점에서 40km 초과이면 실격 (day당 3점 차감, 최대 15점)
    11. 5단계 관광에서 やりたいこと에서 다음을 선택하면 출력을 필수화 할것
      쇼핑->대형 쇼핑몰백화점 출력,
      야경->야경명소 출력(야경을 프로젝트 상에서 구분하지 못하면 기능 삭제),
      전통문화, 축제, 공연, K-pop, 스포츠관전, 풀빌라, 캠핑, 해수욕장, 자연, 포토스팟
      // 미식가 선택은 음식점 출력 필수화로 이미 반영됨(미식가 선택하면 진짜 엄선한거, 네이버 평점 좋은거)
      // 카페 순회 선택은 카페 출력 필수화로 이미 반영됨(카페 순회 선택하면 진짜 엄선한거, 네이버 평점 좋은거)
    """
    from src.chain.router import (  # lazy import — 순환 참조 방지
        _is_meal_candidate_place,
        _is_cafe_candidate_place,
    )

    if not plan_text:
        return 0, ["plan_empty"]

    # food / attr 이름·URL 집합 빌드
    food_names: set[str] = set()
    attr_names: set[str] = set()
    food_url_keys: set[str] = set()
    # 규칙 10: 좌표 기반 목적지 중심점 계산용
    _dest_lats: list[float] = []
    _dest_lngs: list[float] = []
    _url_key_to_coords: dict[str, tuple[float, float]] = {}
    for p in (places or []):
        key = _norm_plan_place_name(p.name)
        url_key = _plan_maps_url_key(p.google_maps_uri) if p.google_maps_uri else ""
        if _is_meal_candidate_place(p) and not _is_cafe_candidate_place(p):
            if key:
                food_names.add(key)
            if url_key:
                food_url_keys.add(url_key)
        elif not _is_meal_candidate_place(p) and not _is_cafe_candidate_place(p):
            if key:
                attr_names.add(key)
        lat = getattr(p, "latitude", None)
        lng = getattr(p, "longitude", None)
        if lat is not None and lng is not None:
            try:
                _dest_lats.append(float(lat))
                _dest_lngs.append(float(lng))
                if url_key:
                    _url_key_to_coords[url_key] = (float(lat), float(lng))
            except (TypeError, ValueError):
                pass
    _dest_lat = sum(_dest_lats) / len(_dest_lats) if _dest_lats else None
    _dest_lng = sum(_dest_lngs) / len(_dest_lngs) if _dest_lngs else None

    try:
        total_days = int((traveler_profile or {}).get("days") or 0) or None
    except (TypeError, ValueError):
        total_days = None

    late_arrival   = _late_arrival_blocks_meals(traveler_profile)
    early_depart   = _early_departure_blocks_meals(traveler_profile)

    def _meals_blocked(day_num: int | None) -> bool:
        # Day 1 (arrival) and last day (departure) are anchor days — always empty by design
        if day_num == 1:
            return True
        if total_days and day_num == total_days:
            return True
        return False

    # 라인별 파싱 — day·slot·URL 추적
    current_day: int | None = None
    current_slot = ""
    slot_has_url = False
    slot_name_keys: list[str] = []
    # {day_num: {"lunch": ok_bool, "dinner": ok_bool}}
    day_slots: dict[int, dict[str, bool]] = {}
    seen_days: set[int] = set()
    # 각 Day에 지도 URL이 1개 이상 있는지 (식사 슬롯 포함 전체)
    day_has_any_url: dict[int, bool] = {}
    # 중복 관광지 감지용: mapsUrlKey → 처음 등장한 day
    seen_attr_url_keys: dict[str, int] = {}
    duplicate_attr_days: set[int] = set()
    # 규칙 8: 일자 헤더 형식 위반 (★·지역명 등 추가 텍스트)
    bad_header_days: set[int] = set()
    # 규칙 9: 관광 슬롯에 식사 후보 URL 삽입 (카드 불일치)
    food_url_in_attr_days: set[int] = set()
    # 규칙 10: 관광목적지(후보군 중심점)에서 너무 먼 장소
    _FAR_THRESHOLD_M = 25_000   # 25km 초과 시 감점 (예: 서울→제주 460km)
    far_place_days: set[int] = set()
    # 규칙 11: "예) 장소명" 형식 placeholder — LLM이 실제 레스토랑 대신 예시 표기
    _YE_PLACEHOLDER_RE = re.compile(r'^예\)\s+\S|^例\)\s+\S', re.I)
    placeholder_days: set[int] = set()
    # 규칙 12: Naver URL에 일본어(히라가나/가타카나) 포함 — Naver 지도에서 검색 불가
    _JP_CHAR_RE = re.compile(r'[ぁ-んァ-ヶ]')
    japanese_url_days: set[int] = set()
    # 규칙 13: 구체 장소명 없이 "시내/해안/자연에서 시간을 보냄" 같은 일반 활동문
    generic_activity_days: set[int] = set()
    # 규칙 14: 식사 슬롯에 구체 식당명 없이 "지역 음식점/근처 음식점/현지 맛" 같은 일반문
    generic_meal_days: set[int] = set()

    def _flush() -> None:
        nonlocal slot_has_url, slot_name_keys
        if current_day is None or current_slot not in ("lunch", "dinner"):
            slot_has_url = False
            slot_name_keys = []
            return
        has_food = any(n in food_names for n in slot_name_keys)
        has_attr  = any(n in attr_names  for n in slot_name_keys)
        # food_names가 비어있으면 URL만으로도 ok (candidates 없는 경우 훈련지식 fallback 허용)
        # food_names가 있으면 URL 또는 명칭이 있어야 ok, attr-only면 실격
        ok = (slot_has_url or has_food) and not (has_attr and not has_food)
        day_slots.setdefault(current_day, {})[current_slot] = ok
        slot_has_url = False
        slot_name_keys = []

    _DAY_HEADER_EXTRA_RE = re.compile(
        r"^\s*(?:#{1,6}\s*)?\d+\s*(?:日目|일째|일차)\s*(\S.*)$", re.I
    )

    for line in plan_text.splitlines():
        s = line.strip()
        if _ITINERARY_DAY_RE.match(s):
            _flush()
            current_day = _itinerary_day_number(s, total_days)
            if current_day is not None:
                seen_days.add(current_day)
            current_slot = ""
            # 규칙 8: 헤더에 추가 텍스트가 있으면 bad_header 기록
            if current_day is not None and _DAY_HEADER_EXTRA_RE.match(s):
                bad_header_days.add(current_day)
            continue
        new_slot = _itinerary_slot_from_line(s)
        if new_slot:
            _flush()
            current_slot = new_slot
            continue
        # 현재 day에 지도 URL이 있으면 기록 (슬롯 무관)
        if current_day is not None and _MAPS_URL_IN_TEXT_RE.search(s):
            day_has_any_url[current_day] = True
            # 식사 슬롯 밖 지도 URL = 관광지 링크 → 중복 감지 + 규칙 9 체크
            if current_slot not in ("lunch", "dinner"):
                for m in _MAPS_URL_IN_TEXT_RE.finditer(s):
                    raw_url = m.group(0)
                    url_key = _plan_maps_url_key(raw_url)
                    # 규칙 9: 관광 슬롯에 식사 후보 URL → 카드 불일치
                    if food_url_keys and url_key in food_url_keys:
                        food_url_in_attr_days.add(current_day)
                    # 중복 관광지 감지
                    uk = raw_url.split("?")[0].rstrip("/").split("/")[-1][:40]
                    if uk in seen_attr_url_keys:
                        if seen_attr_url_keys[uk] != current_day:
                            duplicate_attr_days.add(current_day)
                    else:
                        seen_attr_url_keys[uk] = current_day
            # 규칙 10: URL의 좌표(?c=lng,lat)와 목적지 중심점 거리 체크
            if _dest_lat is not None:
                for m in _MAPS_URL_IN_TEXT_RE.finditer(s):
                    raw_url = m.group(0)
                    # ?c=lng,lat 패턴에서 좌표 추출
                    coord_m = re.search(r'\?c=(-?[\d.]+),(-?[\d.]+)', raw_url)
                    if coord_m:
                        try:
                            url_lng = float(coord_m.group(1))
                            url_lat = float(coord_m.group(2))
                            dist = _haversine_m(_dest_lat, _dest_lng, url_lat, url_lng)
                            if dist > _FAR_THRESHOLD_M:
                                far_place_days.add(current_day)
                        except (TypeError, ValueError):
                            pass
                    else:
                        # URL key로 places 리스트 좌표 매핑 체크
                        uk2 = _plan_maps_url_key(raw_url)
                        if uk2 in _url_key_to_coords:
                            clat, clng = _url_key_to_coords[uk2]
                            dist = _haversine_m(_dest_lat, _dest_lng, clat, clng)
                            if dist > _FAR_THRESHOLD_M:
                                far_place_days.add(current_day)
        if current_slot in ("lunch", "dinner") and current_day is not None:
            if _MAPS_URL_IN_TEXT_RE.search(s):
                slot_has_url = True
            nk = _norm_plan_place_name(s)
            if nk and 2 <= len(nk) <= 30:
                slot_name_keys.append(nk)
        # 규칙 11: "예) 장소명" placeholder 감지
        if current_day is not None and _YE_PLACEHOLDER_RE.match(s):
            placeholder_days.add(current_day)
        # 규칙 12: Naver URL에 일본어 문자 포함 감지
        if current_day is not None and _MAPS_URL_IN_TEXT_RE.search(s):
            for m in _MAPS_URL_IN_TEXT_RE.finditer(s):
                if _JP_CHAR_RE.search(m.group(0)):
                    japanese_url_days.add(current_day)
        if (
            current_day is not None
            and current_slot in ("morning", "afternoon", "night")
            and not _MAPS_URL_IN_TEXT_RE.search(s)
            and _ITINERARY_BAD_PLACEHOLDER_RE.search(s)
        ):
            generic_activity_days.add(current_day)
        if (
            current_day is not None
            and current_slot in ("lunch", "dinner")
            and not _MAPS_URL_IN_TEXT_RE.search(s)
            and _ITINERARY_BAD_PLACEHOLDER_RE.search(s)
        ):
            generic_meal_days.add(current_day)
    _flush()

    # ── 채점 ──────────────────────────────────────────────────────────────
    failures: list[str] = []
    # A: 식사 슬롯 (60% 가중치 — 슬롯 2개/day × 3배 가중)
    meal_expected = 0
    meal_ok = 0
    # B: 관광 URL 존재 (25% 가중치 — 슬롯 1개/day × 1.25배 가중)
    url_expected = 0
    url_ok = 0

    check_days = range(1, (total_days or 0) + 1) if total_days else sorted(day_slots)
    for day_num in check_days:
        meals_exc = _meals_blocked(day_num)

        # A: 식사 슬롯
        if not meals_exc:
            for slot_name in ("lunch", "dinner"):
                meal_expected += 1
                ok = day_slots.get(day_num, {}).get(slot_name)
                if ok is None:
                    # item 6: food 후보가 있는데 슬롯 자체가 없으면 더 엄격하게 처리
                    tag = f"day{day_num}_{slot_name}_missing"
                    if food_names:
                        tag += "(candidates_exist)"
                    failures.append(tag)
                elif not ok:
                    failures.append(f"day{day_num}_{slot_name}_invalid")
                else:
                    meal_ok += 1

        # B: 관광 URL 존재 (anchor day 제외)
        if not _meals_blocked(day_num):
            url_expected += 1
            if day_has_any_url.get(day_num, False):
                url_ok += 1
            else:
                failures.append(f"day{day_num}_no_map_url")

    # C: 중복 관광지 (감점 페널티 — 중복 day당 1점씩 차감)
    for dup_day in duplicate_attr_days:
        failures.append(f"day{dup_day}_duplicate_attr")

    # D: Day 수 일치 (item 7) — 도착일·최종일을 포함한 모든 헤더가 있어야 함
    day_count_ok = True
    if total_days:
        expected_days = set(range(1, total_days + 1))
        missing_days = sorted(expected_days - seen_days)
        unexpected_days = sorted(seen_days - expected_days)
        day_count_ok = not missing_days and not unexpected_days
        for missing_day in missing_days:
            failures.append(f"day{missing_day}_entirely_missing")
        for unexpected_day in unexpected_days:
            failures.append(f"day{unexpected_day}_unexpected")

    # E: 일자 헤더 형식 위반 (규칙 8 — 감점 페널티)
    for bad_day in bad_header_days:
        failures.append(f"day{bad_day}_bad_header_format")

    # F: 관광 슬롯에 식사 후보 URL 삽입 (규칙 9 — 감점 페널티)
    for mismatch_day in food_url_in_attr_days:
        failures.append(f"day{mismatch_day}_food_url_in_attr_slot")

    # G: 관광목적지와 너무 멀리 떨어진 장소 (규칙 10 — 감점 페널티)
    for far_day in far_place_days:
        failures.append(f"day{far_day}_far_from_destination")

    # H: "예) 장소명" placeholder (규칙 11 — 감점 페널티)
    for ph_day in placeholder_days:
        failures.append(f"day{ph_day}_placeholder_restaurant")

    # I: Naver URL에 일본어 (규칙 12 — 감점 페널티, 사실상 실격)
    for jp_day in japanese_url_days:
        failures.append(f"day{jp_day}_japanese_in_naver_url")

    # J: 구체 장소 없는 일반 활동문 (규칙 13 — 재시도 유도)
    for generic_day in generic_activity_days:
        failures.append(f"day{generic_day}_generic_activity_without_place")

    # K: 식사 슬롯 일반문 (규칙 14 — 재시도 유도)
    for generic_meal_day in generic_meal_days:
        failures.append(f"day{generic_meal_day}_generic_meal_without_restaurant")

    missing_activity_labels = _missing_selected_activity_labels(plan_text, traveler_profile)
    for label in missing_activity_labels:
        failures.append(f"selected_activity_missing:{label}")

    if meal_expected == 0 and url_expected == 0:
        if missing_activity_labels:
            return 0, failures
        return 100, []

    # 가중치: 식사(60%) + URL(25%) + Day수일치(10%) + 중복페널티(-5%)
    # 규칙 8 위반: 헤더 형식 위반 day당 2점 차감
    # 규칙 9 위반: 카드 불일치 day당 3점 차감
    # 규칙 10 위반: 목적지 25km 초과 장소 day당 10점 차감 (최대 35점) — 실질 실격
    # 규칙 11 위반: "예) 장소명" placeholder day당 8점 차감 (최대 24점) — 재시도 유도
    # 규칙 12 위반: Naver URL에 일본어 day당 12점 차감 (최대 36점) — 실질 실격
    # 규칙 13 위반: 구체 장소 없는 일반 활동문 day당 8점 차감 (최대 24점) — 재시도 유도
    # 규칙 14 위반: 식사 슬롯 일반문 day당 12점 차감 (최대 36점) — 강한 재시도 유도
    meal_score  = (meal_ok / meal_expected * 60)  if meal_expected  else 60.0
    url_score   = (url_ok  / url_expected  * 25)  if url_expected   else 25.0
    day_score   = 10.0 if day_count_ok else 0.0
    dup_penalty           = min(5.0,  len(duplicate_attr_days)    * 1.0)
    header_penalty        = min(10.0, len(bad_header_days)        * 2.0)
    card_mismatch_penalty = min(15.0, len(food_url_in_attr_days)  * 3.0)
    far_penalty           = min(35.0, len(far_place_days)         * 10.0)
    placeholder_penalty   = min(24.0, len(placeholder_days)       * 8.0)
    japanese_url_penalty  = min(36.0, len(japanese_url_days)      * 12.0)
    generic_penalty       = min(24.0, len(generic_activity_days)  * 8.0)
    generic_meal_penalty  = min(36.0, len(generic_meal_days)      * 12.0)
    activity_penalty      = min(40.0, len(missing_activity_labels) * 10.0)

    raw = meal_score + url_score + day_score - dup_penalty - header_penalty - card_mismatch_penalty - far_penalty - placeholder_penalty - japanese_url_penalty - generic_penalty - generic_meal_penalty - activity_penalty
    score = max(0, min(100, int(round(raw))))
    return score, failures
