"""한국 프로스포츠 일정 조회 (KBO / KBL / KOVO / K리그).

- K리그: https://www.kleague.com/schedule.do → POST /getScheduleList.do
- KBL: https://www.kbl.or.kr/match/schedule (SPA — 일정 API 미공개 시 안내만)
- KOVO: https://kovo.co.kr/games/v-leagues/schedules (SPA)
- KBO: https://www.koreabaseball.com (시즌 종료 시 빈 결과 + 안내)
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "sports_schedule.json"

_LEAGUE_META: dict[str, dict[str, str]] = {
    "kbo": {
        "label_ja": "KBO（プロ野球）",
        "official_url": "https://www.koreabaseball.com/Schedule/Schedule.aspx",
        "schedule_url": "https://www.koreabaseball.com/Schedule/Schedule.aspx",
        "ws_url": "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList",
        "off_season_months": [12, 1, 2],  # KBO off-season: Dec–Feb only
        "off_season_note_ja": (
            "KBOシーズン外（12〜2月）のため試合がありません。"
            "公式サイトで次シーズン日程をご確認ください。"
        ),
    },
    "kbl": {
        "label_ja": "KBL（プロバスケ）",
        "official_url": "https://www.kbl.or.kr/match/schedule",
        "schedule_url": "https://www.kbl.or.kr/match/schedule",
        "off_season_months": [5, 6, 7, 8, 9],  # KBL season: Oct–Apr
        "off_season_note_ja": (
            "KBLシーズン外（5〜9月）のため試合がありません。"
            "公式サイトで来季日程をご確認ください。"
        ),
    },
    "kovo": {
        "label_ja": "KOVO（Vリーグ）",
        "official_url": "https://kovo.co.kr/games/v-leagues/schedules",
        "schedule_url": "https://kovo.co.kr/games/v-leagues/schedules",
        "off_season_months": [5, 6, 7, 8],  # V-League season: Oct–Apr
        "off_season_note_ja": (
            "VリーグはシーズンAway（5〜8月）のため試合がありません。"
            "公式サイトで来季日程をご確認ください。"
        ),
    },
    "kleague": {
        "label_ja": "Kリーグ（サッカー）",
        "official_url": "https://www.kleague.com/schedule.do?leagueId=1",
        "schedule_url": "https://www.kleague.com/schedule.do?leagueId=1",
        "off_season_note_ja": "該当月に登録試合がない場合は公式日程で最新情報をご確認ください。",
    },
}

# KBO 구단별 예매처 (홈팀 기준)
# 티켓링크: LG·한화·삼성·KT·KIA  /  인터파크: 두산(PB004)·키움(PB003)  /  자체예매: SSG·롯데·NC
_KBO_TICKET_MAP: dict[str, str] = {
    "LG":   "https://www.ticketlink.co.kr/sports/baseball",
    "한화":  "https://www.ticketlink.co.kr/sports/baseball",
    "삼성":  "https://www.ticketlink.co.kr/sports/baseball",
    "KT":   "https://www.ticketlink.co.kr/sports/baseball",
    "KIA":  "https://www.ticketlink.co.kr/sports/baseball",
    "두산":  "https://ticket.interpark.com/Contents/Sports/GoodsInfo?SportsCode=07001&TeamCode=PB004",
    "키움":  "https://ticket.interpark.com/Contents/Sports/GoodsInfo?SportsCode=07001&TeamCode=PB003",
    "SSG":  "https://www.ssglanders.com/main",
    "롯데":  "https://www.giantsclub.com/contents/ticket",
    "NC":   "https://ticket.ncdinos.com/",
}

_KBO_VENUE_DISPLAY: dict[str, str] = {
    "잠실": "잠실야구장",
    "고척": "고척스카이돔",
    "대구": "대구 삼성라이온즈파크",
    "창원": "창원 NC파크",
    "대전": "대전 한화생명볼파크",
    "사직": "부산 사직야구장",
    "문학": "인천 SSG랜더스필드",
    "수원": "수원 KT위즈파크",
    "광주": "광주-KIA챔피언스필드",
    "울산": "울산 문수야구장",
    "청주": "청주야구장",
    "포항": "포항야구장",
}

_SPORT_TO_LEAGUES: dict[str, list[str]] = {
    "soccer": ["kleague"],
    "baseball": ["kbo"],
    "basketball": ["kbl"],
    "volleyball": ["kovo"],
    "sports": ["kbo", "kbl", "kovo", "kleague"],
}

# 숙소·경기장 위치 추정용 (위도, 경도)
_CITY_CENTROIDS: dict[str, tuple[float, float]] = {
    "서울": (37.5665, 126.9780),
    "ソウル": (37.5665, 126.9780),
    "seoul": (37.5665, 126.9780),
    "잠실": (37.5120, 127.0719),
    "송파": (37.5120, 127.0719),
    "고척": (37.4682, 126.8970),
    "구로": (37.4682, 126.8970),
    "강남": (37.4979, 127.0276),
    "명동": (37.5636, 126.9869),
    "홍대": (37.5563, 126.9236),
    "인천": (37.4563, 126.7052),
    "仁川": (37.4563, 126.7052),
    "incheon": (37.4563, 126.7052),
    "수원": (37.2998, 127.0096),
    "용인": (37.2411, 127.1776),
    "성남": (37.4200, 127.1265),
    "고양": (37.6584, 126.8320),
    "부산": (35.1796, 129.0756),
    "釜山": (35.1796, 129.0756),
    "busan": (35.1796, 129.0756),
    "대구": (35.8714, 128.6014),
    "대전": (36.3504, 127.3845),
    "大田": (36.3504, 127.3845),
    "daejeon": (36.3504, 127.3845),
    "유성": (36.3620, 127.3560),
    "광주": (35.1595, 126.8526),
    "창원": (35.2285, 128.6811),
    "마산": (35.2285, 128.6811),
    "전주": (35.8242, 127.1480),
    "제주": (33.4996, 126.5312),
    "済州": (33.4996, 126.5312),
    "jeju": (33.4996, 126.5312),
    "천안": (36.8151, 127.1139),
    "아산": (36.7898, 127.0018),
    "충남": (36.8151, 127.1139),
    "김해": (35.2285, 128.8890),
    "김포": (37.6153, 126.7155),
    "파주": (37.7599, 126.7800),
    "광양": (34.9404, 127.6909),
    "안산": (37.3219, 126.8309),
    "화성": (37.1995, 126.8310),
    "충남": (36.8151, 127.1139),
    "아산": (36.7898, 127.0018),
    "대전월드컵": (36.3174, 127.4294),
    "문학": (37.4370, 126.6930),
    "사직": (35.1940, 129.0615),
    "광주기아": (35.1684, 126.8895),
}

_REGION_CHIP_CENTROIDS: dict[str, tuple[float, float]] = {
    "seoul": (37.5665, 126.9780),
    "gyeonggi": (37.6584, 126.8320),
    "incheon": (37.4563, 126.7052),
    "gangwon": (37.7519, 128.8760),
    "chungcheong": (36.3504, 127.3845),
    "jeolla": (35.8242, 127.1480),
    "gyeongsang": (35.1796, 129.0756),
    "busan": (35.1796, 129.0756),
    "jeju": (33.4996, 126.5312),
}

_REGION_CHIP_EXTRA_CENTERS: dict[str, list[tuple[float, float]]] = {
    # 광역 권역 선택 시 한 도시 중심만 보지 않도록 보강
    "gyeongsang": [
        (35.8419, 128.6814),  # 대구 삼성라이온즈파크
        (35.1689, 128.5850),  # 창원 NC파크
        (35.1940, 129.0615),  # 부산 사직
        (35.5384, 129.3114),  # 울산
    ],
    "jeolla": [
        (35.1684, 126.8895),  # 광주 KIA챔피언스필드
        (35.8683, 127.1286),  # 전주월드컵
    ],
    "chungcheong": [
        (36.3174, 127.4294),  # 대전월드컵/한화
        (36.8151, 127.1139),  # 천안
    ],
    "gyeonggi": [
        (37.2998, 127.0096),  # 수원
        (37.3943, 126.9467),  # 안양
        (37.4860, 126.6900),  # 인천삼산(수도권 인접)
        (37.6153, 126.7155),  # 김포
    ],
}

# (키워드…), lat, lng — 경기장·구단 홈 기준
_VENUE_COORDS: list[tuple[tuple[str, ...], float, float]] = [
    (("잠실", "롯데자이언츠", "jamsil"), 37.5120, 127.0719),
    (("고척", "고척스카이돔", "키움"), 37.4682, 126.8970),
    (("대구", "삼성라이온즈", "라이온즈파크"), 35.8419, 128.6814),
    (("창원", "nc파크", "nc park"), 35.1689, 128.5850),
    (("대전", "한화생명", "한화"), 36.3174, 127.4294),
    (("광주", "기아", "kia"), 35.1684, 126.8895),
    (("부산", "사직", "롯데자이언츠", "자이언츠파크"), 35.1940, 129.0615),
    (("수원", "kt wiz", "위즈파크"), 37.2998, 127.0096),
    (("인천", "문학", "ssg", "랜더스"), 37.4370, 126.6930),
    (("서울월드컵", "상암", "fc서울"), 37.5683, 126.8972),
    (("전주", "전북"), 35.8683, 127.1286),
    (("대전월드컵", "대전시티"), 36.3174, 127.4294),
    (("천안", "천안아산"), 36.8151, 127.1139),
    (("아산", "아산"), 36.7898, 127.0018),
    (("김해", "김해"), 35.2285, 128.8890),
    (("김포", "김포"), 37.6153, 126.7155),
    (("파주", "파주"), 37.7599, 126.7800),
    (("용인", "용인"), 37.2411, 127.1776),
    (("성남", "성남"), 37.4200, 127.1265),
    # KBL 농구 경기장
    (("잠실실내체육관", "서울 sk", "sk나이츠", "삼성썬더스", "서울삼성"), 37.5120, 127.0719),
    (("사직실내체육관", "부산 kcc", "kcc이지스"), 35.1940, 129.0615),
    (("대구실내체육관", "한국가스공사", "페가수스"), 35.8714, 128.6014),
    (("삼산체육관", "인천삼산", "인천 전자랜드", "전자랜드"), 37.4860, 126.6900),
    (("안양실내체육관", "안양 정관장", "정관장", "레드부스터"), 37.3943, 126.9467),
    (("동천체육관", "울산 현대모비스", "현대모비스", "피버스"), 35.5384, 129.3114),
    (("창원실내체육관", "창원 lg", "lg세이커스"), 35.2285, 128.6811),
    (("kt소닉붐", "수원 kt", "소닉붐"), 37.2998, 127.0096),
    (("원주종합체육관", "원주 db", "db프로미"), 37.3422, 127.9202),
    # KOVO 배구 경기장
    (("장충체육관", "서울 gs", "gs칼텍스", "우리카드"), 37.5594, 127.0063),
    (("의정부실내체육관", "의정부 kb", "ibk기업은행", "알토스"), 37.7380, 127.0445),
    (("천안유관순체육관", "현대캐피탈", "스카이워커스"), 36.8151, 127.1139),
    (("인천삼산월드체육관", "대한항공", "점보스", "흥국생명"), 37.4860, 126.6900),
    (("페퍼저축은행", "ai페퍼스", "광주페퍼"), 35.1595, 126.8526),
    (("충무체육관", "삼성화재", "블루팡스", "kgc인삼공사"), 36.3504, 127.3845),
    (("한국전력", "빅스톰"), 37.2998, 127.0096),
    (("ok금융그룹", "읏맨"), 37.3219, 126.8309),
]

_KBO_HOME_COORDS: dict[str, tuple[float, float]] = {
    "LG": (37.5120, 127.0719),
    "두산": (37.5120, 127.0719),
    "키움": (37.4682, 126.8970),
    "한화": (36.3174, 127.4294),
    "삼성": (35.8419, 128.6814),
    "NC": (35.1689, 128.5850),
    "롯데": (35.1940, 129.0615),
    "SSG": (37.4370, 126.6930),
    "KT": (37.2998, 127.0096),
    "KIA": (35.1684, 126.8895),
}

_KBL_HOME_COORDS: dict[str, tuple[float, float]] = {
    "서울 SK": (37.5120, 127.0719),
    "SK나이츠": (37.5120, 127.0719),
    "서울 삼성": (37.5120, 127.0719),
    "삼성썬더스": (37.5120, 127.0719),
    "부산 KCC": (35.1940, 129.0615),
    "KCC이지스": (35.1940, 129.0615),
    "한국가스공사": (35.8714, 128.6014),
    "페가수스": (35.8714, 128.6014),
    "인천 전자랜드": (37.4860, 126.6900),
    "전자랜드": (37.4860, 126.6900),
    "안양 정관장": (37.3943, 126.9467),
    "정관장": (37.3943, 126.9467),
    "울산 현대모비스": (35.5384, 129.3114),
    "현대모비스": (35.5384, 129.3114),
    "창원 LG": (35.2285, 128.6811),
    "LG세이커스": (35.2285, 128.6811),
    "수원 KT": (37.2998, 127.0096),
    "KT소닉붐": (37.2998, 127.0096),
    "원주 DB": (37.3422, 127.9202),
    "DB프로미": (37.3422, 127.9202),
}

_KOVO_HOME_COORDS: dict[str, tuple[float, float]] = {
    "GS칼텍스": (37.5594, 127.0063),
    "우리카드": (37.5594, 127.0063),
    "흥국생명": (37.4860, 126.6900),
    "대한항공": (37.4860, 126.6900),
    "현대캐피탈": (36.8151, 127.1139),
    "현대건설": (37.2998, 127.0096),
    "IBK기업은행": (37.7380, 127.0445),
    "삼성화재": (36.3504, 127.3845),
    "KGC인삼공사": (36.3504, 127.3845),
    "OK금융그룹": (37.3219, 126.8309),
    "한국전력": (37.2998, 127.0096),
    "페퍼저축은행": (35.1595, 126.8526),
}

NEARBY_SPORTS_MAX_KM = 25.0

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,ja;q=0.8",
}


@dataclass(frozen=True)
class SportsMatch:
    league: str
    date: str  # YYYY-MM-DD
    time: str | None
    home_team: str
    away_team: str
    venue: str
    official_url: str
    status: str = "scheduled"  # scheduled | off_season_notice | fetch_failed
    ticket_url: str = ""  # 홈팀 기준 예매처 URL

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SportsScheduleClient:
    """여행 기간·종목에 맞는 경기 일정을 조회."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def search(
        self,
        *,
        leagues: list[str],
        start: date | None,
        end: date | None,
        max_per_league: int = 8,
    ) -> list[SportsMatch]:
        if not leagues:
            return []

        if start is None:
            start = date.today()
        if end is None:
            end = start + timedelta(days=14)
        if end < start:
            start, end = end, start

        seen: set[tuple[str, str, str, str]] = set()
        out: list[SportsMatch] = []
        leagues_found: set[str] = set()

        for league in leagues:
            league = league.lower()
            if league not in _LEAGUE_META:
                continue
            try:
                batch = self._fetch_league(league, start, end)
            except Exception as exc:
                logger.warning("sports fetch %s failed: %s", league, exc)
                batch = []
            if batch:
                leagues_found.add(league)
            for m in batch:
                key = (m.league, m.date, m.home_team, m.away_team)
                if key in seen:
                    continue
                seen.add(key)
                out.append(m)
                if (
                    sum(1 for x in out if _league_bucket(x.league) == _league_bucket(league))
                    >= max_per_league
                ):
                    break

        # 캐시 (수동 갱신분)
        if not out:
            out = self._load_cache(start, end, leagues)
            if out:
                return out[: max_per_league * len(leagues)]

        # 경기 없음 → 실제 오프시즌인 리그만 off_season 안내, 나머지는 fetch_failed 안내
        missing = [lg for lg in leagues if lg in _LEAGUE_META and lg not in leagues_found]
        if not out and missing:
            off_season = [lg for lg in missing if self._is_off_season(lg, start, end)]
            fetch_fail = [lg for lg in missing if lg not in off_season]
            out = self._off_season_notices(off_season, start, end)
            out += self._fetch_failed_notices(fetch_fail, start, end)

        out.sort(key=lambda m: (m.status != "scheduled", m.date, m.time or "99:99", m.league))
        return out[: max_per_league * len(leagues) + len(missing)]

    def _fetch_league(self, league: str, start: date, end: date) -> list[SportsMatch]:
        if league == "kleague":
            return self._fetch_kleague(start, end)
        if league == "kbo":
            return self._fetch_kbo(start, end)
        if league == "kbl":
            return self._fetch_kbl(start, end)
        if league == "kovo":
            return self._fetch_kovo(start, end)
        return []

    def _is_off_season(self, league: str, start: date, end: date) -> bool:
        months = _LEAGUE_META.get(league, {}).get("off_season_months")
        if not months:
            return False
        return all(d.month in months for d in (start, end))

    def _fetch_kleague(self, start: date, end: date) -> list[SportsMatch]:
        """K리그 공식 POST API (schedule.do 와 동일 데이터)."""
        meta = _LEAGUE_META["kleague"]
        matches: list[SportsMatch] = []
        headers = {
            **_HEADERS,
            "Content-Type": "application/json; charset=utf-8",
            "Referer": meta["schedule_url"],
            "Origin": "https://www.kleague.com",
        }
        url = "https://www.kleague.com/getScheduleList.do"

        cur = start.replace(day=1)
        while cur <= end:
            for league_id in ("1", "2"):
                # etcYn=Y 는 scheduleList 가 비는 경우가 있음(2026 기준). N=정규 월별 일정.
                body = {
                    "year": str(cur.year),
                    "month": f"{cur.month:02d}",
                    "leagueId": league_id,
                    "etcYn": "N",
                }
                try:
                    resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
                    if resp.ok:
                        batch = self._parse_kleague_json(
                            resp.json(), meta["official_url"], start, end, league_id
                        )
                        matches.extend(batch)
                        if batch:
                            logger.info(
                                "kleague ok %s/%02d leagueId=%s → %d matches in range",
                                cur.year,
                                cur.month,
                                league_id,
                                len(batch),
                            )
                    else:
                        logger.warning(
                            "kleague HTTP %s leagueId=%s %s/%02d",
                            resp.status_code,
                            league_id,
                            cur.year,
                            cur.month,
                        )
                except Exception as exc:
                    logger.warning("kleague fetch %s: %s", body, exc)
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

        return matches

    def _parse_kleague_json(
        self,
        data: Any,
        official_url: str,
        start: date,
        end: date,
        league_id: str,
    ) -> list[SportsMatch]:
        if not isinstance(data, dict):
            return []
        rows = (data.get("data") or {}).get("scheduleList") or []
        out: list[SportsMatch] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            raw_date = str(
                item.get("gameDate")
                or item.get("matchDate")
                or item.get("meetDate")
                or ""
            )
            d = self._normalize_date(raw_date)
            if not d or not (start <= d <= end):
                continue
            home = str(
                item.get("homeTeamName")
                or item.get("homeName")
                or item.get("homeTeam")
                or ""
            ).strip()
            away = str(
                item.get("awayTeamName")
                or item.get("awayName")
                or item.get("awayTeam")
                or ""
            ).strip()
            if not home and not away:
                continue
            venue = str(
                item.get("fieldNameFull")
                or item.get("fieldName")
                or item.get("stadiumName")
                or item.get("stadium")
                or item.get("placeName")
                or ""
            ).strip()
            t = self._normalize_time(
                str(item.get("gameTime") or item.get("matchTime") or item.get("time") or "")
            )
            league_code = "kleague2" if league_id == "2" else "kleague"
            sched_url = (
                "https://www.kleague.com/schedule.do?leagueId=2"
                if league_id == "2"
                else official_url
            )
            out.append(
                SportsMatch(
                    league=league_code,
                    date=d.isoformat(),
                    time=t,
                    home_team=home or "?",
                    away_team=away or "?",
                    venue=venue or "会場未確認",
                    official_url=sched_url,
                )
            )
        return out

    def _fetch_kbo(self, start: date, end: date) -> list[SportsMatch]:
        """KBO — ASMX POST returning HTML-table JSON ({rows: [...]})."""
        meta = _LEAGUE_META["kbo"]
        matches: list[SportsMatch] = []

        ws_headers = {
            **_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": meta["official_url"],
            "Origin": "https://www.koreabaseball.com",
            "X-Requested-With": "XMLHttpRequest",
        }

        cur = start.replace(day=1)
        while cur <= end:
            # srIdList=0,9,6 → 정규시즌(0) + 와일드카드(9) + 준플레이오프(6)
            payload = (
                f"leId=1&srIdList=0%2C9%2C6"
                f"&seasonId={cur.year}&gameMonth={cur.month:02d}&teamId="
            )
            try:
                resp = requests.post(
                    meta["ws_url"], headers=ws_headers, data=payload, timeout=self.timeout
                )
                if resp.ok:
                    rows = resp.json().get("rows", [])
                    batch = self._parse_kbo_table_rows(rows, meta["official_url"], start, end, cur.year)
                    if batch:
                        matches.extend(batch)
                        logger.info("kbo asmx ok %d/%02d → %d matches", cur.year, cur.month, len(batch))
                    else:
                        logger.debug("kbo asmx empty %d/%02d", cur.year, cur.month)
            except Exception as exc:
                logger.warning("kbo asmx %d/%02d: %s", cur.year, cur.month, exc)

            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

        return matches

    def _parse_kbo_table_rows(
        self, rows: list, official_url: str, start: date, end: date, season_year: int
    ) -> list[SportsMatch]:
        """Parse KBO ASMX table-row response into SportsMatch objects.

        Row cell layout (Class field):
          'day'   → date string like "05.29(금)"  (RowSpan covers several game rows)
          'time'  → game time like "18:30"
          'play'  → matchup like "KIAvsLG" or "NC1vs5LG" (away vs home, scores stripped)
          'relay' → broadcast info (ignored)
          None    → misc cells; second-to-last is venue, last is always "-"
        """

        def _strip(txt: str) -> str:
            return re.sub(r"<[^>]+>", "", txt or "").strip()

        out: list[SportsMatch] = []
        current_day_str = ""

        for row in rows:
            cells = row.get("row", [])

            # Update current date when a 'day' cell is present
            for c in cells:
                if c.get("Class") == "day":
                    current_day_str = _strip(c.get("Text", ""))
                    break

            # Parse date: "05.29(금)" → date(season_year, 5, 29)
            dm = re.match(r"(\d{2})\.(\d{2})", current_day_str)
            if not dm:
                continue
            try:
                d = date(season_year, int(dm.group(1)), int(dm.group(2)))
            except ValueError:
                continue
            if not (start <= d <= end):
                continue

            # Time
            game_time = None
            for c in cells:
                if c.get("Class") == "time":
                    game_time = self._normalize_time(_strip(c.get("Text", "")))
                    break

            # Matchup: "KIAvsLG" → away=KIA, home=LG  /  "NC1vs5LG" → away=NC, home=LG
            play_text = ""
            for c in cells:
                if c.get("Class") == "play":
                    play_text = _strip(c.get("Text", ""))
                    break
            if "vs" not in play_text:
                continue
            parts = play_text.split("vs", 1)
            away = re.sub(r"\d+", "", parts[0]).strip()
            home = re.sub(r"\d+", "", parts[1]).strip()
            if not away and not home:
                continue

            # Venue: second-to-last among Class=None cells
            none_cells = [c for c in cells if c.get("Class") is None]
            venue = _strip(none_cells[-2].get("Text", "")) if len(none_cells) >= 2 else ""
            venue = _KBO_VENUE_DISPLAY.get(venue, venue)

            out.append(SportsMatch(
                league="kbo",
                date=d.isoformat(),
                time=game_time,
                home_team=home or "?",
                away_team=away or "?",
                venue=venue or "球場（要確認）",
                official_url=official_url,
                ticket_url=_KBO_TICKET_MAP.get(home, ""),
            ))

        return out

    def _fetch_kbl(self, start: date, end: date) -> list[SportsMatch]:
        """KBL 농구 일정 — 공식 REST API 시도, 실패 시 빈 목록."""
        meta = _LEAGUE_META["kbl"]
        matches: list[SportsMatch] = []
        headers = {
            **_HEADERS,
            "Referer": meta["schedule_url"],
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.kbl.or.kr",
        }

        cur = start.replace(day=1)
        while cur <= end:
            # KBL season: starts in October — e.g., Oct 2024 → season "2024-25"
            season_start = cur.year if cur.month >= 9 else cur.year - 1
            season_label = f"{season_start}-{str(season_start + 1)[-2:]}"

            # Try known KBL API endpoint patterns (SPA internal API)
            attempts = [
                {
                    "method": "GET",
                    "url": (
                        f"https://www.kbl.or.kr/api/v1/schedule/list"
                        f"?season={season_label}&month={cur.month:02d}"
                    ),
                },
                {
                    "method": "POST",
                    "url": "https://www.kbl.or.kr/api/schedule/getList",
                    "json": {"year": cur.year, "month": cur.month},
                },
                {
                    "method": "GET",
                    "url": (
                        f"https://www.kbl.or.kr/match/schedule"
                        f"?year={cur.year}&month={cur.month:02d}"
                    ),
                },
            ]

            for attempt in attempts:
                try:
                    if attempt["method"] == "POST":
                        resp = requests.post(
                            attempt["url"],
                            headers=headers,
                            json=attempt.get("json"),
                            timeout=self.timeout,
                        )
                    else:
                        resp = requests.get(
                            attempt["url"], headers=headers, timeout=self.timeout
                        )
                    ct = resp.headers.get("content-type", "")
                    if resp.ok and "json" in ct:
                        data = resp.json()
                        batch = self._parse_kbl_json(data, meta["official_url"], start, end)
                        if batch:
                            matches.extend(batch)
                            logger.info(
                                "kbl ok %d/%02d → %d matches", cur.year, cur.month, len(batch)
                            )
                            break
                except Exception as exc:
                    logger.debug("kbl attempt %s: %s", attempt["url"], exc)

            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

        return matches

    def _parse_kbl_json(
        self, data: Any, official_url: str, start: date, end: date
    ) -> list[SportsMatch]:
        """KBL JSON 응답을 SportsMatch 목록으로 파싱 (다양한 키 이름 허용)."""
        rows: list = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            for key in ("data", "list", "scheduleList", "games", "result", "items"):
                v = data.get(key)
                if isinstance(v, list):
                    rows = v
                    break
                if isinstance(v, dict):
                    for k2 in ("list", "scheduleList", "games"):
                        v2 = v.get(k2)
                        if isinstance(v2, list):
                            rows = v2
                            break
                    if rows:
                        break
        out: list[SportsMatch] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            raw_date = str(
                item.get("gameDate") or item.get("matchDate") or item.get("date") or ""
            )
            d = self._normalize_date(raw_date)
            if not d or not (start <= d <= end):
                continue
            home = str(
                item.get("homeTeamName") or item.get("homeName") or item.get("home") or ""
            ).strip()
            away = str(
                item.get("awayTeamName") or item.get("awayName") or item.get("away") or ""
            ).strip()
            if not home and not away:
                continue
            venue = str(
                item.get("stadiumName") or item.get("venue") or item.get("arena") or ""
            ).strip()
            t = self._normalize_time(
                str(item.get("gameTime") or item.get("matchTime") or item.get("time") or "")
            )
            out.append(
                SportsMatch(
                    league="kbl",
                    date=d.isoformat(),
                    time=t,
                    home_team=home or "?",
                    away_team=away or "?",
                    venue=venue or (home + " 홈구장" if home else "会場未確認"),
                    official_url=official_url,
                )
            )
        return out

    def _fetch_kovo(self, start: date, end: date) -> list[SportsMatch]:
        """KOVO V리그 배구 일정 — 공식 REST API 시도, 실패 시 빈 목록."""
        meta = _LEAGUE_META["kovo"]
        matches: list[SportsMatch] = []
        headers = {
            **_HEADERS,
            "Referer": meta["schedule_url"],
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://kovo.co.kr",
        }

        cur = start.replace(day=1)
        while cur <= end:
            # KOVO season number: 2022-23 = 022, 2024-25 = 024
            season_start = cur.year if cur.month >= 9 else cur.year - 1
            season_num = f"0{season_start - 2000:02d}"

            attempts = [
                {
                    "method": "GET",
                    "url": (
                        f"https://kovo.co.kr/api/games/v-leagues/schedules"
                        f"?season={season_num}&gender=all&league=200&round=all"
                        f"&year={cur.year}&month={cur.month:02d}"
                    ),
                },
                {
                    "method": "GET",
                    "url": (
                        f"https://kovo.co.kr/api/schedule/list"
                        f"?season={season_num}&month={cur.month:02d}"
                    ),
                },
                {
                    "method": "POST",
                    "url": "https://kovo.co.kr/api/schedule/search",
                    "json": {
                        "season": season_num,
                        "year": cur.year,
                        "month": cur.month,
                        "gender": "all",
                        "league": "200",
                    },
                },
            ]

            for attempt in attempts:
                try:
                    if attempt["method"] == "POST":
                        resp = requests.post(
                            attempt["url"],
                            headers=headers,
                            json=attempt.get("json"),
                            timeout=self.timeout,
                        )
                    else:
                        resp = requests.get(
                            attempt["url"], headers=headers, timeout=self.timeout
                        )
                    ct = resp.headers.get("content-type", "")
                    if resp.ok and "json" in ct:
                        data = resp.json()
                        batch = self._parse_kovo_json(data, meta["official_url"], start, end)
                        if batch:
                            matches.extend(batch)
                            logger.info(
                                "kovo ok %d/%02d → %d matches", cur.year, cur.month, len(batch)
                            )
                            break
                except Exception as exc:
                    logger.debug("kovo attempt %s: %s", attempt["url"], exc)

            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)

        return matches

    def _parse_kovo_json(
        self, data: Any, official_url: str, start: date, end: date
    ) -> list[SportsMatch]:
        """KOVO JSON 응답을 SportsMatch 목록으로 파싱."""
        rows: list = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            for key in ("data", "list", "scheduleList", "games", "result", "items", "schedule"):
                v = data.get(key)
                if isinstance(v, list):
                    rows = v
                    break
                if isinstance(v, dict):
                    for k2 in ("list", "scheduleList", "games", "items"):
                        v2 = v.get(k2)
                        if isinstance(v2, list):
                            rows = v2
                            break
                    if rows:
                        break
        out: list[SportsMatch] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            raw_date = str(
                item.get("gameDate") or item.get("matchDate") or item.get("date") or ""
            )
            d = self._normalize_date(raw_date)
            if not d or not (start <= d <= end):
                continue
            home = str(
                item.get("homeTeamName") or item.get("homeName") or item.get("home") or ""
            ).strip()
            away = str(
                item.get("awayTeamName") or item.get("awayName") or item.get("away") or ""
            ).strip()
            if not home and not away:
                continue
            venue = str(
                item.get("stadiumName") or item.get("venueName") or item.get("arena") or ""
            ).strip()
            t = self._normalize_time(
                str(item.get("gameTime") or item.get("matchTime") or item.get("time") or "")
            )
            gender_raw = str(item.get("gender") or item.get("sex") or "")
            league_code = "kovo_w" if "w" in gender_raw.lower() or "여" in gender_raw else "kovo"
            out.append(
                SportsMatch(
                    league=league_code,
                    date=d.isoformat(),
                    time=t,
                    home_team=home or "?",
                    away_team=away or "?",
                    venue=venue or (home + " 홈체육관" if home else "会場未確認"),
                    official_url=official_url,
                )
            )
        return out

    def _fetch_failed_notices(
        self, leagues: list[str], start: date, end: date
    ) -> list[SportsMatch]:
        """試合データ取得失敗 — 日付入りURLで公式サイトへ誘導 (オフシーズンとは区別)。"""
        out: list[SportsMatch] = []
        for lg in leagues:
            meta = _LEAGUE_META.get(lg, {})
            base_sched = meta.get("schedule_url") or meta.get("official_url", "")
            dated_url = self._dated_schedule_url(lg, base_sched, start)
            if lg == "kbo":
                away_note = (
                    "下記公式サイトで日程確認後、チケットを購入してください。"
                    " ティケットリンク(LG·한화·삼성·KT·KIA): https://www.ticketlink.co.kr/sports/baseball"
                    " / インターパーク 두산: https://ticket.interpark.com/Contents/Sports/GoodsInfo?SportsCode=07001&TeamCode=PB004"
                    " / インターパーク 키움: https://ticket.interpark.com/Contents/Sports/GoodsInfo?SportsCode=07001&TeamCode=PB003"
                    " / SSG: https://www.ssglanders.com/ticket/home"
                    " / 롯데: https://www.giantsclub.com/contents/ticket"
                    " / NC: https://ticket.ncdinos.com/"
                )
            else:
                away_note = "下記公式サイトで旅行期間の試合日程をご確認ください。"
            out.append(SportsMatch(
                league=lg,
                date=start.isoformat(),
                time=None,
                home_team="（自動取得に失敗 — 試合は開催されている可能性があります）",
                away_team=away_note,
                venue="",
                official_url=dated_url,
                status="fetch_failed",
            ))
        return out

    @staticmethod
    def _dated_schedule_url(league: str, base_url: str, dt: date) -> str:
        """Return schedule URL with the travel-start date pre-filled where possible."""
        if league == "kbo":
            return f"https://www.koreabaseball.com/Schedule/Schedule.aspx?leId=1&srId=0&date={dt.year}{dt.month:02d}{dt.day:02d}"
        if league == "kleague":
            return f"https://www.kleague.com/schedule.do?leagueId=1&year={dt.year}&month={dt.month:02d}"
        return base_url

    def _off_season_notices(
        self, leagues: list[str], start: date, end: date
    ) -> list[SportsMatch]:
        period = f"{start.isoformat()}〜{end.isoformat()}"
        out: list[SportsMatch] = []
        for lg in leagues:
            meta = _LEAGUE_META.get(lg, {})
            note = meta.get("off_season_note_ja", "公式サイトで日程をご確認ください。")
            out.append(
                SportsMatch(
                    league=lg,
                    date=start.isoformat(),
                    time=None,
                    home_team=f"（{period}の登録試合なし）",
                    away_team=note,
                    venue="",
                    official_url=meta.get("schedule_url", meta.get("official_url", "")),
                    status="off_season_notice",
                )
            )
        return out

    def _load_cache(
        self, start: date, end: date, leagues: list[str]
    ) -> list[SportsMatch]:
        if not CACHE_PATH.is_file():
            return []
        try:
            raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows = raw.get("matches") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return []
        out: list[SportsMatch] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            lg = str(row.get("league", "")).lower()
            if lg not in leagues:
                continue
            d = self._normalize_date(str(row.get("date", "")))
            if not d or not (start <= d <= end):
                continue
            meta = _LEAGUE_META.get(lg, {})
            out.append(
                SportsMatch(
                    league=lg,
                    date=d.isoformat(),
                    time=row.get("time"),
                    home_team=str(row.get("home_team", "")),
                    away_team=str(row.get("away_team", "")),
                    venue=str(row.get("venue", "")),
                    official_url=str(
                        row.get("official_url") or meta.get("official_url", "")
                    ),
                )
            )
        if out:
            logger.info("sports schedule from cache (%d)", len(out))
        return out

    @staticmethod
    def _normalize_date(raw: str) -> date | None:
        raw = raw.strip()
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(raw[:10], fmt).date()
            except ValueError:
                continue
        m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", raw)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
        return None

    @staticmethod
    def _normalize_time(raw: str) -> str | None:
        raw = raw.strip()
        m = re.search(r"(\d{1,2}):(\d{2})", raw)
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
        return None


