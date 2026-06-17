"""Travel context formatting helpers.

Airport, flight, transport, traveler/budget context formatting.
router.py에서 추출한 함수 모음 — 동작은 완전히 동일하다.

airport_transport.py에 이미 있는 AREX/ICN-Seoul 관련 함수는 포함하지 않는다.
"""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.api.aviation_client import AirportBusInfo, AirportTaxiStatus

from src.api.aviation_client import resolve_iata


# ─── IATA 코드 geo 목록 ────────────────────────────────────────────────────────

_AIRPORT_GEO: dict[str, tuple[float, float, str]] = {
    "ICN": (37.4602, 126.4407, "仁川国際空港"),
    "CJU": (33.5113, 126.4930, "제주국제공항"),
    "PUS": (35.1796, 128.9382, "김해국제공항"),
    "GMP": (37.5583, 126.7906, "김포국제공항"),
}


# ─── 항공편 포매터 ─────────────────────────────────────────────────────────────

def _resolve_iata_flexible(code: str) -> str | None:
    """Try direct IATA code first, then alias lookup."""
    code = code.strip().upper()
    if len(code) == 3 and code.isalpha():
        return code
    return resolve_iata(code)


def _fmt_flights(flights: list) -> str:
    if not flights:
        return "(フライトデータなし)"
    lines = [
        "※ 韓国空港公社・仁川国際空港公社などの公開運航情報をもとにした参考スケジュール。遅延・欠航、空席、運賃、搭乗口変更はリアルタイム反映されない場合があります。",
        "※ 搭乗前に航空会社公式サイトで再確認。肉製品・加工肉・一部農水産物、検疫対象地域の訪問・経由がある場合は最新の検疫案内も確認してください。",
    ]
    for i, f in enumerate(flights[:5], 1):
        schedule_range = ""
        if getattr(f, "schedule_start", None) or getattr(f, "schedule_end", None):
            s = f.schedule_start or "?"
            e = f.schedule_end or "?"
            schedule_range = f"  運航期間: {s}〜{e}"
        days = getattr(f, "operating_days", "") or ""
        dep_t = f.dep_scheduled or "-"
        arr_t = f.arr_scheduled or "-"
        line = (
            f"[{i}] {f.airline_name} ({f.airline_iata}) {f.flight_iata}\n"
            f"    {f.dep_iata}({dep_t}) → {f.arr_iata}({arr_t})\n"
            f"    運航曜日: {days or '-'}{schedule_range}"
        )
        lines.append(line)
    return "\n".join(lines)


def _fmt_airport(airport: Any) -> str:
    if airport is None:
        return "(空港情報なし)"
    return (
        f"名称: {airport.name}\n"
        f"IATA: {airport.iata} / ICAO: {airport.icao or '-'}\n"
        f"国: {airport.country_name or '-'}\n"
        f"タイムゾーン: {airport.timezone or '-'}\n"
        f"位置: {airport.latitude}, {airport.longitude}"
    )


def _flight_leg_line(flight: dict, *, leg: str) -> str:
    """wizard flight dict → 1行サマリ (leg: arrival | departure)."""
    if not flight:
        return ""
    iata = flight.get("flight_iata") or ""
    airline = flight.get("airline_name") or ""
    if leg == "arrival":
        t = flight.get("arr_scheduled") or "?"
        ap = flight.get("arr_iata") or "ICN"
        term = flight.get("arr_terminal") or ""
        extra = f" {term}ターミナル" if term else ""
        return f"到着便 {iata} ({airline}) {ap}到着 {t}{extra}"
    t = flight.get("dep_scheduled") or "?"
    ap = flight.get("dep_iata") or "ICN"
    term = flight.get("dep_terminal") or ""
    gate = flight.get("dep_gate") or ""
    extra = ""
    if term:
        extra += f" {term}ターミナル"
    if gate:
        extra += f" ゲート{gate}"
    return f"出国便 {iata} ({airline}) {ap}出発 {t}{extra}"


