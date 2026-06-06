"""Airport transport helpers used by chat routing."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from src.api.aviation_client import AirportRailroadOperation, IncheonAirportClient

logger = logging.getLogger(__name__)

_ICN_SEOUL_TRANSPORT_RE = re.compile(
    r"(인천공항|인천국제공항|仁川空港|仁川国際空港|ICN).*(서울|서울시|서울 시내|명동|明洞|myeongdong|ソウル)"
    r"|"
    r"(서울|서울시|서울 시내|명동|明洞|myeongdong|ソウル).*(인천공항|인천국제공항|仁川空港|仁川国際空港|ICN)",
    re.IGNORECASE,
)

_AREX_EXPRESS_T2_T1_SEOUL: list[tuple[str, str, str]] = [
    ("05:16", "05:24", "06:07"),
    ("06:00", "06:08", "06:51"),
    ("06:30", "06:38", "07:21"),
    ("07:05", "07:13", "07:56"),
    ("08:10", "08:18", "09:01"),
    ("08:58", "09:06", "09:49"),
    ("09:30", "09:38", "10:21"),
    ("10:10", "10:18", "11:01"),
    ("10:50", "10:58", "11:41"),
    ("11:30", "11:38", "12:21"),
    ("12:10", "12:18", "13:01"),
    ("12:45", "12:53", "13:36"),
    ("13:20", "13:28", "14:11"),
    ("14:00", "14:08", "14:51"),
    ("14:40", "14:48", "15:31"),
    ("15:20", "15:28", "16:11"),
    ("16:00", "16:08", "16:51"),
    ("16:40", "16:48", "17:31"),
    ("17:20", "17:28", "18:11"),
    ("18:10", "18:18", "19:01"),
    ("18:35", "18:43", "19:26"),
    ("19:15", "19:23", "20:06"),
    ("20:05", "20:13", "20:56"),
    ("20:55", "21:03", "21:46"),
    ("21:50", "21:58", "22:41"),
    ("22:40", "22:48", "23:31"),
]

_AREX_EXPRESS_FARE_KO = (
    "직통열차 운임: 어른 13,000원 / 회원 12,500원, 어린이 9,500원, "
    "경로·장애인·국가유공자 9,500원"
)
_AREX_EXPRESS_FARE_JA = (
    "直通列車運賃: 大人13,000ウォン / 会員12,500ウォン、子ども9,500ウォン、"
    "シニア・障がい者・国家有功者9,500ウォン"
)
_AREX_FARE_NOTE_KO = "교환번호·제휴카드 할인 적용 시 해당 좌석은 어른 운임으로 변경됩니다."
_AREX_FARE_NOTE_JA = "交換番号・提携カード割引を適用する場合、該当座席は大人運賃扱いになります。"


def is_arex_next_train_question(message: str, keyword: str = "") -> bool:
    text = f"{message or ''} {keyword or ''}"
    if not re.search(r"(AREX|공항철도|직통열차|空港鉄道|直通列車)", text, re.IGNORECASE):
        return False
    return bool(re.search(r"(지금|현재|바로|다음|이후|탈 수|시간|열차|시각|now|next|현재 시간)", text, re.IGNORECASE))


def minutes_from_hhmm(hhmm: str) -> int:
    h, m = hhmm.split(":", 1)
    return int(h) * 60 + int(m)


def rail_time_label(raw: str) -> str:
    text = str(raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 12:
        return f"{digits[8:10]}:{digits[10:12]}"
    if len(digits) >= 4:
        return f"{digits[-4:-2]}:{digits[-2:]}"
    return text


def next_arex_express_rows(now: datetime | None = None, *, terminal: str = "T1", limit: int = 3) -> list[tuple[str, str]]:
    current = now or datetime.now()
    now_min = current.hour * 60 + current.minute
    idx = 1 if terminal.upper() == "T1" else 0
    rows = [(row[idx], row[2]) for row in _AREX_EXPRESS_T2_T1_SEOUL if minutes_from_hhmm(row[idx]) >= now_min]
    return rows[:limit]


def next_arex_rows_from_api(
    operations: list[AirportRailroadOperation],
    now: datetime,
    *,
    limit: int = 3,
) -> list[tuple[str, str, str]]:
    now_min = now.hour * 60 + now.minute
    rows: list[tuple[int, str, str, str]] = []
    for op in operations:
        dep = rail_time_label(op.departure_actual or op.departure_scheduled)
        if not re.fullmatch(r"\d{2}:\d{2}", dep):
            continue
        dep_min = minutes_from_hhmm(dep)
        if dep_min < now_min:
            continue
        arr = rail_time_label(op.arrival_actual or op.arrival_scheduled)
        rows.append((dep_min, dep, arr, op.train_class or "Dirc"))
    rows.sort(key=lambda row: row[0])
    return [(dep, arr, cls) for _, dep, arr, cls in rows[:limit]]


def fetch_arex_operations_for_now(now: datetime) -> list[AirportRailroadOperation]:
    client = IncheonAirportClient(timeout=8)
    if not client.is_configured:
        return []
    return client.search_airport_railroad(
        train_class="Dirc",
        operation_date=now.strftime("%Y%m%d"),
        station_code="100",
        limit=200,
    )


def arex_next_train_reply(
    reply_language: str,
    now: datetime | None = None,
    operations: list[AirportRailroadOperation] | None = None,
) -> str:
    current = now or datetime.now()
    api_rows: list[tuple[str, str, str]] = []
    data_source = "official_static"
    if operations is not None:
        api_rows = next_arex_rows_from_api(operations, current, limit=3)
        if api_rows:
            data_source = "api"
    else:
        try:
            api_rows = next_arex_rows_from_api(fetch_arex_operations_for_now(current), current, limit=3)
            if api_rows:
                data_source = "api"
        except Exception as exc:
            logger.warning("AREX railroad API fallback: %s", exc)
    fallback_rows = next_arex_express_rows(current, terminal="T1", limit=3)
    now_label = current.strftime("%H:%M")
    rows = [(dep, arr) for dep, arr, _ in api_rows] if api_rows else fallback_rows
    source_line_ko = "출처: 인천국제공항공사 공항철도 운행정보 API" if data_source == "api" else "출처: AREX 공식 시간표 기준"
    source_line_ja = "出典: 仁川国際空港公社 空港鉄道運行情報API" if data_source == "api" else "出典: AREX公式時刻表ベース"
    if reply_language == "日本語":
        if not rows:
            return (
                f"現在時刻 {now_label} 以降、仁川空港T1発ソウル駅行きのAREX直通列車は本日分が終了しています。\n\n"
                "一般列車または深夜バス・タクシーを検討してください。\n"
                f"{source_line_ja}\n"
                "AREX公式: https://www.airportrailroad.com/main"
            )
        lines = [f"現在時刻 {now_label} 以降、仁川空港T1からすぐ乗れるAREX直通列車です。", ""]
        for i, (dep, arr) in enumerate(rows, 1):
            lines.append(f"{i}. T1 {dep} 発 → ソウル駅 {arr} 着")
        lines.extend([
            "",
            "T2から乗る場合は、T1発の約8分前がT2発時刻の目安です。",
            "一般列車は直通より本数が多く、弘大入口・孔徳など途中駅で降りられます。",
            _AREX_EXPRESS_FARE_JA,
            _AREX_FARE_NOTE_JA,
            source_line_ja,
            "公式: https://www.airportrailroad.com/main",
        ])
        return "\n".join(lines)

    if not rows:
        return (
            f"현재 시각 {now_label} 이후 인천공항 T1 출발 서울역행 AREX 직통열차는 오늘 운행분이 종료된 상태입니다.\n\n"
            "이 경우 일반열차, 심야버스, 택시를 확인하는 쪽이 좋습니다.\n"
            f"{source_line_ko}\n"
            "AREX 공식: https://www.airportrailroad.com/main"
        )
    lines = [f"현재 시각 {now_label} 이후, 인천공항 T1에서 바로 탈 수 있는 AREX 직통열차입니다.", ""]
    for i, (dep, arr) in enumerate(rows, 1):
        lines.append(f"{i}. T1 {dep} 출발 → 서울역 {arr} 도착")
    lines.extend([
        "",
        "T2에서 타는 경우에는 T1 출발보다 약 8분 빠른 시간이 T2 출발 기준입니다.",
        "일반열차는 직통보다 배차가 더 많고, 홍대입구·공덕 등 중간역 하차가 가능합니다.",
        _AREX_EXPRESS_FARE_KO,
        _AREX_FARE_NOTE_KO,
        source_line_ko,
        "AREX 공식: https://www.airportrailroad.com/main",
    ])
    return "\n".join(lines)


def is_icn_to_seoul_transport_question(message: str, keyword: str = "") -> bool:
    text = f"{message or ''} {keyword or ''}"
    if not _ICN_SEOUL_TRANSPORT_RE.search(text):
        return False
    return bool(re.search(r"(교통|이동|가는|가려|방법|route|transport|アクセス|行き方|移動)", text, re.IGNORECASE))


def icn_to_seoul_transport_reply(reply_language: str) -> str:
    if reply_language == "日本語":
        return (
            "仁川空港からソウル市内へ行くなら、まずはこの3択です。\n\n"
            "1. AREX（空港鉄道）\n"
            "おすすめ: ソウル駅・弘大入口・孔徳方面へ行く時\n"
            "直通列車: T1/T2 → ソウル駅ノンストップ、約43分\n"
            f"{_AREX_EXPRESS_FARE_JA}\n"
            f"{_AREX_FARE_NOTE_JA}\n"
            "一般列車: 弘大入口・孔徳・DMCなど途中駅で下車可能\n"
            "時刻表・料金: AREX公式で確認\n"
            "公式: https://www.airportrailroad.com/main\n\n"
            "2. 空港リムジンバス\n"
            "おすすめ: 明洞・市庁・東大門・江南など、ホテル近くまで行きたい時\n"
            "料金目安: K Airport Limousineはソウル市内方面 大人18,000ウォン\n"
            "時刻表: 路線別に公式ページで確認\n"
            "公式: https://klimousine.com/EN/bus/bus.php\n\n"
            "3. タクシー\n"
            "おすすめ: 深夜到着・荷物が多い・ホテル前まで直接行きたい時\n"
            "明洞まで: 約80〜90分 / 約47,000〜52,000ウォン + 空港高速道路通行料7,900ウォン目安\n"
            "経路マップ: https://map.kakao.com/link/to/明洞,37.5638,126.9826\n"
            "タクシーアプリ: Kakao T https://www.kakaomobility.com/service-kakaot/\n\n"
            "迷ったら、ソウル駅方面はAREX、明洞・市庁・東大門のホテルならリムジンバス、深夜や大きな荷物がある時はタクシーが無難です。"
        )

    return (
        "인천공항에서 서울시내로 갈 때는 아래 3가지 중에서 고르면 됩니다.\n\n"
        "1. AREX(공항철도)\n"
        "추천: 서울역, 홍대입구, 공덕 방면 이동\n"
        "직통열차: 인천공항 T1/T2 → 서울역 논스톱, 약 43분\n"
        f"{_AREX_EXPRESS_FARE_KO}\n"
        f"{_AREX_FARE_NOTE_KO}\n"
        "일반열차: 홍대입구, 공덕, 디지털미디어시티 등 중간 하차 가능\n"
        "시간표/요금: AREX 공식에서 확인\n"
        "공식: https://www.airportrailroad.com/main\n\n"
        "2. 공항 리무진버스\n"
        "추천: 명동, 시청, 동대문, 강남 등 호텔·도심 정류장까지 바로 가고 싶을 때\n"
        "요금: K Airport Limousine 기준 서울시내 성인 18,000원\n"
        "시간표: 노선별 공식 페이지에서 확인\n"
        "공식: https://klimousine.com/KO/bus/bus.php\n"
        "인천공항 버스 검색: https://www.airport.kr/ap/ko/tpt/busRouteList.do\n\n"
        "3. 택시\n"
        "추천: 심야 도착, 큰 짐, 호텔 앞 이동이 필요할 때\n"
        "명동까지: 약 80~90분 / 약 47,000~52,000원 + 고속도로 통행료 7,900원 별도 기준\n"
        "경로맵: https://map.kakao.com/link/to/명동,37.5638,126.9826\n"
        "택시앱: Kakao T https://www.kakaomobility.com/service-kakaot/\n"
        "택시요금 안내: https://english.seoul.go.kr/policy/transportation/modes-of-transport/taxi/\n\n"
        "추천 기준: 서울역은 AREX, 명동·시청·동대문 호텔은 리무진버스, 심야나 큰 짐이 있으면 택시."
    )