def _profile_jeju_only(profile: dict | None) -> bool:
    if not profile:
        return False
    regions = [str(r).lower() for r in profile.get("regions") or []]
    return len(regions) == 1 and regions[0] == "jeiju"


def leagues_from_profile(profile: dict | None) -> list[str]:
    if not profile:
        return []
    sports: list[str] = list(profile.get("sports") or [])
    activities: list[str] = list(profile.get("activities") or [])
    if "sports" in activities and not sports:
        sports = ["sports"]
    seen: set[str] = set()
    out: list[str] = []
    for s in sports:
        for lg in _SPORT_TO_LEAGUES.get(s, []):
            if lg == "kbo" and _profile_jeju_only(profile):
                continue
            if lg not in seen:
                seen.add(lg)
                out.append(lg)
    return out


def _league_bucket(league: str) -> str:
    if league.startswith("kleague"):
        return "kleague"
    if league.startswith("kovo"):
        return "kovo"
    return league


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    earth_radius_km = 6371.0
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def accommodation_location_blob(profile: dict | None) -> str:
    """숙소·지역 텍스트를 소문자 한 덩어리로."""
    if not profile:
        return ""
    parts: list[str] = []
    accom = profile.get("accommodation") or {}
    for key in ("address", "detail", "name", "region"):
        val = accom.get(key)
        if val:
            parts.append(str(val))
    for src in (accom.get("selectedHotel") or {}, accom.get("selectedPlace") or {}):
        for key in ("address", "name", "formattedAddress"):
            val = src.get(key)
            if val:
                parts.append(str(val))
    cities = profile.get("regionCities") or profile.get("region_cities")
    if cities:
        parts.append(str(cities))
    for reg in profile.get("regions") or []:
        parts.append(str(reg))
    return " ".join(parts).lower()