def _normalize_airport_iata(code: str | None) -> str:
    c = (code or "").strip().upper()[:3]
    return c if c in _AIRPORT_GEO else "ICN"


def _jeju_only_profile(profile: dict | None) -> bool:
    if not profile:
        return False
    regions = [str(r).lower() for r in profile.get("regions") or []]
    return len(regions) == 1 and regions[0] == "jeju"


def arrival_airport_iata(profile: dict | None) -> str:
    if not profile:
        return "ICN"
    ap = profile.get("arrival_airport")
    if ap:
        return _normalize_airport_iata(str(ap))
    flight = profile.get("flight") or {}
    if not isinstance(flight, dict):
        flight = {}
    return _normalize_airport_iata(flight.get("to"))


def _fmt_airport_itinerary_transport(profile: dict | None) -> str:
    """到着空港に応じた移動・1日目ルール（LLM Reference）。"""
    ap = arrival_airport_iata(profile)
    if ap == "CJU":
        return (
            "【到着空港・交通ルール — 厳守】\n"
            "- 到着空港は済州国際空港（CJU）。仁川AREX・仁川リムジンは**使用禁止**。\n"
            "- 1日目: ① CJU到着・入国 ② 済州空港バス（リムジン）で宿泊エリアへ（約60〜90分） ③ チェックイン・休息\n"
            "- 深夜到着時は外食・観光ブロックなし。宿泊先でチェックイン・休息のみ。\n"
            "- 最終日: 宿泊先→CJU→出国便（便時刻はReference Dataの出国便）\n"
        )
    if ap == "PUS":
        return (
            "【到着空港・交通ルール — 厳守】\n"
            "- 到着空港は金海国際空港（PUS）。AREX・仁川リムジンは**使用禁止**。\n"
            "- 1日目: ① PUS到着・入国 ② 金海空港バスで宿泊方面 ③ チェックイン・休息\n"
            "- 参考: https://newbusan.net/airportbus/info_bus_stop.html\n"
        )
    if ap == "GMP":
        return (
            "【到着空港・交通ルール — 厳守】\n"
            "- 到着空港は金浦国際空港（GMP）。AREX・仁川リムジンは**使用禁止**。\n"
            "- 1日目: ① GMP到着・入国 ② 地下鉄または空港リムジンで宿泊方面 ③ チェックイン・休息\n"
            "- 参考: https://www.airportlimousine.co.kr/\n"
        )
    return (
        "【到着空港・交通ルール — 仁川（ICN）】\n"
        "- 1日目例: ① ICN到着・入国 ② AREX一般またはリムジン→宿泊エリア ③ チェックイン\n"
        "- 仁川以外のエリア観光は2日目以降。路線名・所要時間を明示（曖昧な「地下鉄利用」のみは禁止）\n"
    )


def _airport_terminal_codes_from_profile(profile: dict | None) -> list[str]:
    """wizard flight terminal → 인천공항 API 터미널 코드(P01/P03)."""
    if not profile:
        return ["P01", "P03"]
    flight = profile.get("flight") or {}
    terminals: list[str] = []
    for key in ("selected", "selectedReturn"):
        f = flight.get(key) or {}
        raw = " ".join(
            str(f.get(k) or "") for k in ("arr_terminal", "dep_terminal", "terminal")
        ).upper()
        if "2" in raw or "P03" in raw or "T2" in raw:
            terminals.append("P03")
        elif "1" in raw or "P01" in raw or "T1" in raw:
            terminals.append("P01")
    return list(dict.fromkeys(terminals)) or ["P01", "P03"]


