"""Itinerary repair helpers.

URL 복구, 슬롯 파싱, 식사 타이밍, plain place 감지, area focus 매칭.
router.py에서 추출한 함수 모음 — 동작은 완전히 동일하다.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.api.google_places_client import NearbyPlace

# ─── URL 복구 ─────────────────────────────────────────────────────────────────

_MAPS_URL_IN_TEXT_RE = re.compile(
    r"https?://(?:maps\.google\.com|www\.google\.com/maps|goo\.gl/maps|maps\.app\.goo\.gl|map\.naver\.com)/\S+",
    re.I,
)


def _norm_plan_place_name(text: str | None) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower().strip("「」『』\"'`"))


_JP_NAME_MAP_MARKER = "【日本語名マップ】"


def _extract_jp_name_map(plan_text: str) -> tuple[str, dict[str, str]]:
    """プラン末尾の【日本語名マップ】セクションを取り出して本文から除去する。

    Returns (cleaned_plan_text, {ko_name: jp_name}).
    """
    if _JP_NAME_MAP_MARKER not in plan_text:
        return plan_text, {}
    idx = plan_text.index(_JP_NAME_MAP_MARKER)
    clean_text = plan_text[:idx].rstrip()
    map_section = plan_text[idx + len(_JP_NAME_MAP_MARKER):]
    name_map: dict[str, str] = {}
    for line in map_section.splitlines():
        line = line.strip()
        if "→" in line:
            ko, sep, ja = line.partition("→")
            ko = ko.strip()
            ja = ja.strip()
            if ko and ja:
                name_map[ko] = ja
    return clean_text, name_map


def _apply_jp_names_to_places(
    places: "list[NearbyPlace]", name_map: "dict[str, str]"
) -> "list[NearbyPlace]":
    """name_mapを参照して各NearbyPlaceにname_jaを設定した新リストを返す。"""
    import dataclasses as _dc
    if not name_map:
        return places
    result: list = []
    for p in places:
        jp = name_map.get(p.name)
        if jp and not getattr(p, "name_ja", None):
            try:
                p = _dc.replace(p, name_ja=jp)
            except Exception:
                pass
        result.append(p)
    return result


def _repair_itinerary_place_urls(reply: str, places: "list[NearbyPlace]") -> str:
    """LLM이 장소명은 썼지만 maps URL을 누락한 경우, 검증된 후보 URL을 복구한다.

    프론트 지도/카드가 본문과 어긋나는 것을 막기 위한 최후 안전망이다.
    """
    if not reply or not places:
        return reply
    by_name: dict[str, Any] = {}
    for p in places:
        uri = p.google_maps_uri or ""
        key = _norm_plan_place_name(p.name)
        if uri and key and key not in by_name:
            by_name[key] = p
    if not by_name:
        return reply

    out: list[str] = []
    injected: set[str] = set()
    lines = reply.splitlines()
    for idx, line in enumerate(lines):
        out.append(line)
        stripped = line.strip()
        key = _norm_plan_place_name(stripped)
        place = by_name.get(key)
        if not place:
            continue
        lookahead = "\n".join(lines[idx + 1: idx + 4])
        if _MAPS_URL_IN_TEXT_RE.search(lookahead):
            continue
        url = place.google_maps_uri or ""
        if url and url not in injected:
            injected.add(url)
            out.append(url)
    return "\n".join(out)


# ─── 슬롯 파싱 ────────────────────────────────────────────────────────────────

_ITINERARY_SLOT_MARKERS = {
    "morning": ("午前", "오전", "朝", "아침"),
    "lunch": ("昼食", "ランチ", "점심"),
    "afternoon": ("午後", "오후"),
    "dinner": ("夕食", "ディナー", "저녁"),
    "night": ("夜", "밤"),
}
_ITINERARY_DAY_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\d+\s*日目|\d+\s*일째|Day\s*\d+|最終日)", re.I)
_ITINERARY_BAD_PLACEHOLDER_RE = re.compile(
    r"(?:周辺を散策|周辺散策|近くを歩く|쇼핑이나\s*산책|주변(?:을|에서)?\s*산책|일대\s*산책|"
    r"롯데월드타워\s*주변|宿泊先周辺のレストラン|カフェで軽食|カフェタイム|카페\s*타임|"
    r"(?:市内|시내|海岸沿い|해안가|自然|자연).{0,24}(?:過ご|楽し|撮影|보내|즐기|촬영)|"
    r"(?:지역|에리어|エリア|근처|주변|일대|近く|周辺).{0,12}(?:음식점|식당|맛집|한국음식|요리|レストラン|食堂|食事)|"
    r"(?:현지|当地|地元|한국\s*같은|韓国らしい).{0,12}(?:맛|요리|음식|グルメ|料理|食事)|"
    r"候補が(?:足りない|全部終わった)|"
    r"候補不足|時間外の可能性|現地で探す|店名は記載しない|コンビニ|軽食|間食)",
    re.I,
)

_CAFE_SLOT_ONLY_RE = re.compile(
    r"^\s*(?:\[?\s*(?:カフェ(?:タイム|巡り|休憩)?|카페\s*(?:타임|순회|휴식)?)\s*\]?|"
    r"(?:☕\s*)?(?:カフェ(?:タイム|休憩)?|카페\s*(?:타임|휴식)?))\s*$",
    re.I,
)
_EMPTY_COMBINED_SLOT_RE = re.compile(r"^\s*(?:夕食|저녁)\s*(?:夜|밤)\s*$")


def _queue_places_for_repair(
    places: "list[NearbyPlace]",
    predicate: Any,
) -> "list[NearbyPlace]":
    out: list = []
    seen: set[str] = set()
    for p in places or []:
        if not predicate(p):
            continue
        uri = p.google_maps_uri or ""
        if not uri:
            continue
        key = f"{_norm_plan_place_name(p.name)}|{_plan_maps_url_key(uri)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _plan_maps_url_key(url: str | None) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    cid = re.search(r"[?&]cid=(\d+)", text)
    if cid:
        return f"cid:{cid.group(1)}"
    if "map.naver.com" in text.lower():
        return text.split("?")[0].rstrip("/")
    return text.split("&g_mp=")[0].split("&")[0].rstrip("/")


def _itinerary_slot_from_line(line: str) -> str:
    text = str(line or "").strip().strip("#:-・* ")
    for slot, markers in _ITINERARY_SLOT_MARKERS.items():
        if any(text == marker or text.startswith(marker) for marker in markers):
            return slot
    return ""


def _itinerary_day_number(line: str, total_days: int | None = None) -> int | None:
    text = str(line or "").strip()
    if re.search(r"最終日", text) and total_days:
        return total_days
    m = re.search(r"(?:Day\s*)?(\d+)\s*(?:日目|일째|일차|日|day)?", text, re.I)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


# ─── 식사 타이밍 ─────────────────────────────────────────────────────────────


def _late_arrival_blocks_meals(profile: dict | None) -> bool:
    from src.chain.travel_context import _parse_hhmm  # lazy import (순환 참조 방지)
    inbound = ((profile or {}).get("flight") or {}).get("selected") or {}
    parsed = _parse_hhmm(inbound.get("arr_scheduled"))
    if not parsed:
        return False
    h, m = parsed
    total = h * 60 + m + 160  # immigration/baggage plus lodging transfer estimate
    est = total % (24 * 60)
    return est >= 22 * 60 + 30 or total >= 24 * 60


def _early_departure_blocks_meals(profile: dict | None) -> bool:
    from src.chain.travel_context import _parse_hhmm  # lazy import (순환 참조 방지)
    outbound = ((profile or {}).get("flight") or {}).get("selectedReturn") or {}
    parsed = _parse_hhmm(outbound.get("dep_scheduled"))
    if not parsed:
        return False
    h, m = parsed
    return h * 60 + m < 15 * 60


# ─── plain place 감지 ─────────────────────────────────────────────────────────


def _itinerary_line_foodish(line: str) -> bool:
    from src.chain.router import _FOODISH_NAME_MARKERS  # lazy import
    blob = str(line or "").lower()
    return any(marker in blob for marker in _FOODISH_NAME_MARKERS) or any(
        marker.lower() in blob for marker in (
            "restaurant", "cafe", "coffee", "dessert", "brunch", "bakery",
            "レストラン", "カフェ", "デザート", "食堂", "食事", "軽食",
        )
    )


def _looks_like_plain_itinerary_place_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 34:
        return False
    if _MAPS_URL_IN_TEXT_RE.search(text) or _itinerary_slot_from_line(text) or _ITINERARY_DAY_RE.match(text):
        return False
    if re.search(r"[。.!?！？]|です|ます|입니다|합니다|즐길|맛볼|확인|候補|スポット", text):
        return False
    return bool(re.search(r"[ㄱ-힝]", text))


# ─── area focus 매칭 ─────────────────────────────────────────────────────────

_BUSAN_DAY_AREA_ALIASES: dict[str, tuple[str, ...]] = {
    "해운대": ("해운대", "송정", "기장"),
    "송정": ("해운대", "송정", "기장"),
    "기장": ("기장", "송정", "해운대"),
    "광안리": ("광안리", "수영구", "해운대"),
    "수영": ("수영구", "광안리", "해운대"),
    "남포": ("남포", "중구", "영도", "부산역"),
    "영도": ("영도", "남포", "중구"),
}

_JPN_CITY_TO_KO: dict[str, str] = {
    # 광역시
    "釜山": "부산", "プサン": "부산",
    "大邱": "대구", "テグ": "대구",
    "仁川": "인천", "インチョン": "인천",
    "光州": "광주", "クァンジュ": "광주",
    "大田": "대전", "テジョン": "대전",
    "蔚山": "울산", "ウルサン": "울산",
    "世宗": "세종", "セジョン": "세종",
    # 경상북도
    "浦項": "포항", "ポハン": "포항",
    "慶州": "경주", "キョンジュ": "경주",
    "安東": "안동", "アンドン": "안동",
    "亀尾": "구미", "クミ": "구미",
    "聞慶": "문경", "ムンギョン": "문경",
    "尚州": "상주", "サンジュ": "상주",
    "栄州": "영주", "ヨンジュ": "영주",
    "永川": "영천", "ヨンチョン": "영천",
    "盈徳": "영덕", "ヨンドク": "영덕",
    "青松": "청송", "チョンソン경북": "청송",
    "蔚珍": "울진", "ウルジン": "울진",
    "鬱陵": "울릉", "ウルルン": "울릉",
    "奉化": "봉화", "ポンファ": "봉화",
    "義城": "의성", "ウィソン": "의성",
    "清道": "청도", "チョンド": "청도",
    "漆谷": "칠곡", "チルゴク": "칠곡",
    "醴泉": "예천", "イェチョン": "예천",
    "慶山": "경산", "キョンサン": "경산",
    "高霊": "고령", "コリョン": "고령",
    "星州": "성주", "ソンジュ": "성주",
    "金泉": "김천", "キムチョン": "김천",
    # 경상남도
    "統営": "통영", "トンヨン": "통영",
    "巨済": "거제", "コジェ": "거제",
    "昌原": "창원", "チャンウォン": "창원",
    "晋州": "진주", "チンジュ": "진주",
    "南海": "남해", "ナムヘ": "남해",
    "河東": "하동", "ハドン": "하동",
    "山清": "산청", "サンチョン": "산청",
    "咸陽": "함양", "ハミャン": "함양",
    "陜川": "합천", "ハプチョン": "합천",
    "密陽": "밀양", "ミリャン": "밀양",
    "梁山": "양산", "ヤンサン": "양산",
    "金海": "김해", "キムヘ": "김해",
    "泗川": "사천", "サチョン": "사천",
    "居昌": "거창", "コチャン경남": "거창",
    "昌寧": "창녕", "チャンニョン": "창녕",
    "咸安": "함안", "ハマン": "함안",
    "宜寧": "의령", "ウィリョン": "의령",
    # 전라북도
    "全州": "전주", "チョンジュ": "전주",
    "群山": "군산", "クンサン": "군산",
    "益山": "익산", "イクサン": "익산",
    "井邑": "정읍", "チョンウプ": "정읍",
    "南原": "남원", "ナムォン": "남원",
    "茂朱": "무주", "ムジュ": "무주",
    "扶安": "부안", "プアン": "부안",
    "高敞": "고창", "コチャン전북": "고창",
    "完州": "완주", "ワンジュ": "완주",
    "淳昌": "순창", "スンチャン": "순창",
    "任実": "임실", "イムシル": "임실",
    "長水": "장수", "チャンス": "장수",
    "鎭安": "진안", "チナン": "진안",
    "金堤": "김제", "キムジェ": "김제",
    # 전라남도
    "麗水": "여수", "ヨス": "여수",
    "順天": "순천", "スンチョン": "순천",
    "木浦": "목포", "モクポ": "목포",
    "潭陽": "담양", "タミャン": "담양",
    "康津": "강진", "カンジン": "강진",
    "高興": "고흥", "コフン": "고흥",
    "곡성": "곡성", "コクソン": "곡성",
    "光陽": "광양", "クァンヤン": "광양",
    "求礼": "구례", "クリェ": "구례",
    "羅州": "나주", "ナジュ": "나주",
    "宝城": "보성", "ポソン": "보성",
    "新安": "신안", "シンアン": "신안",
    "霊光": "영광", "ヨングァン": "영광",
    "霊巌": "영암", "ヨンアム": "영암",
    "莞島": "완도", "ワンド": "완도",
    "長城": "장성", "チャンソン": "장성",
    "長興": "장흥", "チャンフン": "장흥",
    "珍島": "진도", "チンド": "진도",
    "咸平": "함평", "ハンピョン": "함평",
    "海南": "해남", "ヘナム": "해남",
    "和順": "화순", "ファスン": "화순",
    # 충청북도
    "清州": "청주", "チョンジュ충북": "청주",
    "忠州": "충주", "チュンジュ": "충주",
    "堤川": "제천", "チェチョン": "제천",
    "丹陽": "단양", "タニャン": "단양",
    "報恩": "보은", "ポウン": "보은",
    "槐山": "괴산", "クェサン": "괴산",
    "永同": "영동", "ヨンドン충북": "영동",
    "沃川": "옥천", "オクチョン": "옥천",
    # 충청남도
    "公州": "공주", "コンジュ": "공주",
    "扶余": "부여", "プヨ": "부여",
    "瑞山": "서산", "ソサン": "서산",
    "泰安": "태안", "テアン": "태안",
    "牙山": "아산", "アサン": "아산",
    "保寧": "보령", "ポリョン": "보령",
    "論山": "논산", "ノンサン": "논산",
    "錦山": "금산", "クムサン": "금산",
    "唐津": "당진", "タンジン": "당진",
    "礼山": "예산", "イェサン": "예산",
    "洪城": "홍성", "ホンソン": "홍성",
    "青陽": "청양", "チョンヤン": "청양",
    "天安": "천안", "チョナン": "천안",
    # 강원도
    "江陵": "강릉", "カンヌン": "강릉",
    "束草": "속초", "ソクチョ": "속초",
    "春川": "춘천", "チュンチョン": "춘천",
    "原州": "원주", "ウォンジュ": "원주",
    "平昌": "평창", "ピョンチャン": "평창",
    "襄陽": "양양", "ヤンヤン": "양양",
    "東海": "동해", "トンヘ": "동해",
    "三陟": "삼척", "サムチョク": "삼척",
    "寧越": "영월", "ヨンウォル": "영월",
    "旌善": "정선", "チョンソン강원": "정선",
    "鉄原": "철원", "チョルォン": "철원",
    "洪川": "홍천", "ホンチョン": "홍천",
    "太白": "태백", "テベク": "태백",
    "華川": "화천", "ファチョン": "화천",
    "横城": "횡성", "フェンソン": "횡성",
    "麟蹄": "인제", "インジェ": "인제",
    # 경기도
    "水原": "수원", "スウォン": "수원",
    "龍仁": "용인", "ヨンイン": "용인",
    "坡州": "파주", "パジュ": "파주",
    "华城": "화성", "ファソン": "화성",
    "高陽": "고양", "コヤン": "고양",
    "城南": "성남", "ソンナム": "성남",
    "南楊州": "남양주", "ナミャンジュ": "남양주",
    "加平": "가평", "カピョン": "가평",
    "楊平": "양평", "ヤンピョン": "양평",
    "驪州": "여주", "ヨジュ": "여주",
    "抱川": "포천", "ポチョン": "포천",
    "漣川": "연천", "ヨンチョン경기": "연천",
    "富川": "부천", "プチョン": "부천",
    # 제주도
    "済州": "제주", "チェジュ": "제주",
    "西帰浦": "서귀포", "ソグィポ": "서귀포",
}


def _day_focus_area_tokens(line: str) -> tuple[str, ...]:
    from src.chain.router import _parse_region_city_tokens  # lazy import
    text = str(line or "")
    tokens: list[str] = []
    had_group = False
    for m in re.finditer(r"[（(【]([^）)】]+)[）)】]", text):
        had_group = True
        tokens.extend(_parse_region_city_tokens(m.group(1)))
    if not had_group:
        explicit = re.sub(r"^\s*(?:#{1,6}\s*)?(?:Day\s*)?\d+\s*(?:日目|일째|일차|日|day)?", "", text, flags=re.I)
        if explicit and explicit != text:
            for token in _parse_region_city_tokens(explicit):
                if token not in tokens:
                    tokens.append(token)

    out: list[str] = []
    for token in tokens:
        clean = re.sub(r"(?:지역|エリア|周辺|観光|食事|일정|코스)$", "", token).strip()
        for jpn, ko in _JPN_CITY_TO_KO.items():
            if jpn in clean:
                clean = ko
                break
        if not re.search(r"[ㄱ-힝]", clean):
            continue
        if not clean:
            continue
        expanded = _BUSAN_DAY_AREA_ALIASES.get(clean, (clean,))
        for item in expanded:
            if item and item not in out:
                out.append(item)
    return tuple(out[:5])


def _place_matches_day_focus(place: "NearbyPlace | None", day_focus: tuple[str, ...]) -> bool:
    if not place or not day_focus:
        return True
    blob = " ".join(
        str(x or "")
        for x in (place.address, place.name, getattr(place, "search_area", ""))
    )
    return any(token in blob for token in day_focus)


def _repair_wizard_itinerary_rules(
    reply: str,
    places: "list[NearbyPlace]",
    traveler_profile: dict | None,
    user_message: str,
) -> str:
    """Wizard itinerary safety net for meal/card consistency.

    The prompt is intentionally strict, but streamed model output can still leak
    restaurant cards into morning/afternoon/night slots. This pass removes those
    blocks before the UI renders the final itinerary.
    """
    # lazy imports — 순환 참조 방지
    from src.chain.router import (  # noqa: PLC0415
        _is_wizard_plan_request,
        _is_meal_candidate_place,
        _is_cafe_candidate_place,
        _foodish_signal,
        _has_cafe_hopping_interest,
        _is_civic_office_text,
        _CIVIC_OFFICE_URL_RE,
        _tourism_search_areas,
        _accommodation_food_areas,
        _needs_accommodation_buffer_candidates,
        _place_in_stay_zone,
        _accom_is_sudogwon,
        _place_in_seoul_zone,
        _place_in_goyang_zone,
        _place_in_incheon_zone,
    )

    if not reply or not _is_wizard_plan_request(traveler_profile, user_message):
        return reply

    food_by_url: set[str] = set()
    food_names: set[str] = set()
    food_place_by_url: dict[str, Any] = {}
    food_place_by_name: dict[str, Any] = {}
    attr_by_url: set[str] = set()
    attr_names: set[str] = set()
    attr_place_by_url: dict[str, Any] = {}
    attr_place_by_name: dict[str, Any] = {}
    cafe_by_url: set[str] = set()
    cafe_by_name: set[str] = set()
    cafe_place_by_url: dict[str, Any] = {}
    cafe_place_by_name: dict[str, Any] = {}
    food_queue = _queue_places_for_repair(
        places,
        lambda p: _is_meal_candidate_place(p)
        and not _is_cafe_candidate_place(p)
    )
    cafe_queue = _queue_places_for_repair(places, _is_cafe_candidate_place)
    attr_queue = _queue_places_for_repair(
        places,
        lambda p: not _is_cafe_candidate_place(p)
        and not _is_meal_candidate_place(p)
        and not _foodish_signal(p),
    )
    used_food: set[str] = set()
    used_cafe: set[str] = set()
    used_attr: set[str] = set()
    for p in places or []:
        uri = p.google_maps_uri or ""
        key = _plan_maps_url_key(uri)
        name_key = _norm_plan_place_name(p.name)
        if _is_cafe_candidate_place(p):
            if key:
                cafe_by_url.add(key)
                cafe_place_by_url[key] = p
            if name_key:
                cafe_by_name.add(name_key)
                cafe_place_by_name[name_key] = p
        is_food = _is_meal_candidate_place(p) and not _is_cafe_candidate_place(p)
        if is_food:
            if key:
                food_by_url.add(key)
                food_place_by_url[key] = p
            if name_key:
                food_names.add(name_key)
                food_place_by_name[name_key] = p
        is_attr = (
            not _is_cafe_candidate_place(p)
            and not _is_meal_candidate_place(p)
            and not _foodish_signal(p)
        )
        if is_attr:
            if key:
                attr_by_url.add(key)
                attr_place_by_url[key] = p
            if name_key:
                attr_names.add(name_key)
                attr_place_by_name[name_key] = p

    has_cafe_interest = _has_cafe_hopping_interest(traveler_profile, user_message)
    lines = reply.splitlines()
    out: list[str] = []
    slot = ""
    day_food_count = 0
    day_cafe_count = 0
    slot_plain_place_seen = False
    used_food_names_global: set[str] = set()  # cross-day dedup for restaurants
    day_attr_places: list = []
    last_kept_place_food = False
    current_day: int | None = None
    current_day_focus: tuple[str, ...] = ()
    try:
        total_days = int((traveler_profile or {}).get("days") or 0) or None
    except (TypeError, ValueError):
        total_days = None
    late_arrival_blocks_meals = _late_arrival_blocks_meals(traveler_profile)
    early_departure_blocks_meals = _early_departure_blocks_meals(traveler_profile)
    travel_areas = _tourism_search_areas(traveler_profile)
    stay_areas = _accommodation_food_areas(traveler_profile)
    penultimate_return_day = (
        total_days - 1
        if total_days
        and total_days > 2
        and _needs_accommodation_buffer_candidates(traveler_profile, travel_areas)
        else None
    )

    def meals_blocked_for_day(day_num: int | None) -> bool:
        if day_num == 1 and late_arrival_blocks_meals:
            return True
        if total_days and day_num == total_days and early_departure_blocks_meals:
            return True
        return False

    def wrong_penultimate_dinner_place(url_key: str, name_key: str) -> bool:
        if not penultimate_return_day or current_day != penultimate_return_day or slot != "dinner":
            return False
        place = food_place_by_url.get(url_key) or food_place_by_name.get(name_key)
        if not place:
            return False
        if _place_in_stay_zone(place, stay_areas):
            return False
        if not stay_areas and _accom_is_sudogwon(traveler_profile):
            return not (
                _place_in_seoul_zone(place)
                or _place_in_goyang_zone(place)
                or _place_in_incheon_zone(place)
            )
        return True

    def _attr_cluster_key(place: "Any | None") -> str:
        if not place:
            return ""
        key = _norm_plan_place_name(place.name)
        if not key:
            return ""
        for suffix in (
            "역사공원", "역사문화공원", "문화공원", "근린공원", "공원",
            "전시관", "기념관", "박물관", "체험관", "전망대", "광장",
        ):
            if key.endswith(suffix) and len(key) > len(suffix) + 2:
                key = key[: -len(suffix)]
                break
        return key

    def _place_distance_m(place_a: "Any | None", place_b: "Any | None") -> "float | None":
        try:
            lat1 = float(getattr(place_a, "latitude", None))
            lng1 = float(getattr(place_a, "longitude", None))
            lat2 = float(getattr(place_b, "latitude", None))
            lng2 = float(getattr(place_b, "longitude", None))
        except (TypeError, ValueError):
            return None
        # Good enough for duplicate suppression inside one city block/tourism zone.
        mean_lat = math.radians((lat1 + lat2) / 2)
        dlat = (lat1 - lat2) * 111_320
        dlng = (lng1 - lng2) * 111_320 * math.cos(mean_lat)
        return math.hypot(dlat, dlng)

    def _same_attr_visit_cluster(place_a: "Any | None", place_b: "Any | None") -> bool:
        if not place_a or not place_b:
            return False
        key_a = _attr_cluster_key(place_a)
        key_b = _attr_cluster_key(place_b)
        if not key_a or not key_b:
            return False
        name_related = (
            key_a == key_b
            or (len(key_a) >= 4 and key_a in key_b)
            or (len(key_b) >= 4 and key_b in key_a)
        )
        if not name_related:
            return False
        dist = _place_distance_m(place_a, place_b)
        return dist is None or dist <= 1_200

    def duplicate_day_attr_place(place: "Any | None") -> bool:
        if not place:
            return False
        return any(_same_attr_visit_cluster(prev, place) for prev in day_attr_places)

    def cafeish_line_or_place(line: str, place: "Any | None") -> bool:
        if place is not None and _is_cafe_candidate_place(place):
            return True
        blob = str(line or "").lower()
        return bool(re.search(r"카페|커피|coffee|cafe|디저트|베이커리|dessert|bakery|スイーツ|ベーカリー", blob, re.I))

    def next_place_line(kind: str) -> list[str]:
        queue = food_queue if kind == "food" else cafe_queue if kind == "cafe" else attr_queue
        used = used_food if kind == "food" else used_cafe if kind == "cafe" else used_attr
        for p in queue:
            pkey = f"{p.name}|{p.google_maps_uri}"
            if pkey in used:
                continue
            if kind == "attr" and duplicate_day_attr_place(p):
                continue
            if (
                p.name
                and p.google_maps_uri
                and _place_matches_day_focus(p, current_day_focus)
            ):
                used.add(pkey)
                if kind == "attr":
                    day_attr_places.append(p)
                return [p.name, p.google_maps_uri]
        return []

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if _ITINERARY_DAY_RE.match(stripped):
            slot = ""
            current_day = _itinerary_day_number(stripped, total_days)
            current_day_focus = _day_focus_area_tokens(stripped)
            day_food_count = 0
            day_cafe_count = 0
            day_attr_places = []
            slot_plain_place_seen = False
            last_kept_place_food = False
            out.append(line)
            idx += 1
            continue

        new_slot = _itinerary_slot_from_line(stripped)
        if new_slot:
            if new_slot in {"lunch", "dinner"} and meals_blocked_for_day(current_day):
                slot = "blocked_meal"
                idx += 1
                continue
            slot = new_slot
            slot_plain_place_seen = False
            out.append(line)
            if new_slot == "afternoon" and _has_cafe_hopping_interest(traveler_profile, user_message):
                lookahead = "\n".join(lines[idx + 1: idx + 5])
                if _CAFE_SLOT_ONLY_RE.search(lookahead) and not _MAPS_URL_IN_TEXT_RE.search(lookahead):
                    inserted = next_place_line("cafe")
                    if inserted:
                        out.extend(inserted)
            idx += 1
            continue

        if slot == "blocked_meal":
            idx += 1
            continue

        if _EMPTY_COMBINED_SLOT_RE.match(stripped):
            out.append("夕食")
            slot = "dinner"
            idx += 1
            continue

        if _CAFE_SLOT_ONLY_RE.match(stripped):
            if _has_cafe_hopping_interest(traveler_profile, user_message):
                out.append(line)
                inserted = next_place_line("cafe")
                if inserted:
                    out.extend(inserted)
            idx += 1
            continue

        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
        if stripped and not _itinerary_slot_from_line(stripped) and not _ITINERARY_DAY_RE.match(stripped):
            civic_block = _is_civic_office_text(stripped) or _is_civic_office_text(next_line)
            if civic_block:
                idx += 1
                if idx < len(lines) and (
                    _MAPS_URL_IN_TEXT_RE.search(lines[idx])
                    or _CIVIC_OFFICE_URL_RE.search(lines[idx])
                ):
                    idx += 1
                if idx < len(lines):
                    tail = lines[idx].strip()
                    if (
                        tail
                        and not _MAPS_URL_IN_TEXT_RE.search(tail)
                        and not _ITINERARY_DAY_RE.match(tail)
                        and not _itinerary_slot_from_line(tail)
                    ):
                        idx += 1
                continue

        if stripped and not _MAPS_URL_IN_TEXT_RE.search(stripped) and _ITINERARY_BAD_PLACEHOLDER_RE.search(stripped):
            idx += 1
            continue

        name_only_key = _norm_plan_place_name(stripped)
        if (
            stripped
            and not _MAPS_URL_IN_TEXT_RE.search(stripped)
            and not _MAPS_URL_IN_TEXT_RE.search(next_line)
            and name_only_key
        ):
            name_only_place = (
                food_place_by_name.get(name_only_key)
                or cafe_place_by_name.get(name_only_key)
                or attr_place_by_name.get(name_only_key)
            )
            name_only_is_cafe = name_only_key in cafe_by_name
            name_only_is_food = not name_only_is_cafe and name_only_key in food_names
            name_only_is_attr = name_only_key in attr_names
            name_only_wrong_area = (
                current_day_focus
                and name_only_place is not None
                and not _place_matches_day_focus(name_only_place, current_day_focus)
            )
            name_only_remove = (
                (name_only_is_food and (slot not in {"lunch", "dinner"} or name_only_wrong_area))
                or (name_only_is_cafe and (not has_cafe_interest or slot != "afternoon" or day_cafe_count >= 1 or name_only_wrong_area))
                or (name_only_is_attr and (slot in {"lunch", "dinner"} or name_only_wrong_area))
                or (name_only_is_attr and slot in {"morning", "afternoon", "night"} and slot_plain_place_seen)
            )
            if name_only_remove:
                replacement = []
                if name_only_is_attr and slot in {"lunch", "dinner"} and day_food_count < 2:
                    replacement = next_place_line("food")
                idx += 1
                if idx < len(lines):
                    tail = lines[idx].strip()
                    if (
                        tail
                        and not _MAPS_URL_IN_TEXT_RE.search(tail)
                        and not _ITINERARY_DAY_RE.match(tail)
                        and not _itinerary_slot_from_line(tail)
                    ):
                        idx += 1
                if replacement:
                    out.extend(replacement)
                    day_food_count += 1
                    last_kept_place_food = True
                continue

        url_match = _MAPS_URL_IN_TEXT_RE.search(next_line)
        if stripped and url_match and not _MAPS_URL_IN_TEXT_RE.search(stripped):
            url_key = _plan_maps_url_key(url_match.group(0))
            name_key = _norm_plan_place_name(stripped)
            # A place is a "cafe block" if its URL/name matches a known cafe candidate.
            is_cafe_block = (
                url_key in cafe_by_url
                or name_key in cafe_by_name
            )
            is_food_block = (
                not is_cafe_block
                and (url_key in food_by_url or name_key in food_names or _itinerary_line_foodish(stripped))
            )
            place_for_block = (
                food_place_by_name.get(name_key)
                or cafe_place_by_name.get(name_key)
                or attr_place_by_name.get(name_key)
                or food_place_by_url.get(url_key)
                or cafe_place_by_url.get(url_key)
                or attr_place_by_url.get(url_key)
            )
            is_attr_block = (
                not is_food_block
                and not is_cafe_block
                and (url_key in attr_by_url or name_key in attr_names)
            )
            wrong_day_area = (
                current_day_focus
                and place_for_block is not None
                and not _place_matches_day_focus(place_for_block, current_day_focus)
            )
            cafe_without_interest = (
                not has_cafe_interest
                and (is_cafe_block or cafeish_line_or_place(stripped, place_for_block))
            )
            nonmeal_in_meal_slot = slot in {"lunch", "dinner"} and (is_attr_block or is_cafe_block)
            duplicate_attr = (
                is_attr_block
                and slot in {"morning", "afternoon", "night"}
                and duplicate_day_attr_place(place_for_block)
            )
            # Cross-day restaurant dedup: remove if this exact restaurant already appeared.
            is_duplicate_food = is_food_block and name_key and name_key in used_food_names_global
            remove_food = is_duplicate_food or (
                is_food_block
                and (
                    slot not in {"lunch", "dinner"}
                    or day_food_count >= 2
                    or last_kept_place_food
                    or wrong_penultimate_dinner_place(url_key, name_key)
                    or wrong_day_area
                )
            )
            # Cafe blocks: keep only 1 per day in afternoon; always remove if not afternoon slot.
            remove_cafe = is_cafe_block and (
                not has_cafe_interest or slot != "afternoon" or day_cafe_count >= 1 or wrong_day_area
            )
            remove_food = remove_food or cafe_without_interest
            remove_attr = is_attr_block and (
                nonmeal_in_meal_slot
                or wrong_day_area
                or duplicate_attr
                or (slot in {"morning", "afternoon", "night"} and slot_plain_place_seen)
            )
            if remove_food or remove_cafe or remove_attr:
                replacement = []
                if nonmeal_in_meal_slot and day_food_count < 2:
                    replacement = next_place_line("food")
                elif cafe_without_interest and slot in {"lunch", "dinner"} and day_food_count < 2:
                    replacement = next_place_line("food")
                elif remove_attr and slot in {"morning", "afternoon", "night"} and not slot_plain_place_seen:
                    replacement = next_place_line("attr")
                idx += 2
                if idx < len(lines):
                    tail = lines[idx].strip()
                    if (
                        tail
                        and not _MAPS_URL_IN_TEXT_RE.search(tail)
                        and not _ITINERARY_DAY_RE.match(tail)
                        and not _itinerary_slot_from_line(tail)
                    ):
                        idx += 1
                if replacement:
                    out.extend(replacement)
                    day_food_count += 1
                    last_kept_place_food = True
                continue
            out.append(line)
            out.append(next_line)
            if is_food_block:
                day_food_count += 1
                last_kept_place_food = True
                if name_key:
                    used_food_names_global.add(name_key)
            elif is_cafe_block:
                day_cafe_count += 1
                last_kept_place_food = False
            elif stripped:
                last_kept_place_food = False
                if slot in {"morning", "afternoon", "night"}:
                    slot_plain_place_seen = True
                    if is_attr_block and place_for_block is not None:
                        day_attr_places.append(place_for_block)
            idx += 2
            continue

        out.append(line)
        if _looks_like_plain_itinerary_place_line(stripped):
            slot_plain_place_seen = True
        if stripped and not _MAPS_URL_IN_TEXT_RE.search(stripped):
            last_kept_place_food = False
        idx += 1

    return "\n".join(out)