def accommodation_center(profile: dict | None) -> tuple[float, float] | None:
    """숙소 좌표 → 주소·도시 키워드 → region 칩 순으로 중심 추정."""
    if not profile:
        return None
    accom = profile.get("accommodation") or {}
    for src in (accom, accom.get("selectedHotel") or {}, accom.get("selectedPlace") or {}):
        lat, lng = src.get("latitude"), src.get("longitude")
        if lat is None or lng is None:
            continue
        try:
            return float(lat), float(lng)
        except (TypeError, ValueError):
            continue

    blob = accommodation_location_blob(profile)
    for city in sorted(_CITY_CENTROIDS, key=len, reverse=True):
        if city in blob:
            return _CITY_CENTROIDS[city]

    for reg in profile.get("regions") or []:
        coords = _REGION_CHIP_CENTROIDS.get(str(reg).lower())
        if coords:
            return coords
    return None


def trip_sports_centers(profile: dict | None) -> list[tuple[tuple[float, float], float]]:
    """숙소 + 목적 지역 중심. 광역권은 더 넓은 반경으로 경기 추천."""
    if not profile:
        return []
    out: list[tuple[tuple[float, float], float]] = []
    seen: set[tuple[float, float]] = set()

    def add(coords: tuple[float, float] | None, radius: float) -> None:
        if not coords:
            return
        key = (round(coords[0], 4), round(coords[1], 4))
        if key in seen:
            return
        seen.add(key)
        out.append((coords, radius))

    add(accommodation_center(profile), NEARBY_SPORTS_MAX_KM)
    blob = accommodation_location_blob(profile)
    for city in sorted(_CITY_CENTROIDS, key=len, reverse=True):
        if city in blob:
            add(_CITY_CENTROIDS[city], 35.0)

    for reg in profile.get("regions") or []:
        key = str(reg).lower()
        add(_REGION_CHIP_CENTROIDS.get(key), 55.0)
        for coords in _REGION_CHIP_EXTRA_CENTERS.get(key, []):
            add(coords, 55.0)
    return out


