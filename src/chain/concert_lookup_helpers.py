"""Pure helpers for direct concert lookup routing."""

from __future__ import annotations

import re
from datetime import date, timedelta

CHAT_CONCERT_RE = re.compile(
    r"콘서트|공연|티켓|예매|팬미팅|케이팝|k[-\s]?pop|idol|アイドル|コンサート|公演",
    re.IGNORECASE,
)
CHAT_CONCERT_STOPWORDS_RE = re.compile(
    r"(콘서트|공연|정보|일정|알려|주세요|예매|티켓|팬미팅|내한|한국|대한민국|"
    r"케이팝|아이돌|서울|인천|부산|대구|대전|광주|울산|제주|"
    r"コンサート|公演|チケット|情報|教えて|日程|アイドル|k[-\s]?pop)",
    re.IGNORECASE,
)
CHAT_CONCERT_DATE_HINT_RE = re.compile(
    r"(?:20\d{2}\s*년\s*)?\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?|"
    r"(?:20\d{2}\s*年\s*)?\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?|"
    r"20\d{2}[-./]\d{1,2}(?:[-./]\d{1,2})?|"
    r"\d{1,2}[-./]\d{1,2}|"
    r"오늘|내일|今日|明日|today|tomorrow",
    re.IGNORECASE,
)
CHAT_CONCERT_KPOP_RE = re.compile(
    r"케이팝|k[-\s]?pop|아이돌|idol|アイドル",
    re.IGNORECASE,
)
CHAT_CONCERT_CONCERT_ONLY_RE = re.compile(
    r"콘서트|티켓|예매|팬미팅|ケイポップ|コンサート|チケット|k[-\s]?pop|idol",
    re.IGNORECASE,
)
CHAT_CONCERT_NATIONWIDE_REGION_KEYS: tuple[str, ...] = (
    "seoul",
    "gyeonggi",
    "incheon",
    "busan",
    "gyeongsang",
    "jeolla",
    "gangwon",
    "chungcheong",
    "jeju",
)
CHAT_CONCERT_REGION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"서울|ソウル|seoul", "seoul"),
    (r"경기|수원|고양|일산|킨텍스|KINTEX|gyeonggi", "gyeonggi"),
    (r"인천|仁川|incheon", "incheon"),
    (r"부산|釜山|busan", "busan"),
    (r"대구|울산|경북|경남|창원|포항|daegu|ulsan", "gyeongsang"),
    (r"대전|충청|청주|천안|dajeon|daejeon", "chungcheong"),
    (r"광주|전라|전주|목포|gwangju|jeolla", "jeolla"),
    (r"강원|강릉|춘천|속초|gangwon", "gangwon"),
    (r"제주|済州|jeju", "jeju"),
)

_CHAT_CONCERT_REGION_LABELS_KO: dict[str, str] = {
    "seoul": "서울",
    "gyeonggi": "경기",
    "incheon": "인천",
    "busan": "부산",
    "gyeongsang": "경상권",
    "jeolla": "전라권",
    "gangwon": "강원권",
    "chungcheong": "충청권",
    "jeju": "제주",
}
_CHAT_CONCERT_REGION_LABELS_JA: dict[str, str] = {
    "seoul": "ソウル",
    "gyeonggi": "京畿",
    "incheon": "仁川",
    "busan": "釜山",
    "gyeongsang": "慶尚圏",
    "jeolla": "全羅圏",
    "gangwon": "江原圏",
    "chungcheong": "忠清圏",
    "jeju": "済州",
}


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def near_future_month(year: int | None, month: int, today: date) -> int:
    if year is not None:
        return year
    candidate_year = today.year
    end_d = month_end(candidate_year, month)
    if end_d < today - timedelta(days=14):
        candidate_year += 1
    return candidate_year


def chat_concert_region_area_keys(message: str) -> list[str]:
    found: list[str] = []
    for pattern, key in CHAT_CONCERT_REGION_PATTERNS:
        if re.search(pattern, message or "", re.IGNORECASE) and key not in found:
            found.append(key)
    return found


def chat_lookup_date_window(message: str) -> tuple[date, date]:
    """Infer a date window for short chat questions."""
    text = message or ""
    today = date.today()
    if re.search(r"오늘|今日|today", text, re.IGNORECASE):
        return today, today
    if re.search(r"내일|明日|tomorrow", text, re.IGNORECASE):
        d = today + timedelta(days=1)
        return d, d

    m = re.search(r"(20\d{2})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})", text)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d, d
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})\s*(?:[./월])\s*(\d{1,2})\s*(?:일|日)?", text)
    if m:
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
            if d < today - timedelta(days=14):
                d = date(today.year + 1, d.month, d.day)
            return d, d
        except ValueError:
            pass

    m = re.search(r"(20\d{2})\s*[년年]\s*(\d{1,2})\s*[월月]", text)
    if m:
        try:
            y, mon = int(m.group(1)), int(m.group(2))
            return date(y, mon, 1), month_end(y, mon)
        except ValueError:
            pass

    m = re.search(r"(?<!\d)(\d{1,2})\s*[월月](?!\s*\d{1,2}\s*[일日])", text)
    if m:
        try:
            mon = int(m.group(1))
            y = near_future_month(None, mon, today)
            return date(y, mon, 1), month_end(y, mon)
        except ValueError:
            pass
    return today, today + timedelta(days=180)


