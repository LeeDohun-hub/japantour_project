"""Live data context formatters: VisitKorea, KTO DataLab, festivals, vacation.

router.py에서 추출한 함수 모음 — 동작은 완전히 동일하다.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api.visitkorea_client import TourApiItem, KtoDataLabItem

from src.api.visitkorea_client import TourApiItem, KtoDataLabItem


def _fmt_visitkorea_stays(items: list[TourApiItem]) -> str:
    if not items:
        return "(Visit Korea 宿泊データなし)"

    def _stay_type_label(it: TourApiItem) -> str:
        cid = it.content_id or ""
        title_lower = (it.title or "").lower()
        if cid.startswith("gocamping-") or any(k in title_lower for k in ("캠핑", "글램핑", "카라반", "camping", "glamping")):
            return "[캠핑장]"
        if any(k in title_lower for k in ("풀빌라", "pool villa", "poolvilla", "프라이빗풀")):
            return "[풀빌라]"
        if any(k in title_lower for k in ("해수욕장", "해변", "비치", "beach")):
            return "[해수욕장]"
        if any(k in title_lower for k in ("펜션", "pension")):
            return "[펜션]"
        return ""

    lines = []
    for i, it in enumerate(items[:14], 1):
        tag = _stay_type_label(it)
        line = f"[{i}] {tag}{it.title}" if tag else f"[{i}] {it.title}"
        if it.addr1:
            line += f" | {it.addr1}"
        if it.tel:
            line += f" | TEL: {it.tel}"
        uri = it.maps_uri()
        if uri:
            line += f"\n    地図: {uri}"
        lines.append(line)
    return "\n".join(lines)


def _extract_ko_name_from_jp_title(title: str) -> str | None:
    """JpnService2 일본어 제목 '海雲台光祭り（해운대 빛 축제）' → 한국어명 추출."""
    import re
    m = re.search(r"[（(]([가-힣][가-힣\s·]{0,40})[)）]", str(title or ""))
    return m.group(1).strip() if m else None


def _fmt_visitkorea_festivals(items: list[TourApiItem]) -> str:
    if not items:
        return "(Visit Korea イベントデータなし)"
    try:
        from src.api.naver_maps_client import naver_map_search_url as _nmsurl
    except ImportError:
        _nmsurl = None
    lines = []
    n = 0
    for it in items[:24]:
        if not it.title:
            continue
        n += 1
        if n > 12:
            break
        period = it.event_period_display()
        line = f"[{n}] {it.title}"
        if period:
            line += f" | {period}"
        if it.addr1:
            line += f" | {it.addr1}"
        # 좌표가 있으면 name+coord URL → placeIndex byUrl 키와 일치
        if it.mapx and it.mapy and _nmsurl:
            try:
                lat, lng = float(it.mapy), float(it.mapx)
                ko_name = _extract_ko_name_from_jp_title(it.title)
                search_name = ko_name or it.title
                map_uri = _nmsurl(search_name, lat, lng)
            except ValueError:
                map_uri = f"https://map.naver.com/p/search/{urllib.parse.quote(it.title)}"
        else:
            map_uri = f"https://map.naver.com/p/search/{urllib.parse.quote(it.title)}"
        line += f"\n    地図: {map_uri}"
        lines.append(line)
    if not lines:
        return "(Visit Korea イベントデータなし)"
    return "\n".join(lines)


def _fmt_visitkorea_attractions(items: list[TourApiItem]) -> str:
    if not items:
        return "(Visit Korea 観光スポットデータなし)"
    import re as _re
    _KO_PAREN = _re.compile(r"[（(]([^）)]+)[）)]")
    lines = []
    for i, it in enumerate(items[:20], 1):
        title = it.title or ""
        # 괄호 안 한국어 이름을 앞에 표시해 LLM이 일본어 음독 대신 한국어 이름을 사용하도록
        m = _KO_PAREN.search(title)
        display_name = m.group(1).strip() if m else title
        line = f"[{i}] {display_name}"
        if m and display_name != title:
            line += f" ({title})"
        if it.addr1:
            line += f" | {it.addr1}"
        if it.tel:
            line += f" | TEL: {it.tel}"
        uri = it.maps_uri()
        if uri:
            line += f"\n    地図: {uri}"
        lines.append(line)
    return "\n".join(lines)


# ─── 결과 데이터클래스 ─────────────────────────────────────────────────
_KTO_LANDMARK_SUFFIXES = (
    "언덕", "고개", "마을", "거리", "골목", "계단", "폭포", "호수", "계곡",
    "봉", "령", "재", "협곡", "절벽", "암석", "암", "석",
)

def _kto_naver_search_name(name: str) -> str:
    """KTO 지명을 Naver Places에서 검색 가능한 이름으로 변환.

    KTO DataLab는 '동산청라언덕'처럼 네이버에 없는 복합 지명을 반환하는 경우가 있다.
    1) 국립/도립 공원 접미사 제거 (prefix 필수): '팔공산국립공원' → '팔공산'
       '남산공원'·'동대문역사문화공원'처럼 prefix 없는 공원은 건드리지 않음.
    2) 2글자 동네 접두어 제거: '동산청라언덕' → '청라언덕'
       잘린 후 부분이 실제 지형 접미어(언덕·고개·마을 등)로 끝나야 적용.
    """
    # 1) 국립/도립/군립/시립/자연/생태 공원 접미사 제거
    #    prefix를 필수로 만들어 '남산공원' 같은 일반 공원은 보존
    stripped = re.sub(
        r"\s*(?:국립|도립|군립|시립|자연|생태|광역시립)\s*공원$", "", name
    ).strip()
    if stripped and stripped != name and len(stripped) >= 2:
        return stripped

    # 2) 2글자 접두어 제거 — 공백 없는 6자 이상 순한글, 잘린 후가 지형 접미어로 끝날 때만
    if (
        len(name) >= 6
        and " " not in name
        and re.fullmatch(r"[가-힣]+", name)
    ):
        candidate = name[2:]
        if len(candidate) >= 3 and any(candidate.endswith(s) for s in _KTO_LANDMARK_SUFFIXES):
            return candidate

    return name


def _fmt_kto_datalab_items(title: str, items: list[KtoDataLabItem], limit: int = 12) -> str:
    if not items:
        return ""
    lines = [f"[{title}]"]
    for i, it in enumerate(items[:limit], 1):
        label = it.name or it.related_name
        if not label:
            continue
        line = f"{i}. {label}"
        # Naver에서 검색 불가한 복합 지명은 실제 검색어를 병기해 LLM이 올바른 URL 생성하도록 안내
        naver_name = _kto_naver_search_name(label)
        if naver_name != label:
            line += f" (네이버 검색어: {naver_name})"
        if it.related_name and it.related_name != label:
            line += f" -> {it.related_name}"
        if it.area:
            line += f" | area: {it.area}"
        if it.address:
            line += f" | address: {it.address}"
        if it.category:
            line += f" | category: {it.category}"
        if it.rank:
            line += f" | rank: {it.rank}"
        if it.score:
            line += f" | score: {it.score}"
        lines.append(line)
    return "\n".join(lines) if len(lines) > 1 else ""


def _fmt_kto_datalab_context(
    hubs: list[KtoDataLabItem],
    related: list[KtoDataLabItem],
    demand: list[KtoDataLabItem],
    extra_sections: dict[str, list[KtoDataLabItem]] | None = None,
) -> str:
    blocks = [
        _fmt_kto_datalab_items("KTO local hub tourism candidates", hubs),
        _fmt_kto_datalab_items("KTO related tourism candidates", related),
        _fmt_kto_datalab_items("KTO regional demand/resource hints", demand, limit=8),
    ]
    for title, items in (extra_sections or {}).items():
        blocks.append(_fmt_kto_datalab_items(title, items, limit=8))
    body = "\n".join(b for b in blocks if b)
    if not body:
        return ""
    return (
        "=== KTO Tourism DataLab / Data.go.kr enrichment ===\n"
        "Use this only to choose stronger tourist areas and candidate anchors. "
        "Prefer sections that match traveler preferences: accessibility, nature/healing, SNS/photo, culture, family/parents. "
        "When writing the user-facing plan, do not mention internal datasets or API availability.\n"
        + body
    )


def _kto_preference_flags(traveler_profile: dict | None, user_message: str = "") -> dict[str, bool]:
    profile = traveler_profile or {}
    add = profile.get("additional") or {}
    styles = {str(x).lower() for x in add.get("travelStyles") or []}
    activities = {str(x).lower() for x in profile.get("activities") or []}
    companion = str(add.get("companion") or "").lower()
    mobility = str(add.get("mobility") or "").lower()
    blob = " ".join(
        sorted(styles | activities)
        + [
            companion,
            mobility,
            str(add.get("note") or ""),
            user_message,
        ]
    ).lower()
    return {
        "accessibility": (
            mobility in {"stairs", "wheelchair", "stroller"}
            or companion in {"family", "parents"}
            or any(k in blob for k in ("wheelchair", "stroller", "階段", "車椅子", "ベビーカー", "高齢"))
        ),
        "green": bool({"nature", "healing"} & styles)
        or any(k in blob for k in ("自然", "힐링", "癒し", "eco", "green")),
        "photo": bool({"sns_hot", "local_vibe"} & styles)
        or any(k in blob for k in ("sns", "写真", "フォト", "인스타", "photo")),
        "culture": "culture" in styles or any(k in blob for k in ("歴史", "文化", "예술", "history", "museum")),
        "must_see": "must_see" in styles,
    }


def _kto_numeric_score(item: KtoDataLabItem) -> float:
    raw = (item.score or item.rank or "").replace(",", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    if item.rank:
        return max(0.0, 100.0 - value)
    return value


def _kto_candidate_queries(
    *,
    hubs: list[KtoDataLabItem],
    related: list[KtoDataLabItem],
    extra_sections: dict[str, list[KtoDataLabItem]] | None = None,
    travel_areas: list[str] | None = None,
    limit: int = 10,
) -> list[str]:
    weighted: list[tuple[float, str]] = []

    def add_items(items: list[KtoDataLabItem], base_score: float) -> None:
        for item in items:
            name = (item.name or item.related_name or "").strip()
            if not name:
                continue
            area_bonus = 0.0
            if travel_areas and item.area:
                if any(area in item.area or item.area in area for area in travel_areas):
                    area_bonus = 20.0
            query = name
            if item.area and item.area not in query:
                query = f"{name} {item.area}"
            elif travel_areas and not any(area in query for area in travel_areas):
                query = f"{name} {travel_areas[0]}"
            weighted.append((base_score + area_bonus + _kto_numeric_score(item) / 10.0, query))

    add_items(hubs, 100.0)
    add_items(related, 90.0)
    for title, items in (extra_sections or {}).items():
        base = 80.0
        lower = title.lower()
        if "accessible" in lower or "eco" in lower or "photo" in lower:
            base = 95.0
        elif "korean tourism" in lower:
            base = 88.0
        add_items(items, base)

    out: list[str] = []
    seen: set[str] = set()
    # chunk 변형 포함 시 limit을 초과할 수 있으므로 내부에서는 limit*2 까지 수집
    for _, query in sorted(weighted, key=lambda x: x[0], reverse=True):
        cleaned = " ".join(query.split()).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)

        # 복합 지명 변형 쿼리 삽입: "동산청라언덕 대구" → "청라언덕 대구" 도 바로 뒤에 추가
        # 이 변형이 Naver에서 검색되어 placeIndex에 등록되면 LLM plan anchor가 살아남는다
        tokens = cleaned.split()
        place_token = tokens[0]
        region_tokens = tokens[1:]
        naver_name = _kto_naver_search_name(place_token)
        if naver_name != place_token:
            variant = " ".join([naver_name] + region_tokens).strip()
            if variant not in seen:
                seen.add(variant)
                out.append(variant)

        if len(out) >= limit * 2:
            break
    return out[:limit]


def _vk_attraction_to_naver_queries(
    items: "list[TourApiItem]",
    area_codes: list[str] | None = None,
    *,
    limit: int = 15,
) -> list[str]:
    """VisitKorea 관광지 제목(JpnService2 일본어)에서 한국어 이름을 추출해 Naver 쿼리 생성.

    JpnService2 제목 형식: "168階段（168계단）" → "168계단"
    addr1으로 지역 접미어 추가: "プサン広域市..." → "부산"
    """
    import re

    _ADDR_TO_REGION: list[tuple[str, str]] = [
        # 구·군 단위 (도시보다 먼저 — 더 정확한 Naver 검색)
        ("ヘウンデ区", "해운대"),      # 부산 해운대구
        ("スヨン区", "수영"),           # 부산 수영구
        ("プサンジン区", "부산진"),      # 부산 부산진구(서면)
        ("サハ区", "사하"),             # 부산 사하구(감천문화마을)
        ("ドンネ区", "동래"),           # 부산 동래구
        ("キジャン郡", "기장"),          # 부산 기장군
        ("ジョンノ区", "종로"),          # 서울 종로구
        ("マポ区", "마포"),             # 서울 마포구
        ("ヨンサン区", "용산"),          # 서울 용산구
        ("カンナム区", "강남"),          # 서울 강남구
        ("ソンパ区", "송파"),            # 서울 송파구
        ("チョンノ区", "종로"),          # 서울 종로구(표기 변형)
        ("ジュン区", "중구"),            # 서울/부산 중구
        ("チェジュ市", "제주시"),         # 제주시 (도시 앞)
        # 광역시 (먼저 — 광역도보다 구체적이므로)
        ("ソウル", "서울"),
        ("プサン", "부산"), ("釜山", "부산"),
        ("インチョン", "인천"), ("仁川", "인천"),
        ("テグ", "대구"), ("大邱", "대구"),
        ("テジョン", "대전"), ("大田", "대전"),
        ("クァンジュ市", "광주"), ("クァンジュ広域市", "광주"), ("光州", "광주"),
        ("ウルサン", "울산"), ("蔚山", "울산"),
        ("セジョン", "세종"), ("世宗", "세종"),
        # 경상북도 도시 (도 이름보다 먼저)
        ("ポハン", "포항"), ("浦項", "포항"),
        ("キョンジュ", "경주"), ("慶州", "경주"),
        ("アンドン", "안동"), ("安東", "안동"),
        ("クミ", "구미"), ("亀尾", "구미"),
        ("ムンギョン", "문경"), ("聞慶", "문경"),
        ("サンジュ", "상주"), ("尚州", "상주"),
        ("ヨンジュ", "영주"), ("栄州", "영주"),
        ("ヨンチョン경북", "영천"), ("永川", "영천"),
        ("ヨンドク", "영덕"), ("盈徳", "영덕"),
        ("ウルジン", "울진"), ("蔚珍", "울진"),
        ("ウルルン", "울릉"), ("鬱陵", "울릉"),
        ("キョンサン市", "경산"), ("慶山", "경산"),
        ("コリョン", "고령"), ("高霊", "고령"),
        ("ポンファ", "봉화"), ("奉化", "봉화"),
        ("チルゴク", "칠곡"), ("漆谷", "칠곡"),
        ("慶尚北", "경북"), ("キョンサンブク", "경북"),
        # 경상남도 도시
        ("トンヨン", "통영"), ("統営", "통영"),
        ("コジェ", "거제"), ("巨済", "거제"),
        ("チャンウォン", "창원"), ("昌原", "창원"),
        ("チンジュ", "진주"), ("晋州", "진주"),
        ("ナムヘ", "남해"), ("南海", "남해"),
        ("ハドン", "하동"), ("河東", "하동"),
        ("サンチョン경남", "산청"), ("山清", "산청"),
        ("ハミャン", "함양"), ("咸陽", "함양"),
        ("ハプチョン", "합천"), ("陜川", "합천"),
        ("ミリャン", "밀양"), ("密陽", "밀양"),
        ("ヤンサン", "양산"), ("梁山", "양산"),
        ("キムヘ", "김해"), ("金海", "김해"),
        ("サチョン", "사천"), ("泗川", "사천"),
        ("チャンニョン", "창녕"), ("昌寧", "창녕"),
        ("ハマン", "함안"), ("咸安", "함안"),
        ("慶尚南", "경남"), ("キョンサンナム", "경남"),
        # 전라북도 도시
        ("チョンジュ", "전주"), ("全州", "전주"),
        ("クンサン", "군산"), ("群山", "군산"),
        ("イクサン", "익산"), ("益山", "익산"),
        ("ナムォン", "남원"), ("南原", "남원"),
        ("ムジュ", "무주"), ("茂朱", "무주"),
        ("プアン", "부안"), ("扶安", "부안"),
        ("全羅北", "전북"), ("チョルラブク", "전북"), ("チョンブク", "전북"),
        # 전라남도 도시
        ("ヨス", "여수"), ("麗水", "여수"),
        ("スンチョン", "순천"), ("順天", "순천"),
        ("モクポ", "목포"), ("木浦", "목포"),
        ("タミャン", "담양"), ("潭陽", "담양"),
        ("クァンヤン", "광양"), ("光陽", "광양"),
        ("クリェ", "구례"), ("求礼", "구례"),
        ("カンジン", "강진"), ("康津", "강진"),
        ("ヘナム", "해남"), ("海南", "해남"),
        ("ワンド", "완도"), ("莞島", "완도"),
        ("チンド", "진도"), ("珍島", "진도"),
        ("ポソン", "보성"), ("宝城", "보성"),
        ("全羅南", "전남"), ("チョルラナム", "전남"),
        # 충청북도 도시
        ("チェチョン", "제천"), ("堤川", "제천"),
        ("タニャン", "단양"), ("丹陽", "단양"),
        ("チュンジュ", "충주"), ("忠州", "충주"),
        ("チョンジュ충북", "청주"), ("清州", "청주"),
        ("忠清北", "충북"), ("チュンチョンブク", "충북"),
        # 충청남도 도시
        ("コンジュ", "공주"), ("公州", "공주"),
        ("プヨ", "부여"), ("扶余", "부여"),
        ("ソサン", "서산"), ("瑞山", "서산"),
        ("テアン", "태안"), ("泰安", "태안"),
        ("アサン", "아산"), ("牙山", "아산"),
        ("ポリョン", "보령"), ("保寧", "보령"),
        ("チョナン", "천안"), ("天安", "천안"),
        ("忠清南", "충남"), ("チュンチョンナム", "충남"),
        # 강원도 도시
        ("カンヌン", "강릉"), ("江陵", "강릉"),
        ("ソクチョ", "속초"), ("束草", "속초"),
        ("チュンチョン", "춘천"), ("春川", "춘천"),
        ("ウォンジュ", "원주"), ("原州", "원주"),
        ("ピョンチャン", "평창"), ("平昌", "평창"),
        ("ヤンヤン", "양양"), ("襄陽", "양양"),
        ("トンヘ", "동해"), ("東海", "동해"),
        ("サムチョク", "삼척"), ("三陟", "삼척"),
        ("カンウォン", "강원"), ("江原", "강원"),
        # 경기도 도시
        ("スウォン", "수원"), ("水原", "수원"),
        ("ヨンイン", "용인"), ("龍仁", "용인"),
        ("パジュ", "파주"), ("坡州", "파주"),
        ("カピョン", "가평"), ("加平", "가평"),
        ("ヤンピョン", "양평"), ("楊平", "양평"),
        ("ポチョン", "포천"), ("抱川", "포천"),
        ("京畿", "경기"), ("キョンギ", "경기"),
        # 제주도
        ("チェジュ市", "제주"), ("ソグィポ", "서귀포"), ("西帰浦", "서귀포"),
        ("済州", "제주"), ("チェジュ", "제주"),
    ]

    _KO_RE = re.compile(r"[（(]([^）)]+)[）)]")

    # 관광지(76) > 생태(78) > 기타 > 쇼핑(79) 순 정렬, 같은 타입 내에서는 원래 순서 유지
    _TYPE_PRIORITY = {"76": 0, "78": 1, "79": 3}
    ordered = sorted(
        items,
        key=lambda it: _TYPE_PRIORITY.get(it.content_type_id or "", 2),
    )

    out: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        title = item.title or ""
        # 괄호 안 한국어 추출 (예: "168階段（168계단）" → "168계단")
        m = _KO_RE.search(title)
        ko_name = m.group(1).strip() if m else ""
        # 한국어가 없으면 제목 전체 사용 (영문 명소 등)
        if not ko_name:
            ko_name = title.strip()
        if not ko_name:
            continue
        # addr1에서 지역 추출해 접미어로
        addr = item.addr1 or ""
        region_suffix = ""
        for jpn_keyword, ko_region in _ADDR_TO_REGION:
            if jpn_keyword in addr:
                region_suffix = ko_region
                break
        query = f"{ko_name} {region_suffix}".strip() if region_suffix else ko_name
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(query)
        if len(out) >= limit:
            break
    return out


# _haversine_m → itinerary_quality.py로 이동, re-export는 line ~5551에 있음


_VK_DRAMA_SET_RE = re.compile(r"드라마\s*세트|촬영지|로케이션|세트장|오픈\s*세트", re.I)


def _clean_vk_ko_name(raw: str) -> str:
    """VK 한국어 장소명에서 [유네스코 세계유산] 등 주석과 인물명 괄호를 제거.

    e.g. "서울 헌릉(태종, 전경왕후)과 인릉(순조, 순원왕후)[유네스코 세계유산(문화유산)]"
      → "서울 헌릉과 인릉"
    """
    # 대괄호·겹낫표 주석 제거 (유네스코, 세계유산 등)
    cleaned = re.sub(r"\s*[\[【][^\]】]{1,200}[\]】]", "", raw).strip()
    # 쉼표 포함 인물명 괄호 제거 (태종, 전경왕후) — 쉼표 없는 괄호는 유지
    cleaned = re.sub(
        r"\s*[（(][가-힣\s,·]{2,40}[)）]",
        lambda m: "" if "," in m.group() else m.group(),
        cleaned,
    ).strip()
    return cleaned or raw


def _vk_attractions_to_naver_places(items: "list[TourApiItem]") -> list:
    """VK TourApiItem → NaverPlace 변환 (추가 API 호출 없음).

    JpnService2 일본어 제목 "景福宮（경복궁）" → 한국어명 "경복궁" 추출.
    mapx/mapy 좌표로 Naver Map URL 생성. 중복 제거는 caller(_dedup_vk_against_naver)가 담당.
    """
    import re
    try:
        from src.api.naver_search_client import NaverPlace
        from src.api.naver_maps_client import naver_map_search_url
    except ImportError:
        return []

    out: list = []
    for item in items:
        if not item.mapx or not item.mapy:
            continue
        try:
            lat = float(item.mapy)
            lng = float(item.mapx)
        except ValueError:
            continue
        raw_title = str(item.title or "").strip()
        ko_match = re.search(r"[（(]([가-힣][가-힣\s·]{0,40})[)）]", raw_title)
        ko_name = ko_match.group(1).strip() if ko_match else None
        name_ja = ""
        if ko_name:
            name_ja = re.sub(r"\s*[（(][가-힣][가-힣\s·]{0,40}[)）]\s*", "", raw_title).strip()
        name = ko_name or _clean_vk_ko_name(raw_title)
        if not name:
            continue
        # 드라마 촬영지·세트장은 관광명소 후보에서 제외 (LLM이 드라마 제목을 지명으로 오용 방지)
        if _VK_DRAMA_SET_RE.search(name):
            from src.chain.router import logger  # lazy import
            logger.debug("_vk_attractions_to_naver_places: skipped drama set item %r", name)
            continue
        if ko_name:
            maps_url = naver_map_search_url(ko_name, lat, lng)
        else:
            # 한국어명 추출 실패 → 좌표만으로 URL 생성 (일본어 검색어가 Naver에 넘어가는 것 방지)
            maps_url = item.maps_uri()
        area = str(item.addr1 or "")[:20]
        out.append(
            NaverPlace(
                name=name,
                category="tourist_attraction",
                address=str(item.addr1 or item.addr2 or ""),
                latitude=lat,
                longitude=lng,
                rating=None,
                user_rating_count=None,
                google_maps_uri=maps_url,
                is_open_now=None,
                distance_meters=None,
                place_id=f"vk:{item.content_id}",
                search_area=area,
                source="visitkorea",
                naver_score=None,
                name_ja=name_ja or None,
            )
        )
    from src.chain.router import logger  # lazy import
    logger.info("_vk_attractions_to_naver_places: converted %d VK items", len(out))
    return out


def _festival_items_to_places(items: "list[TourApiItem]") -> list:
    """축제 TourApiItem (mapx/mapy 있는 것만) → NaverPlace 변환.

    place_id = 'festival:{content_id}' 로 anchor/cafe-anchor 필터를 통과하며
    api_places에 포함되어 프론트엔드 placeIndex.byUrl/byName에 등록된다.
    """
    import re
    try:
        from src.api.naver_search_client import NaverPlace
        from src.api.naver_maps_client import naver_map_search_url
    except ImportError:
        return []

    out: list = []
    for item in items:
        if not item.mapx or not item.mapy:
            continue
        try:
            lat = float(item.mapy)
            lng = float(item.mapx)
        except ValueError:
            continue
        raw_title = str(item.title or "").strip()
        if not raw_title:
            continue
        ko_name = _extract_ko_name_from_jp_title(raw_title)
        name = ko_name or raw_title
        maps_url = naver_map_search_url(name, lat, lng)
        period = item.event_period_display()
        category_label = f"축제・행사{' | ' + period if period else ''}"
        out.append(
            NaverPlace(
                name=name,
                category=category_label,
                address=str(item.addr1 or item.addr2 or ""),
                latitude=lat,
                longitude=lng,
                rating=None,
                user_rating_count=None,
                google_maps_uri=maps_url,
                is_open_now=None,
                distance_meters=None,
                place_id=f"festival:{item.content_id}",
                search_area=str(item.addr1 or "")[:20],
                source="visitkorea",
                naver_score=None,
                name_ja=raw_title if ko_name else None,
            )
        )
    from src.chain.router import logger  # lazy import
    logger.info("_festival_items_to_places: converted %d festival items with coords", len(out))
    return out


def _dedup_vk_against_naver(
    vk_places: list,
    naver_places: list,
    *,
    coord_threshold_m: float = 250.0,
) -> list:
    """VK 장소 중 Naver 결과와 중복인 항목 제거.

    이름 정규화 매칭 또는 좌표 250m 이내면 중복 판단 → Naver 결과 우선 유지.
    """
    from src.chain.itinerary_repair import _norm_plan_place_name  # lazy import
    from src.chain.itinerary_quality import _haversine_m  # lazy import
    existing_names = {_norm_plan_place_name(p.name) for p in naver_places}
    existing_coords = [
        (p.latitude, p.longitude)
        for p in naver_places
        if p.latitude is not None and p.longitude is not None
    ]
    out: list = []
    for vk_p in vk_places:
        if _norm_plan_place_name(vk_p.name) in existing_names:
            continue
        if vk_p.latitude is not None and vk_p.longitude is not None:
            if any(
                _haversine_m(vk_p.latitude, vk_p.longitude, lat, lon) < coord_threshold_m
                for lat, lon in existing_coords
            ):
                continue
        out.append(vk_p)
    return out


# (province_area_code, city_ko) → sigungu_code for JpnService2 areaBasedList2
# probe_sigungu.py 탐침 결과로 확인된 전국 시군구 코드
_VK_CITY_SIGUNGU: dict[tuple[str, str], str] = {
    # 경기도 (31)
    ("31", "가평"): "1",
    ("31", "고양"): "2",
    ("31", "과천"): "3",
    ("31", "광명"): "4",
    ("31", "경기광주"): "5",
    ("31", "구리"): "6",
    ("31", "군포"): "7",
    ("31", "남양주"): "9",
    ("31", "동두천"): "10",
    ("31", "부천"): "11",
    ("31", "성남"): "12",
    ("31", "수원"): "13",
    ("31", "시흥"): "14",
    ("31", "안산"): "15",
    ("31", "안성"): "16",
    ("31", "안양"): "17",
    ("31", "양주"): "18",
    ("31", "양평"): "19",
    ("31", "여주"): "20",
    ("31", "연천"): "21",
    ("31", "오산"): "22",
    ("31", "용인"): "23",
    ("31", "의왕"): "24",
    ("31", "의정부"): "25",
    ("31", "이천"): "26",
    ("31", "파주"): "27",
    ("31", "평택"): "28",
    ("31", "포천"): "29",
    ("31", "하남"): "30",
    ("31", "화성"): "31",
    # 강원도 (32)
    ("32", "강릉"): "1",
    ("32", "고성"): "2",
    ("32", "동해"): "3",
    ("32", "삼척"): "4",
    ("32", "속초"): "5",
    ("32", "양구"): "6",
    ("32", "양양"): "7",
    ("32", "영월"): "8",
    ("32", "원주"): "9",
    ("32", "인제"): "10",
    ("32", "정선"): "11",
    ("32", "철원"): "12",
    ("32", "춘천"): "13",
    ("32", "태백"): "14",
    ("32", "평창"): "15",
    ("32", "홍천"): "16",
    ("32", "화천"): "17",
    ("32", "횡성"): "18",
    # 충청북도 (33)
    ("33", "괴산"): "1",
    ("33", "단양"): "2",
    ("33", "보은"): "3",
    ("33", "영동"): "4",
    ("33", "옥천"): "5",
    ("33", "음성"): "6",
    ("33", "제천"): "7",
    ("33", "진천"): "8",
    ("33", "청주"): "10",
    ("33", "충주"): "11",
    ("33", "증평"): "12",
    # 충청남도 (34)
    ("34", "공주"): "1",
    ("34", "금산"): "2",
    ("34", "논산"): "3",
    ("34", "당진"): "4",
    ("34", "보령"): "5",
    ("34", "부여"): "6",
    ("34", "서산"): "7",
    ("34", "서천"): "8",
    ("34", "아산"): "9",
    ("34", "예산"): "11",
    ("34", "천안"): "12",
    ("34", "청양"): "13",
    ("34", "태안"): "14",
    ("34", "홍성"): "15",
    # 경상북도 (35)
    ("35", "경산"): "1",
    ("35", "경주"): "2",
    ("35", "고령"): "3",
    ("35", "구미"): "4",
    ("35", "김천"): "6",
    ("35", "문경"): "7",
    ("35", "봉화"): "8",
    ("35", "상주"): "9",
    ("35", "성주"): "10",
    ("35", "안동"): "11",
    ("35", "영덕"): "12",
    ("35", "영양"): "13",
    ("35", "영주"): "14",
    ("35", "영천"): "15",
    ("35", "예천"): "16",
    ("35", "울릉"): "17",
    ("35", "울진"): "18",
    ("35", "의성"): "19",
    ("35", "청도"): "20",
    ("35", "청송"): "21",
    ("35", "칠곡"): "22",
    ("35", "포항"): "23",
    # 경상남도 (36)
    ("36", "거제"): "1",
    ("36", "거창"): "2",
    ("36", "고성"): "3",
    ("36", "김해"): "4",
    ("36", "남해"): "5",
    ("36", "밀양"): "7",
    ("36", "사천"): "8",
    ("36", "산청"): "9",
    ("36", "양산"): "10",
    ("36", "의령"): "12",
    ("36", "진주"): "13",
    ("36", "창녕"): "15",
    ("36", "창원"): "16",
    ("36", "통영"): "17",
    ("36", "하동"): "18",
    ("36", "함안"): "19",
    ("36", "함양"): "20",
    ("36", "합천"): "21",
    # 전라북도 (37)
    ("37", "고창"): "1",
    ("37", "군산"): "2",
    ("37", "김제"): "3",
    ("37", "남원"): "4",
    ("37", "무주"): "5",
    ("37", "부안"): "6",
    ("37", "순창"): "7",
    ("37", "완주"): "8",
    ("37", "익산"): "9",
    ("37", "임실"): "10",
    ("37", "장수"): "11",
    ("37", "전주"): "12",
    ("37", "정읍"): "13",
    ("37", "진안"): "14",
    # 전라남도 (38)
    ("38", "강진"): "1",
    ("38", "고흥"): "2",
    ("38", "곡성"): "3",
    ("38", "광양"): "4",
    ("38", "구례"): "5",
    ("38", "나주"): "6",
    ("38", "담양"): "7",
    ("38", "목포"): "8",
    ("38", "무안"): "9",
    ("38", "보성"): "10",
    ("38", "순천"): "11",
    ("38", "신안"): "12",
    ("38", "여수"): "13",
    ("38", "영광"): "16",
    ("38", "영암"): "17",
    ("38", "완도"): "18",
    ("38", "장성"): "19",
    ("38", "장흥"): "20",
    ("38", "진도"): "21",
    ("38", "함평"): "22",
    ("38", "해남"): "23",
    ("38", "화순"): "24",
    # 제주도 (39)
    ("39", "서귀포"): "3",
    ("39", "제주"): "4",
}


def _get_city_sigungu(area_code: str, text: str) -> str:
    """area_code 내에서 text에 등장하는 도시의 sigungu_code 반환. 없으면 ''."""
    for (ac, city), sgu in _VK_CITY_SIGUNGU.items():
        if ac == area_code and city in text:
            return sgu
    return ""