def venue_center(match: SportsMatch) -> tuple[float, float] | None:
    """경기장명·홈팀 기준만 사용 (원정팀명의 도시 오인 방지)."""
    venue = (match.venue or "").strip()
    unknown_venues = {"", "会場未確認", "球場（要確認）"}
    if venue not in unknown_venues:
        text = venue.lower()
    else:
        text = f"{match.venue} {match.home_team}".lower()
    for keywords, lat, lng in _VENUE_COORDS:
        if any(kw.lower() in text for kw in keywords):
            return lat, lng
    for city in sorted(_CITY_CENTROIDS, key=len, reverse=True):
        if city in text:
            return _CITY_CENTROIDS[city]
    for team, coords in _KBO_HOME_COORDS.items():
        if team in (match.home_team or ""):
            return coords
    for team, coords in _KBL_HOME_COORDS.items():
        if team in (match.home_team or ""):
            return coords
    for team, coords in _KOVO_HOME_COORDS.items():
        if team in (match.home_team or ""):
            return coords
    return None


def _venue_near_accommodation_text(match: SportsMatch, accom_blob: str) -> bool:
    if not accom_blob:
        return False
    venue = (match.venue or "").strip()
    unknown_venues = {"", "会場未確認", "球場（要確認）"}
    vtext = (
        venue.lower()
        if venue not in unknown_venues
        else f"{match.venue} {match.home_team}".lower()
    )
    for city in sorted(_CITY_CENTROIDS, key=len, reverse=True):
        if city in accom_blob and city in vtext:
            return True
    return False