def concert_artist_query(message: str) -> str:
    text = CHAT_CONCERT_DATE_HINT_RE.sub(" ", message or "")
    text = CHAT_CONCERT_STOPWORDS_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,!?\t\r\n")
    return text[:80]


def concert_period_label(start_d: date, end_d: date) -> str:
    if start_d == end_d:
        return start_d.isoformat()
    return f"{start_d.isoformat()}~{end_d.isoformat()}"


def concert_region_label(region_keys: list[str], reply_language: str) -> str:
    if not region_keys:
        return "全国" if reply_language == "日本語" else "전국"
    labels = _CHAT_CONCERT_REGION_LABELS_JA if reply_language == "日本語" else _CHAT_CONCERT_REGION_LABELS_KO
    return ", ".join(labels.get(k, k) for k in region_keys)


def concert_filter_label(message: str, artist: str, reply_language: str) -> str:
    if artist:
        return (
            f"アーティスト/キーワード: {artist}"
            if reply_language == "日本語"
            else f"아티스트/키워드: {artist}"
        )
    if CHAT_CONCERT_KPOP_RE.search(message or ""):
        return (
            "K-pop/大衆音楽コンサート"
            if reply_language == "日本語"
            else "K-pop/대중음악 콘서트"
        )
    if CHAT_CONCERT_CONCERT_ONLY_RE.search(message or ""):
        return "コンサート" if reply_language == "日本語" else "콘서트"
    return "公演全体" if reply_language == "日本語" else "전체 공연"


def concert_lookup_reply(
    *,
    reply_language: str,
    message: str,
    artist: str,
    region_keys: list[str],
    start_d: date,
    end_d: date,
    events_count: int,
    raw_count: int,
    web_lines: list[str],
) -> str:
    period = concert_period_label(start_d, end_d)
    region = concert_region_label(region_keys, reply_language)
    filt = concert_filter_label(message, artist, reply_language)

    if reply_language == "日本語":
        header = (
            "KOPISで公演情報を確認しました。\n"
            f"- 期間: {period}\n"
            f"- 地域: {region}\n"
            f"- 条件: {filt}\n"
        )
        if events_count:
            return (
                header
                + f"- 結果: {events_count}件をカード表示\n\n"
                "下のカードで日程・会場・詳細リンクを確認できます。"
            )
        if web_lines:
            return (
                header
                + "- KOPIS結果: 条件に一致するカードなし\n\n"
                "KOPISでは一致する公演を確認できませんでした。参考になる公式/ニュース検索結果です。\n\n"
                + "\n".join(web_lines)
            )
        broader = (
            f"\n同じ期間のKOPIS公演候補は{raw_count}件ありましたが、"
            "K-pop/大衆音楽コンサート条件ではカード化できる一致がありませんでした。"
            if raw_count and CHAT_CONCERT_KPOP_RE.search(message or "")
            else ""
        )
        return (
            header
            + "- KOPIS結果: 条件に一致するカードなし"
            + broader
            + "\n\n次は「7月 公演情報」「7月 ソウル コンサート」「アーティスト名 + 7月 コンサート」のように聞くと絞り込みやすいです。"
        )

    header = (
        "KOPIS 기준으로 공연 정보를 확인했습니다.\n"
        f"- 기간: {period}\n"
        f"- 지역: {region}\n"
        f"- 조건: {filt}\n"
    )
    if events_count:
        return (
            header
            + f"- 결과: {events_count}건을 카드로 표시\n\n"
            "아래 카드에서 일정, 장소, 상세 링크를 확인해 주세요."
        )
    if web_lines:
        return (
            header
            + "- KOPIS 결과: 조건에 맞는 카드 없음\n\n"
            "KOPIS에서는 일치하는 공연을 확인하지 못했습니다. 참고 가능한 공식/뉴스 검색 결과입니다.\n\n"
            + "\n".join(web_lines)
        )
    broader = (
        f"\n같은 기간의 KOPIS 공연 후보는 {raw_count}건 있었지만, "
        "K-pop/대중음악 콘서트 조건으로 카드화할 일치 결과는 없었습니다."
        if raw_count and CHAT_CONCERT_KPOP_RE.search(message or "")
        else ""
    )
    return (
        header
        + "- KOPIS 결과: 조건에 맞는 카드 없음"
        + broader
        + "\n\n다음에는 `7월 공연정보`, `7월 서울 콘서트`, `아티스트명 + 7월 콘서트`처럼 물으면 더 잘 좁힐 수 있습니다."
    )