def _airport_bus_area_codes(profile: dict | None) -> list[int]:
    """숙소/선택지역 → 인천공항 버스 API area 코드."""
    if not profile:
        return [1]
    from src.chain.router import _region_cities_text  # lazy import
    accom = profile.get("accommodation") or {}
    text = " ".join(
        str(x or "")
        for x in (
            accom.get("address"),
            accom.get("detail"),
            accom.get("name"),
            accom.get("region"),
            (accom.get("selectedPlace") or {}).get("address"),
            (accom.get("selectedHotel") or {}).get("address"),
            _region_cities_text(profile),
            " ".join(str(r) for r in profile.get("regions") or []),
        )
    ).lower()
    rules: list[tuple[int, tuple[str, ...]]] = [
        (3, ("인천", "incheon", "仁川", "송도", "부평", "연수")),
        (2, ("경기", "gyeonggi", "京畿", "고양", "일산", "수원", "광주시", "경기광주", "경기도 광주", "파주", "용인", "가평", "양평")),
        (4, ("강원", "gangwon", "江原", "속초", "강릉", "양양", "춘천", "평창")),
        (5, ("충청", "chungcheong", "忠清", "대전", "공주", "천안", "청주", "보령", "태안")),
        (6, ("경상", "gyeongsang", "慶尚", "부산", "대구", "경주", "거제", "통영", "안동", "포항")),
        (7, ("전라", "jeolla", "全羅", "광주", "전주", "여수", "목포", "순천", "군산")),
        (1, ("서울", "seoul", "ソウル", "명동", "홍대", "강남", "동대문")),
    ]
    codes = [code for code, kws in rules if any(k.lower() in text for k in kws)]
    return list(dict.fromkeys(codes)) or [1]


def _transport_prefers(profile: dict | None, key: str) -> bool:
    if not profile:
        return True
    transport = [str(t).lower() for t in profile.get("transport") or []]
    return not transport or key in transport


def _filter_airport_buses_for_profile(
    buses: "list[AirportBusInfo]",
    profile: dict | None,
) -> "list[AirportBusInfo]":
    from src.chain.router import _region_cities_text  # lazy import
    if not buses or not profile:
        return buses[:6]
    accom = profile.get("accommodation") or {}
    words = [
        str(accom.get("address") or ""),
        str(accom.get("detail") or ""),
        str(accom.get("region") or ""),
        _region_cities_text(profile),
    ]
    tokens = [
        t.strip().lower()
        for text in words
        for t in re.split(r"[\s,、/・|()（）-]+", text)
        if len(t.strip()) >= 2
    ]
    matched = [
        b for b in buses
        if any(tok in (b.routeinfo or "").lower() for tok in tokens)
    ]
    return (matched or buses)[:6]


def _fmt_airport_bus_infos(buses: "list[AirportBusInfo]") -> str:
    if not buses:
        return ""
    lines = [
        "=== 仁川空港 空港バス候補（公社API BusInformation/getBusInfo）===",
        "※ 到着日・最終日の空港アクセスで、該当路線がある場合はAREXより優先候補として検討。",
    ]
    for i, b in enumerate(buses[:6], 1):
        fare = f" / 大人運賃 {b.adultfare}ウォン" if b.adultfare else ""
        ride = []
        if b.t1ridelo:
            ride.append(f"T1乗り場 {b.t1ridelo}")
        if b.t2ridelo:
            ride.append(f"T2乗り場 {b.t2ridelo}")
        times = []
        if b.t1wdayt:
            times.append(f"T1平日 {b.t1wdayt}")
        if b.t2wdayt:
            times.append(f"T2平日 {b.t2wdayt}")
        lines.append(
            f"[{i}] {b.busnumber or '路線番号不明'} {b.busclass or ''}{fare}\n"
            f"    運行会社: {b.cpname or '-'}\n"
            f"    乗り場: {', '.join(ride) or '-'}\n"
            f"    主な経由地: {b.routeinfo or '-'}\n"
            f"    時刻表目安: {' / '.join(times) or '-'}"
        )
    return "\n".join(lines)