def filter_matches_near_accommodation(
    matches: list[SportsMatch],
    profile: dict | None,
    *,
    max_km: float = NEARBY_SPORTS_MAX_KM,
) -> list[SportsMatch]:
    """status=scheduled 중 숙소 근처 경기만 반환. 근처 없으면 빈 목록."""
    if not profile or not matches:
        return []
    scheduled = [m for m in matches if m.status == "scheduled"]
    if not scheduled:
        return []

    centers = trip_sports_centers(profile)
    blob = accommodation_location_blob(profile)
    if not centers and not blob.strip():
        return []

    out: list[SportsMatch] = []
    for m in scheduled:
        vc = venue_center(m)
        if centers and vc:
            if any(
                _haversine_km(c[0], c[1], vc[0], vc[1]) <= max(max_km, radius)
                for c, radius in centers
            ):
                out.append(m)
            continue
        if _venue_near_accommodation_text(m, blob):
            out.append(m)
    return out


def travel_dates_from_profile(profile: dict | None) -> tuple[date | None, date | None]:
    if not profile:
        return None, None
    flight = profile.get("flight") or {}
    depart = flight.get("depart") or flight.get("departure")
    ret = flight.get("returnDate") or flight.get("return")
    start = SportsScheduleClient._normalize_date(str(depart)) if depart else None
    end = SportsScheduleClient._normalize_date(str(ret)) if ret else None
    if start and not end and profile.get("nights"):
        try:
            nights = int(profile["nights"])
            end = start + timedelta(days=max(nights, 1))
        except (TypeError, ValueError):
            pass
    return start, end


_VENUE_PLACEHOLDER = frozenset(
    {"", "会場未確認", "球場（要確認）", "会場要確認", "会場未確認"}
)


# KBO·主要競技場の場内フード（定番・シーズンで変動 — 当日確認）
_STADIUM_FOOD_TIPS: dict[str, list[str]] = {
    "잠실": [
        "OB맥주·치킨(치맥) — 잠실 대표",
        "회오리감자",
        "소떡소떡",
        "빙수·아이스크림(여름)",
        "층별 매점(두산·LG 홈) 메뉴 상이",
    ],
    "잠실야구장": [
        "OB맥주·치킨(치맥)",
        "회오리감자·소떡소떡",
    ],
    "고척": [
        "피자·도시락(실내 좌석)",
        "치킨·맥주",
        "핫도그·감자튀김",
    ],
    "고척스카이돔": ["피자·도시락", "치킨·맥주", "회오리감자"],
    "사직": [
        "롯데리아(구장 내)",
        "어묵·핫도그",
        "돼지국밥 코너",
        "부산식 국밥·핫바",
    ],
    "사직야구장": ["롯데리아", "어묵·핫도그", "돼지국밥"],
    "광주": ["닭강정", "치킨·맥주", "기아 챔피언스 필드 매점"],
    "기아챔피언스필드": ["닭강정", "치킨·맥주", "감자류"],
    "대전": [
        "한화생명볼파크 — 치킨·맥주",
        "불맛 갈비(시즌 메뉴)",
        "회오리감자·핫도그",
    ],
    "한화생명볼파크": ["치킨·맥주", "불맛 갈비", "회오리감자"],
    "수원": [
        "삼겹살 버거(KT 위즈 파크 대표)",
        "치킨·맥주",
        "소떡소떡",
    ],
    "kt위즈파크": ["삼겹살 버거", "치킨·맥주"],
    "문학": [
        "크림새우 — 1루 2층 응원석(으쓱이존) 방면 / 외야 바비큐존 뒤편 스테이션 매장",
        "버거 원더스 치즈 푸틴 — 1루 1층 응원석(으쓱이존) 근처",
        "커빙 빙수 — 1루 2층 파울 폴대 근처, 스타벅스 옆",
        "스타벅스 랜더스필드점 — 1루 2층 복도 쪽 등 구장 내 매장",
        "스트릿 츄러스 — 1루 외야 바비큐존 뒤",
        "요기요/SSG 공식앱 픽업 주문 — 일부 매장 제한 가능",
    ],
    "문학야구장": [
        "크림새우 — 1루 2층 응원석 / 외야 바비큐존 뒤편",
        "버거 원더스 치즈 푸틴 — 1루 1층",
        "스트릿 츄러스 — 1루 외야 바비큐존 뒤",
    ],
    "인천": ["크림새우", "버거 원더스 치즈 푸틴", "스트릿 츄러스"],
    "창원": [
        "NC파크 — 마산식 찹쌀순대",
        "회·핫도그",
        "치킨·맥주",
    ],
    "nc파크": ["찹쌀순대", "회·핫도그"],
    "대구": [
        "삼성 라이온즈 파크 — 치킨·맥주",
        "떡볶이·소떡",
        "라이온즈 맥주 홀",
    ],
    "라이온즈파크": ["치킨·맥주", "떡볶이·소떡"],
    "울산": ["치킨·맥주", "핫도그", "울산 문수 야구장 매점"],
    "문수": ["치킨·맥주", "핫도그"],
    "청주": [
        "OB맥주",
        "치킨·소떡",
        "한화 육장어구이(대표 이벤트 메뉴)",
    ],
    "청주야구장": ["OB맥주", "치킨", "육장어구이"],
    # Kリーグ・サッカー場（代表例）
    "서울월드컵": [
        "푸드트럭·간편식 — 북측광장/주요 게이트 주변 운영 변동",
        "떡볶이·핫도그·닭강정",
        "편의점·카페 — 월드컵경기장몰/메가박스 방면",
    ],
    "상암": ["푸드트럭·간편식", "월드컵경기장몰 편의점·카페"],
    "월드컵경기장": ["푸드트럭·간편식", "떡볶이·핫도그", "편의점·카페"],
    "전주월드컵": [
        "푸드트럭존 — 경기일 운영 변동",
        "치킨·핫도그·분식류",
        "경기장 외부 매점·편의점 이용",
    ],
    "대전월드컵": ["푸드트럭·분식", "치킨·핫도그", "월드컵경기장역 주변 편의점"],
    "수원월드컵": ["푸드트럭·분식", "치킨·핫도그", "빅버드 주변 편의점"],
    "탄천종합": ["푸드트럭·간편식", "분식·핫도그", "야탑역 방면 식당가 이용"],
    "용인미르": ["푸드트럭·간편식", "핫도그·분식", "경기일 매점 운영 확인"],
    "천안종합": ["푸드트럭·간편식", "핫도그·분식", "천안종합운동장 주변 편의점"],
    "이순신종합": ["푸드트럭·간편식", "분식·음료", "경기일 매점 운영 확인"],
    "아산": ["푸드트럭·간편식", "분식·음료"],
    "김포솔터": ["푸드트럭·간편식", "핫도그·분식", "솔터체육공원 주변 편의점"],
    "파주": ["푸드트럭·간편식", "분식·음료", "경기일 매점 운영 확인"],
    "김해": ["푸드트럭·간편식", "분식·음료", "경기장 주변 편의점"],
    "제주월드컵": ["푸드트럭·간편식", "감귤 음료·분식류", "월드컵경기장 주변 카페"],
    "문학경기장": ["어묵·핫도그", "치킨", "경기일 푸드트럭 운영 확인"],
    # KBL・バスケ会場
    "잠실실내체육관": [
        "잠실종합운동장 매점 — 음료·스낵·핫도그",
        "치킨·버거류는 경기일 입점/운영 확인",
        "종합운동장역 주변 편의점·카페",
    ],
    "사직실내체육관": ["실내체육관 매점 — 음료·스낵", "사직야구장/종합운동장 주변 분식", "사직역 주변 식당가"],
    "대구실내체육관": ["실내체육관 매점 — 음료·스낵", "북구 산격동 주변 분식·치킨", "경기일 매점 운영 확인"],
    "삼산체육관": ["삼산월드체육관 매점 — 음료·스낵", "삼산체육관역 주변 카페·분식", "경기일 푸드부스 확인"],
    "인천삼산": ["삼산월드체육관 매점", "삼산체육관역 주변 카페·분식"],
    "안양실내체육관": ["실내체육관 매점 — 음료·스낵", "범계역·평촌 주변 식당가", "경기일 푸드부스 확인"],
    "동천체육관": ["체육관 매점 — 음료·스낵", "울산 동천체육관 주변 분식·치킨", "경기일 운영 확인"],
    "창원실내체육관": ["체육관 매점 — 음료·스낵", "창원스포츠파크 주변 분식·치킨", "경기일 푸드부스 확인"],
    "수원kt소닉붐": ["수원 KT 소닉붐 아레나 매점", "분식·핫도그·음료", "수원종합운동장 주변 식당가"],
    "원주종합체육관": ["종합체육관 매점 — 음료·스낵", "원주종합운동장 주변 분식", "경기일 운영 확인"],
    # KOVO・バレー会場
    "장충체육관": ["장충체육관 매점 — 음료·스낵", "동대입구역·장충동 족발거리 주변 식사", "경기일 푸드부스 확인"],
    "의정부실내체육관": ["체육관 매점 — 음료·스낵", "의정부종합운동장 주변 분식", "경기일 운영 확인"],
    "천안유관순": ["유관순체육관 매점 — 음료·스낵", "천안종합운동장 주변 분식", "경기일 푸드부스 확인"],
    "인천삼산월드체육관": ["삼산월드체육관 매점 — 음료·스낵", "삼산체육관역 주변 카페·분식"],
    "광주페퍼": ["페퍼스타디움 매점 — 음료·스낵", "염주종합체육관 주변 분식·카페", "경기일 운영 확인"],
    "염주": ["체육관 매점 — 음료·스낵", "염주체육관 주변 분식·카페"],
    "충무체육관": ["충무체육관 매점 — 음료·스낵", "대전 한밭종합운동장 주변 분식", "경기일 운영 확인"],
    "수원실내": ["수원실내체육관 매점 — 음료·스낵", "수원종합운동장 주변 분식·치킨"],
    "안산상록수": ["상록수체육관 매점 — 음료·스낵", "상록수역 주변 분식·카페", "경기일 운영 확인"],
}