def _fmt_airport_taxi_status(statuses: "list[AirportTaxiStatus]") -> str:
    if not statuses:
        return ""
    labels = {"P01": "T1", "P03": "T2"}
    lines = [
        "=== 仁川空港 タクシー出車・待機情報（公社API StatusOfTaxi/getTaxiStatus）===",
        "※ タクシー利用時は到着ターミナルに合わせて乗り場・待機時間を反映。",
    ]
    for s in statuses[:4]:
        t = labels.get(s.terno, s.terno or "ターミナル不明")
        lines.append(
            f"[{t}] 更新 {s.updatetime or '-'}\n"
            f"    ソウル: {s.seoultaxicnt or '-'}台 / 待ち {s.seoulstandtime or '-'}分 / 乗り場 {s.seoultaxistand or '-'}\n"
            f"    仁川: {s.incheontaxicnt or '-'}台 / 待ち {s.incheonstandtime or '-'}分 / 乗り場 {s.incheontaxistand or '-'}\n"
            f"    京畿: {s.gyenggitaxicnt or '-'}台 / 待ち {s.gyenggistandtime or '-'}分 / 乗り場 {s.gyenggitaxistand or '-'}\n"
            f"    インターナショナル/大型: {s.intercitytaxicnt or '-'}台 / {s.vantaxicnt or '-'}台"
        )
    return "\n".join(lines)


def _fmt_icn_ground_transport_plan_rule(
    buses: "list[AirportBusInfo]",
    statuses: "list[AirportTaxiStatus]",
) -> str:
    if not buses and not statuses:
        return ""
    lines = [
        "=== 仁川空港アクセス 最終プラン反映ルール（厳守）===",
        "このブロックは内部参考で終わらせず、ユーザー向け最終プラン本文に必ず反映する。",
        "- 1日目の②（ICN→宿泊先）と最終日の②（宿泊先→ICN）に、利用候補を1行で書く。",
        "- 「公社API」「Reference Data」という語は本文に出さない。",
    ]
    if buses:
        lines.append(
            "- 空港バス候補がある場合: 路線番号、T1/T2乗り場、主な経由地、運賃目安を短く記載する。"
        )
    if statuses:
        lines.append(
            "- タクシー情報がある場合: 到着ターミナルに合う乗り場と待機時間目安を「タクシー利用時の目安」として短く記載する。"
        )
    lines.append(
        "- 例: ② 空港リムジン6000番台（T1/T2乗り場は候補参照）またはAREX一般で宿泊エリアへ。タクシー利用時は京畿方面乗り場・待機目安も確認。"
    )
    return "\n".join(lines)


def _fmt_traveler_flight_constraints(profile: dict | None) -> str:
    """위저드 확정 입국·귀국편 → 일정 LLM용 구조화 블록."""
    if not profile:
        return ""
    flight = profile.get("flight") or {}
    lines: list[str] = []

    if flight.get("depart"):
        lines.append(f"旅行開始日: {flight['depart']}")
    if flight.get("returnDate"):
        lines.append(f"帰国日（最終日）: {flight['returnDate']}")

    inbound = flight.get("selected")
    if inbound:
        lines.append(f"1日目: {_flight_leg_line(inbound, leg='arrival')}")
        lines.append("  → 入国審査・税関: 通常60〜90分を1日目ブロックに含める")

    outbound = flight.get("selectedReturn")
    if not outbound:
        return "\n".join(lines) if lines else ""

    lines.append(f"最終日: {_flight_leg_line(outbound, leg='departure')}")

    lines.append(
        "  → 国際線: 出発2〜3時間前に空港到着（チェックイン・保安・出国審査90〜120分＋移動時間）"
    )
    lines.append(
        "  → 最終日の観光・食事は出発時刻から逆算し、上記空港到着目安より前にすべて終了"
    )
    return "\n".join(lines)


def _parse_hhmm(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    s = str(raw).strip().replace(":", "")
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:2]) % 24, int(s[2:4]) % 60
    if len(s) == 3 and s.isdigit():
        return int(s[0]) % 24, int(s[1:3]) % 60
    return None