_HOME_TEAM_STADIUM_FOOD: dict[str, list[str]] = {
    "LG": _STADIUM_FOOD_TIPS["잠실"],
    "두산": _STADIUM_FOOD_TIPS["잠실"],
    "키움": _STADIUM_FOOD_TIPS["고척"],
    "롯데": _STADIUM_FOOD_TIPS["사직"],
    "기아": _STADIUM_FOOD_TIPS["광주"],
    "한화": _STADIUM_FOOD_TIPS["대전"],
    "KT": _STADIUM_FOOD_TIPS["수원"],
    "SSG": _STADIUM_FOOD_TIPS["문학"],
    "랜더스": _STADIUM_FOOD_TIPS["문학"],
    "NC": _STADIUM_FOOD_TIPS["창원"],
    "삼성": _STADIUM_FOOD_TIPS["대구"],
    "KIA": _STADIUM_FOOD_TIPS["광주"],
    # Kリーグ
    "FC서울": _STADIUM_FOOD_TIPS["서울월드컵"],
    "서울": _STADIUM_FOOD_TIPS["서울월드컵"],
    "전북": _STADIUM_FOOD_TIPS["전주월드컵"],
    "대전": _STADIUM_FOOD_TIPS["대전월드컵"],
    "수원FC": _STADIUM_FOOD_TIPS["수원월드컵"],
    "수원": _STADIUM_FOOD_TIPS["수원월드컵"],
    "성남": _STADIUM_FOOD_TIPS["탄천종합"],
    "용인": _STADIUM_FOOD_TIPS["용인미르"],
    "천안": _STADIUM_FOOD_TIPS["천안종합"],
    "아산": _STADIUM_FOOD_TIPS["아산"],
    "김포": _STADIUM_FOOD_TIPS["김포솔터"],
    "파주": _STADIUM_FOOD_TIPS["파주"],
    "김해": _STADIUM_FOOD_TIPS["김해"],
    "제주": _STADIUM_FOOD_TIPS["제주월드컵"],
    # KBL
    "서울 SK": _STADIUM_FOOD_TIPS["잠실실내체육관"],
    "SK나이츠": _STADIUM_FOOD_TIPS["잠실실내체육관"],
    "서울 삼성": _STADIUM_FOOD_TIPS["잠실실내체육관"],
    "삼성썬더스": _STADIUM_FOOD_TIPS["잠실실내체육관"],
    "부산 KCC": _STADIUM_FOOD_TIPS["사직실내체육관"],
    "KCC": _STADIUM_FOOD_TIPS["사직실내체육관"],
    "한국가스공사": _STADIUM_FOOD_TIPS["대구실내체육관"],
    "페가수스": _STADIUM_FOOD_TIPS["대구실내체육관"],
    "전자랜드": _STADIUM_FOOD_TIPS["삼산체육관"],
    "정관장": _STADIUM_FOOD_TIPS["안양실내체육관"],
    "현대모비스": _STADIUM_FOOD_TIPS["동천체육관"],
    "창원 LG": _STADIUM_FOOD_TIPS["창원실내체육관"],
    "LG세이커스": _STADIUM_FOOD_TIPS["창원실내체육관"],
    "수원 KT": _STADIUM_FOOD_TIPS["수원kt소닉붐"],
    "KT소닉붐": _STADIUM_FOOD_TIPS["수원kt소닉붐"],
    "원주 DB": _STADIUM_FOOD_TIPS["원주종합체육관"],
    "DB프로미": _STADIUM_FOOD_TIPS["원주종합체육관"],
    # KOVO
    "GS칼텍스": _STADIUM_FOOD_TIPS["장충체육관"],
    "우리카드": _STADIUM_FOOD_TIPS["장충체육관"],
    "IBK기업은행": _STADIUM_FOOD_TIPS["의정부실내체육관"],
    "현대캐피탈": _STADIUM_FOOD_TIPS["천안유관순"],
    "대한항공": _STADIUM_FOOD_TIPS["인천삼산월드체육관"],
    "흥국생명": _STADIUM_FOOD_TIPS["인천삼산월드체육관"],
    "페퍼저축은행": _STADIUM_FOOD_TIPS["광주페퍼"],
    "AI페퍼스": _STADIUM_FOOD_TIPS["광주페퍼"],
    "삼성화재": _STADIUM_FOOD_TIPS["충무체육관"],
    "KGC인삼공사": _STADIUM_FOOD_TIPS["충무체육관"],
    "정관장 레드스파크스": _STADIUM_FOOD_TIPS["충무체육관"],
    "한국전력": _STADIUM_FOOD_TIPS["수원실내"],
    "현대건설": _STADIUM_FOOD_TIPS["수원실내"],
    "OK금융그룹": _STADIUM_FOOD_TIPS["안산상록수"],
}


_STADIUM_FOOD_BAD_WORDS = (
    "구내식당", "사내식당", "직원식당", "급식", "단체급식",
    "社員食堂", "職員食堂", "給食", "canteen", "cafeteria",
)


def _is_bad_stadium_food_text(text: str) -> bool:
    t = (text or "").lower()
    return any(word.lower() in t for word in _STADIUM_FOOD_BAD_WORDS)


def lookup_stadium_food_tips(venue: str, home_team: str = "") -> list[str]:
    """경기장명·홈팀으로 정적 매점 메뉴 힌트."""
    v = (venue or "").strip().lower().replace(" ", "")
    if v:
        for key, tips in _STADIUM_FOOD_TIPS.items():
            if key.replace(" ", "") in v or v in key.replace(" ", ""):
                return list(tips)
    ht = (home_team or "").strip()
    if ht:
        for key, tips in sorted(
            _HOME_TEAM_STADIUM_FOOD.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if ht.startswith(key) or key in ht:
                return list(tips)
    return []


def iter_scheduled_match_venues(
    matches: list[SportsMatch],
    *,
    max_venues: int = 4,
) -> list[tuple[str, str, str]]:
    """실제 일정 경기의 (venue, league, home_team) — 경기장 내부 먹거리용."""
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for m in matches:
        if m.status in ("off_season_notice", "fetch_failed"):
            continue
        venue = (m.venue or "").strip()
        if venue in _VENUE_PLACEHOLDER:
            venue = f"{m.home_team} 홈구장".strip() if m.home_team else ""
        if not venue:
            continue
        key = venue.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((venue, m.league, m.home_team or ""))
        if len(out) >= max_venues:
            break
    return out


def build_stadium_food_search_queries(
    venue: str,
    league: str = "",
    lang: str = "ja",
) -> list[str]:
    """경기장당 복수 검색 쿼리（웹検索ヒット率向上）."""
    venue = venue.strip()
    league = (league or "").lower()
    qs: list[str] = [build_stadium_food_search_query(venue, league, lang)]
    if league == "kbo":
        qs.append(f"{venue} 야구장 먹거리 매점 추천")
        qs.append(f"{venue} 매점 위치 구역 층 먹거리")
        qs.append(f"{venue} KBO 球場 グルメ")
    elif league.startswith("kleague"):
        qs.append(f"{venue} 축구장 먹거리")
        qs.append(f"{venue} 매점 위치 구역")
        qs.append(f"{venue} サッカー スタジアム グルメ")
    else:
        qs.append(f"{venue} 경기장 먹거리 매점")
        qs.append(f"{venue} 매점 위치")
    seen: set[str] = set()
    out: list[str] = []
    for q in qs:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:4]


def build_stadium_food_search_query(
    venue: str,
    league: str = "",
    lang: str = "ja",
) -> str:
    """경기장 내 매점·먹거리 — DuckDuckGo 검색 쿼리."""
    venue = venue.strip()
    league = (league or "").lower()
    if lang == "ja":
        if league.startswith("kleague"):
            sport = "サッカー"
        elif league == "kbo":
            sport = "野球"
        elif league == "kbl":
            sport = "バスケ"
        elif "kovo" in league:
            sport = "バレー"
        else:
            sport = "スポーツ"
        return f"{venue} {sport} 球場 グルメ フード 売店 おすすめ"
    return f"{venue} 경기장 먹거리 매점 음식 추천"


def fmt_stadium_food_context(
    venues: list[tuple[str, str, str]],
    web_by_venue: dict[str, list],
    *,
    lang: str = "ja",
) -> str:
    """정적 매점 힌트 + 웹검색 스니펫 — LLM Reference Data."""
    if not venues:
        return ""
    lines: list[str] = [
        "※ 以下の【代表メニュー】と【ウェブ検索】のみ観戦ブロックに使うこと。",
        "※ 「チキン・ホットドッグ・トッポッキ」の一般羅列だけは禁止（下記の具体名を列挙）。",
        "※ 구내식당・社員食堂・給食・canteen/cafeteria は観光客向けではないため絶対に書かない。",
        "※ 位置・ゲート・階・内野/外野などがウェブ検索に出た場合のみ、売店位置メモとして併記。無ければ位置を創作しない。",
        "※ 価格・品切れ・メニュー変更は当日・公式で要確認。",
    ]
    for venue, league, home_team in venues:
        tips = lookup_stadium_food_tips(venue, home_team)
        web_results = web_by_venue.get(venue) or []
        lines.append(f"\n■ {venue}")
        if tips:
            label = "代表メニュー（スタジアム定番）" if lang == "ja" else "대표 메뉴"
            lines.append(f"【{label}】")
            for t in tips:
                lines.append(f"  - {t}")
        if web_results:
            lines.append("【ウェブ検索メモ（売店位置・メニュー候補）】")
            for i, r in enumerate(web_results, 1):
                title = getattr(r, "title", "") or ""
                snippet = getattr(r, "snippet", "") or ""
                url = getattr(r, "url", "") or ""
                if _is_bad_stadium_food_text(f"{title} {snippet} {url}"):
                    continue
                if title:
                    lines.append(f"  [{i}] {title}")
                if snippet:
                    lines.append(f"      {snippet[:280]}")
                if url:
                    lines.append(f"      {url}")
        if not tips and not web_results:
            lines.append("  （場内メニュー情報なし — 創作せず「当日売店で確認」のみ）")
    return "\n".join(lines)


def fmt_sports_matches(matches: list[SportsMatch], lang: str = "ja") -> str:
    if not matches:
        return (
            "(該当期間の試合データなし — 試合観戦ブロックは作らない)"
        )
    lines: list[str] = []
    for i, m in enumerate(matches, 1):
        if m.status in ("off_season_notice", "fetch_failed"):
            meta = _LEAGUE_META.get(m.league, {})
            label = meta.get("label_ja", m.league.upper())
            if m.status == "fetch_failed":
                lines.append(
                    f"[{i}] {label} | ⚠ {m.home_team}\n"
                    f"    {m.away_team}\n"
                    "    試合日程: 取得不可"
                )
            else:
                lines.append(
                    f"[{i}] {label} | {m.home_team}\n"
                    f"    → {m.away_team}\n"
                    "    試合日程: シーズン外"
                )
            continue
        meta = _LEAGUE_META.get(m.league, _LEAGUE_META.get(_league_bucket(m.league), {}))
        label = meta.get("label_ja", m.league.upper())
        if m.league == "kovo_w":
            label = "KOVO（女子Vリーグ）"
        time_str = f" {m.time}" if m.time else ""
        teams = f"{m.home_team} vs {m.away_team}".strip(" vs ")
        venue = m.venue or "会場要確認"
        lines.append(
            f"[{i}] {label} | {m.date}{time_str} | {teams} | {venue}\n"
            f"    チケット・観戦情報: {m.ticket_url or '会場・球団公式で確認'}"
        )
    return "\n".join(lines)