def _fmt_late_arrival_day1_hint(profile: dict | None) -> str:
    """入国+移動後に23時以降に宿泊先到着が見込まれる場合、1日目ルールをReferenceに明示."""
    if not profile:
        return ""
    inbound = (profile.get("flight") or {}).get("selected") or {}
    parsed = _parse_hhmm(inbound.get("arr_scheduled"))
    if not parsed:
        return ""
    h, m = parsed
    # 入国審査〜90分 + 宿泊先まで移動〜70分（目安）
    total = h * 60 + m + 90 + 70
    est_h, est_m = (total // 60) % 24, total % 60
    if est_h < 23 and not (est_h == 22 and est_m >= 30):
        return ""
    accom = profile.get("accommodation") or {}
    label = accom.get("name") or accom.get("address") or "宿泊先"
    if accom.get("type") == "friend":
        label = "友人宅"
    return (
        "=== 1日目 深夜到着フラグ（システム推定）===\n"
        f"到着便後、推定 {est_h:02d}:{est_m:02d} 頃に {label} 到着見込み。\n"
        "→ 1日目は「チェックイン・休息」の順序ブロックのみ（時刻レンジは書かない）。\n"
        "→ 【夕食】【観光】【夜景】等のブロックは追加しない。\n"
        "→ 夕食の代わりに1行: 深夜のため外食は控え、宿泊先で休息（店名創作禁止）。\n"
    )


# ─── 예산 helper ──────────────────────────────────────────────────────────────

def _fmt_budget_hint(traveler_profile: dict | None) -> str:
    """予算スタイル・重視費目 → LLM向け具体的行動指示を生成."""
    if not traveler_profile:
        return ""
    budget = traveler_profile.get("budget") or {}
    style = str(budget.get("style") or "").lower()
    priority = list(budget.get("priority") or [])

    if not style and not priority:
        return ""

    lines: list[str] = ["=== 予算スタイル指示（食事・移動・観光の選択基準）==="]

    if style == "budget":
        lines += [
            "【コスパ重視】食事候補の中から庶民的・地元向けの選択肢を優先する。",
            "- 食事: 백반집・분식집・포장마차系・定食系など1人前₩8,000〜15,000相当の日常食を優先。"
            " 高級韓定食・オマカセ・ホテル内レストランは候補にあっても後回しにする。",
            "- 観光: 無料または入場料が安いスポット（公園・市場・ストリート・無料展示）を積極的に選ぶ。",
            "- 移動: 地下鉄・バスを第一選択として明示。タクシーは終電後など必要な場面のみ。",
        ]
    elif style == "premium":
        lines += [
            "【プレミアム】食事候補の中から体験価値・雰囲気・品質が高い選択肢を優先する。",
            "- 食事: 韓定食・高級焼肉・創作韓国料理など、旅の記念になる食事処を積極的に選ぶ。",
            "- 観光: 体験型・少人数向けプログラム（伝統工芸・料理クラス等）も候補にあれば積極的に提案。",
            "- 移動: 必要に応じてタクシー・カカオT利用を自然に提案してよい。",
        ]
    elif style == "normal":
        lines.append(
            "【バランス】コスパと体験価値のバランスを取る。特別な理由なく高額店・低品質店に偏らない。"
        )

    pri_notes = {
        "transport": "交通費重視: 移動コストを抑えた経路（地下鉄・バス）を優先し、移動の選択肢を詳しく案内する。",
        "stay": "宿泊費重視: 宿泊候補がある場合はコスパや立地について一言コメントを添える。",
        "food": "食費重視: 食事候補の中でとくにコスパが高い、または食体験の価値が際立つ選択肢を優先する。",
    }
    for p in priority:
        if p in pri_notes:
            lines.append(f"【重視費目:{p}】{pri_notes[p]}")

    return "\n".join(lines) + "\n"
