"""Filter hotel Places results to match wizard 시·도 / 시·군·구 selection."""

from __future__ import annotations

import re
from typing import Iterable

# 광역 시·도 — 주소에 포함되어야 할 토큰 (한글·로마자)
_SIDO_POSITIVE: dict[str, tuple[str, ...]] = {
    "서울특별시": ("서울", "Seoul", "서울특별시"),
    "부산광역시": ("부산", "Busan", "부산광역시"),
    "대구광역시": ("대구", "Daegu", "대구광역시"),
    "인천광역시": ("인천", "Incheon", "인천광역시"),
    "광주광역시": ("광주", "Gwangju", "광주광역시"),
    "대전광역시": ("대전", "Daejeon", "대전광역시"),
    "울산광역시": ("울산", "Ulsan", "울산광역시"),
    "세종특별자치시": ("세종", "Sejong", "세종특별자치시"),
    "경기도": ("경기", "Gyeonggi", "경기도"),
    "강원특별자치도": ("강원", "Gangwon", "강원특별자치도", "강원도"),
    "충청북도": ("충북", "충청북", "Chungcheongbuk", "충청북도"),
    "충청남도": ("충남", "충청남", "Chungcheongnam", "충청남도"),
    "전북특별자치도": ("전북", "전라북", "Jeonbuk", "전북특별자치도"),
    "전라남도": ("전남", "전라남", "Jeonnam", "전라남도"),
    "경상북도": ("경북", "경상북", "Gyeongsangbuk", "경상북도"),
    "경상남도": ("경남", "경상남", "Gyeongsangnam", "경상남도"),
    "제주특별자치도": ("제주", "Jeju", "제주특별자치도", "제주도"),
}

# 선택 광역과 다른 광역 토큰이 단독으로 있으면 제외 (서울 검색 시 인천만 있는 주소 등)
_SIDO_CROSS_EXCLUDE: dict[str, tuple[str, ...]] = {
    "서울특별시": (
        "인천",
        "Incheon",
        "부산",
        "Busan",
        "대구",
        "Daegu",
        "광주",
        "Gwangju",
        "대전",
        "Daejeon",
        "울산",
        "Ulsan",
        "제주",
        "Jeju",
    ),
    "인천광역시": ("부산", "Busan", "대구", "Daegu", "제주", "Jeju"),
    "부산광역시": ("인천", "Incheon", "서울", "Seoul"),
    "대구광역시": ("인천", "Incheon", "서울", "Seoul"),
    "광주광역시": ("인천", "Incheon", "서울", "Seoul"),
    "대전광역시": ("인천", "Incheon", "서울", "Seoul"),
    "울산광역시": ("인천", "Incheon", "서울", "Seoul"),
}

# "○○시 △△구" 복합 선택 시 시·도 내 시(市) 영문 — 구 힌트와 AND 로 매칭
_CITY_SI_EN_HINTS: dict[str, tuple[str, ...]] = {
    "고양시": ("goyang-si", "goyang city", "goyang"),
    "성남시": ("seongnam-si", "seongnam city", "seongnam"),
    "수원시": ("suwon-si", "suwon city", "suwon"),
    "안산시": ("ansan-si", "ansan city", "ansan"),
    "안양시": ("anyang-si", "anyang city", "anyang"),
    "용인시": ("yongin-si", "yongin city", "yongin"),
    "청주시": ("cheongju-si", "cheongju city", "cheongju"),
    "천안시": ("cheonan-si", "cheonan city", "cheonan"),
    "전주시": ("jeonju-si", "jeonju city", "jeonju"),
    "포항시": ("pohang-si", "pohang city", "pohang"),
    "창원시": ("changwon-si", "changwon city", "changwon", "masan", "jinhae"),
}

# Places 주소가 영문·로마자만인 경우 보조 (wizard ADDR_DATA 시·군·구 전체, 226개)
# 갱신: python scripts/generate_sigungu_en_hints.py 후 hotel_area_filter.py 블록 교체
_SIGUNGU_EN_HINTS: dict[str, tuple[str, ...]] = {
    "남구": ('nam-gu', 'nam district'),
    "동구": ('dong-gu', 'dong district'),
    "북구": ('buk-gu', 'buk district'),
    "서구": ('seo-gu', 'seo district'),
    "중구": ('jung-gu', 'jung district'),
    "강남구": ('gangnam-gu', 'gangnam district', 'gangnam'),
    "강동구": ('gangdong-gu', 'gangdong district', 'gangdong'),
    "강릉시": ('gangneung-si', 'gangneung city', 'gangneung'),
    "강북구": ('gangbuk-gu', 'gangbuk district', 'gangbuk'),
    "강서구": ('gangseo-gu', 'gangseo district', 'gangseo'),
    "강진군": ('gangjin-gun', 'gangjin district', 'gangjin'),
    "강화군": ('ganghwa-gun', 'ganghwa district', 'ganghwa'),
    "거제시": ('geoje-si', 'geoje city', 'geoje'),
    "거창군": ('geochang-gun', 'geochang district', 'geochang'),
    "경산시": ('gyeongsan-si', 'gyeongsan city', 'gyeongsan'),
    "경주시": ('gyeongju-si', 'gyeongju city', 'gyeongju'),
    "계룡시": ('gyeryong-si', 'gyeryong city', 'gyeryong'),
    "계양구": ('gyeyang-gu', 'gyeyang district', 'gyeyang'),
    "고령군": ('goryeong-gun', 'goryeong district', 'goryeong'),
    "고성군": ('goseong-gun', 'goseong district', 'goseong'),
    "고창군": ('gochang-gun', 'gochang district', 'gochang'),
    "고흥군": ('goheung-gun', 'goheung district', 'goheung'),
    "곡성군": ('gokseong-gun', 'gokseong district', 'gokseong'),
    "공주시": ('gongju-si', 'gongju city', 'gongju'),
    "과천시": ('gwacheon-si', 'gwacheon city', 'gwacheon'),
    "관악구": ('gwanak-gu', 'gwanak district', 'gwanak'),
    "광명시": ('gwangmyeong-si', 'gwangmyeong city', 'gwangmyeong'),
    "광산구": ('gwangsan-gu', 'gwangsan district', 'gwangsan'),
    "광양시": ('gwangyang-si', 'gwangyang city', 'gwangyang'),
    "광주시": ('gwangju-si', 'gwangju city', 'gwangju'),
    "광진구": ('gwangjin-gu', 'gwangjin district', 'gwangjin'),
    "괴산군": ('goesan-gun', 'goesan district', 'goesan'),
    "구례군": ('gurye-gun', 'gurye district', 'gurye'),
    "구로구": ('guro-gu', 'guro district', 'guro'),
    "구리시": ('guri-si', 'guri city', 'guri'),
    "구미시": ('gumi-si', 'gumi city', 'gumi'),
    "군산시": ('gunsan-si', 'gunsan city', 'gunsan'),
    "군포시": ('gunpo-si', 'gunpo city', 'gunpo'),
    "금산군": ('geumsan-gun', 'geumsan district', 'geumsan'),
    "금정구": ('geumjeong-gu', 'geumjeong district', 'geumjeong'),
    "금천구": ('geumcheon-gu', 'geumcheon district', 'geumcheon'),
    "기장군": ('gijang-gun', 'gijang-eup', 'gijang-gu', 'gijang'),
    "김제시": ('gimje-si', 'gimje city', 'gimje'),
    "김천시": ('gimcheon-si', 'gimcheon city', 'gimcheon'),
    "김포시": ('gimpo-si', 'gimpo city', 'gimpo'),
    "김해시": ('gimhae-si', 'gimhae city', 'gimhae'),
    "나주시": ('naju-si', 'naju city', 'naju'),
    "남동구": ('namdong-gu', 'namdong district', 'namdong'),
    "남원시": ('namwon-si', 'namwon city', 'namwon'),
    "남해군": ('namhae-gun', 'namhae district', 'namhae'),
    "노원구": ('nowon-gu', 'nowon district', 'nowon'),
    "논산시": ('nonsan-si', 'nonsan city', 'nonsan'),
    "단양군": ('danyang-gun', 'danyang district', 'danyang'),
    "달서구": ('dalseo-gu', 'dalseo district', 'dalseo'),
    "달성군": ('dalseong-gun', 'dalseong district', 'dalseong'),
    "담양군": ('damyang-gun', 'damyang district', 'damyang'),
    "당진시": ('dangjin-si', 'dangjin city', 'dangjin'),
    "대덕구": ('daedeok-gu', 'daedeok district', 'daedeok'),
    "도봉구": ('dobong-gu', 'dobong district', 'dobong'),
    "동래구": ('dongnae-gu', 'dongnae district', 'dongnae'),
    "동작구": ('dongjak-gu', 'dongjak district', 'dongjak'),
    "동해시": ('donghae-si', 'donghae city', 'donghae'),
    "마포구": ('mapo-gu', 'mapo district', 'mapo'),
    "목포시": ('mokpo-si', 'mokpo city', 'mokpo'),
    "무안군": ('muan-gun', 'muan district', 'muan'),
    "무주군": ('muju-gun', 'muju district', 'muju'),
    "문경시": ('mungyeong-si', 'mungyeong city', 'mungyeong'),
    "밀양시": ('miryang-si', 'miryang city', 'miryang'),
    "보령시": ('boryeong-si', 'boryeong city', 'boryeong'),
    "보성군": ('boseong-gun', 'boseong district', 'boseong'),
    "보은군": ('boeun-gun', 'boeun district', 'boeun'),
    "봉화군": ('bonghwa-gun', 'bonghwa district', 'bonghwa'),
    "부안군": ('buan-gun', 'buan district', 'buan'),
    "부여군": ('buyeo-gun', 'buyeo district', 'buyeo'),
    "부천시": ('bucheon-si', 'bucheon city', 'bucheon'),
    "부평구": ('bupyeong-gu', 'bupyeong district', 'bupyeong'),
    "사상구": ('sasang-gu', 'sasang district', 'sasang'),
    "사천시": ('sacheon-si', 'sacheon city', 'sacheon'),
    "사하구": ('saha-gu', 'saha district', 'saha'),
    "산청군": ('sancheong-gun', 'sancheong district', 'sancheong'),
    "삼척시": ('samcheok-si', 'samcheok city', 'samcheok'),
    "상주시": ('sangju-si', 'sangju city', 'sangju'),
    "서산시": ('seosan-si', 'seosan city', 'seosan'),
    "서천군": ('seocheon-gun', 'seocheon district', 'seocheon'),
    "서초구": ('seocho-gu', 'seocho district', 'seocho'),
    "성동구": ('seongdong-gu', 'seongdong district', 'seongdong'),
    "성북구": ('seongbuk-gu', 'seongbuk district', 'seongbuk'),
    "성주군": ('seongju-gun', 'seongju district', 'seongju'),
    "세종시": ('sejong-si', 'sejong city', 'sejong'),
    "속초시": ('sokcho-si', 'sokcho city', 'sokcho'),
    "송파구": ('songpa-gu', 'songpa district', 'songpa'),
    "수성구": ('suseong-gu', 'suseong district', 'suseong'),
    "수영구": ('suyeong-gu', 'suyeong district', 'suyeong'),
    "순창군": ('sunchang-gun', 'sunchang district', 'sunchang'),
    "순천시": ('suncheon-si', 'suncheon city', 'suncheon'),
    "시흥시": ('siheung-si', 'siheung city', 'siheung'),
    "신안군": ('sinan-gun', 'sinan district', 'sinan'),
    "아산시": ('asan-si', 'asan city', 'asan'),
    "안동시": ('andong-si', 'andong city', 'andong'),
    "안성시": ('anseong-si', 'anseong city', 'anseong'),
    "양구군": ('yanggu-gun', 'yanggu district', 'yanggu'),
    "양산시": ('yangsan-si', 'yangsan city', 'yangsan'),
    "양양군": ('yangyang-gun', 'yangyang district', 'yangyang'),
    "양주시": ('yangju-si', 'yangju city', 'yangju'),
    "양천구": ('yangcheon-gu', 'yangcheon district', 'yangcheon'),
    "양평군": ('yangpyeong-gun', 'yangpyeong district', 'yangpyeong'),
    "여수시": ('yeosu-si', 'yeosu city', 'yeosu'),
    "여주시": ('yeoju-si', 'yeoju city', 'yeoju'),
    "연수구": ('yeonsu-gu', 'yeonsu district', 'yeonsu'),
    "연제구": ('yeonje-gu', 'yeonje district', 'yeonje'),
    "연천군": ('yeoncheon-gun', 'yeoncheon district', 'yeoncheon'),
    "영광군": ('yeonggwang-gun', 'yeonggwang district', 'yeonggwang'),
    "영덕군": ('yeongdeok-gun', 'yeongdeok district', 'yeongdeok'),
    "영도구": ('yeongdo-gu', 'yeongdo district', 'yeongdo'),
    "영동군": ('yeongdong-gun', 'yeongdong district', 'yeongdong'),
    "영암군": ('yeongam-gun', 'yeongam district', 'yeongam'),
    "영양군": ('yeongyang-gun', 'yeongyang district', 'yeongyang'),
    "영월군": ('yeongwol-gun', 'yeongwol district', 'yeongwol'),
    "영주시": ('yeongju-si', 'yeongju city', 'yeongju'),
    "영천시": ('yeongcheon-si', 'yeongcheon city', 'yeongcheon'),
    "예산군": ('yesan-gun', 'yesan district', 'yesan'),
    "예천군": ('yecheon-gun', 'yecheon district', 'yecheon'),
    "오산시": ('osan-si', 'osan city', 'osan'),
    "옥천군": ('okcheon-gun', 'okcheon district', 'okcheon'),
    "옹진군": ('ongjin-gun', 'ongjin district', 'ongjin'),
    "완도군": ('wando-gun', 'wando district', 'wando'),
    "완주군": ('wanju-gun', 'wanju district', 'wanju'),
    "용산구": ('yongsan-gu', 'yongsan district', 'yongsan'),
    "울릉군": ('ulleung-gun', 'ulleung district', 'ulleung'),
    "울주군": ('ulju-gun', 'ulju district', 'ulju'),
    "울진군": ('uljin-gun', 'uljin district', 'uljin'),
    "원주시": ('wonju-si', 'wonju city', 'wonju'),
    "유성구": ('yuseong-gu', 'yuseong district', 'yuseong'),
    "은평구": ('eunpyeong-gu', 'eunpyeong district', 'eunpyeong'),
    "음성군": ('eumseong-gun', 'eumseong district', 'eumseong'),
    "의령군": ('uiryeong-gun', 'uiryeong district', 'uiryeong'),
    "의성군": ('uiseong-gun', 'uiseong district', 'uiseong'),
    "의왕시": ('uiwang-si', 'uiwang city', 'uiwang'),
    "이천시": ('icheon-si', 'icheon city', 'icheon'),
    "익산시": ('iksan-si', 'iksan city', 'iksan'),
    "인제군": ('inje-gun', 'inje district', 'inje'),
    "임실군": ('imsil-gun', 'imsil district', 'imsil'),
    "장성군": ('jangseong-gun', 'jangseong district', 'jangseong'),
    "장수군": ('jangsu-gun', 'jangsu district', 'jangsu'),
    "장흥군": ('jangheung-gun', 'jangheung district', 'jangheung'),
    "정선군": ('jeongseon-gun', 'jeongseon district', 'jeongseon'),
    "정읍시": ('jeongeup-si', 'jeongeup city', 'jeongeup'),
    "제주시": ('jeju-si', 'jeju city', 'jeju'),
    "제천시": ('jecheon-si', 'jecheon city', 'jecheon'),
    "종로구": ('jongno-gu', 'jongno district', 'jongno', 'jong-ro'),
    "중랑구": ('jungnang-gu', 'jungnang district', 'jungnang'),
    "증평군": ('jeungpyeong-gun', 'jeungpyeong district', 'jeungpyeong'),
    "진도군": ('jindo-gun', 'jindo district', 'jindo'),
    "진안군": ('jinan-gun', 'jinan district', 'jinan'),
    "진주시": ('jinju-si', 'jinju city', 'jinju'),
    "진천군": ('jincheon-gun', 'jincheon district', 'jincheon'),
    "창녕군": ('changnyeong-gun', 'changnyeong district', 'changnyeong'),
    "철원군": ('cheorwon-gun', 'cheorwon district', 'cheorwon'),
    "청도군": ('cheongdo-gun', 'cheongdo district', 'cheongdo'),
    "청송군": ('cheongsong-gun', 'cheongsong district', 'cheongsong'),
    "청양군": ('cheongyang-gun', 'cheongyang district', 'cheongyang'),
    "춘천시": ('chuncheon-si', 'chuncheon city', 'chuncheon'),
    "충주시": ('chungju-si', 'chungju city', 'chungju'),
    "칠곡군": ('chilgok-gun', 'chilgok district', 'chilgok'),
    "태백시": ('taebaek-si', 'taebaek city', 'taebaek'),
    "태안군": ('taean-gun', 'taean district', 'taean'),
    "통영시": ('tongyeong-si', 'tongyeong city', 'tongyeong'),
    "파주시": ('paju-si', 'paju city', 'paju'),
    "평창군": ('pyeongchang-gun', 'pyeongchang district', 'pyeongchang'),
    "평택시": ('pyeongtaek-si', 'pyeongtaek city', 'pyeongtaek'),
    "포천시": ('pocheon-si', 'pocheon city', 'pocheon'),
    "하남시": ('hanam-si', 'hanam city', 'hanam'),
    "하동군": ('hadong-gun', 'hadong district', 'hadong'),
    "함안군": ('haman-gun', 'haman district', 'haman'),
    "함양군": ('hamyang-gun', 'hamyang district', 'hamyang'),
    "함평군": ('hampyeong-gun', 'hampyeong district', 'hampyeong'),
    "합천군": ('hapcheon-gun', 'hapcheon district', 'hapcheon'),
    "해남군": ('haenam-gun', 'haenam district', 'haenam'),
    "홍성군": ('hongseong-gun', 'hongseong district', 'hongseong'),
    "홍천군": ('hongcheon-gun', 'hongcheon district', 'hongcheon'),
    "화성시": ('hwaseong-si', 'hwaseong city', 'hwaseong'),
    "화순군": ('hwasun-gun', 'hwasun district', 'hwasun'),
    "화천군": ('hwacheon-gun', 'hwacheon district', 'hwacheon'),
    "횡성군": ('hoengseong-gun', 'hoengseong district', 'hoengseong'),
    "남양주시": ('namyangju-si', 'namyangju city', 'namyangju'),
    "동대문구": ('dongdaemun-gu', 'dongdaemun district', 'dongdaemun'),
    "동두천시": ('dongducheon-si', 'dongducheon city', 'dongducheon'),
    "미추홀구": ('michuhol-gu', 'michuhol', 'michuhol-gu'),
    "부산진구": ('busanjin district', 'busanjin-gu', 'busanjin'),
    "서귀포시": ('seogwipo-si', 'seogwipo city', 'seogwipo'),
    "서대문구": ('seodaemun-gu', 'seodaemun district', 'seodaemun'),
    "영등포구": ('yeongdeungpo-gu', 'yeongdeungpo district', 'yeongdeungpo'),
    "의정부시": ('uijeongbu-si', 'uijeongbu city', 'uijeongbu'),
    "해운대구": ('haeundae-gu', 'haeundae district', 'haeundae'),
    "포항시 남구": ('nam-gu', 'nam district', 'nam'),
    "포항시 북구": ('buk-gu', 'buk district', 'buk'),
    "고양시 덕양구": ('deogyang-gu', 'deogyang district', 'deogyang'),
    "성남시 분당구": ('bundang-gu', 'bundang district', 'bundang'),
    "성남시 수정구": ('sujeong-gu', 'sujeong district', 'sujeong'),
    "성남시 중원구": ('jungwon-gu', 'jungwon district', 'jungwon'),
    "수원시 권선구": ('gwonseon-gu', 'gwonseon district', 'gwonseon'),
    "수원시 영통구": ('yeongtong-gu', 'yeongtong district', 'yeongtong'),
    "수원시 장안구": ('jangan-gu', 'jangan district', 'jangan'),
    "수원시 팔달구": ('paldal-gu', 'paldal district', 'paldal'),
    "안산시 단원구": ('danwon-gu', 'danwon district', 'danwon'),
    "안산시 상록구": ('sangnok-gu', 'sangnok district', 'sangnok'),
    "안양시 동안구": ('dongan-gu', 'dongan district', 'dongan'),
    "안양시 만안구": ('manan-gu', 'manan district', 'manan'),
    "용인시 기흥구": ('giheung-gu', 'giheung district', 'giheung'),
    "용인시 수지구": ('suji-gu', 'suji district', 'suji'),
    "용인시 처인구": ('cheoin-gu', 'cheoin district', 'cheoin'),
    "전주시 덕진구": ('deokjin-gu', 'deokjin district', 'deokjin'),
    "전주시 완산구": ('wansan-gu', 'wansan district', 'wansan'),
    "창원시 성산구": ('seongsan-gu', 'seongsan district', 'seongsan'),
    "창원시 의창구": ('uichang-gu', 'uichang district', 'uichang'),
    "창원시 진해구": ('jinhae-gu', 'jinhae district', 'jinhae'),
    "천안시 동남구": ('dongnam-gu', 'dongnam district', 'dongnam'),
    "천안시 서북구": ('seobuk-gu', 'seobuk district', 'seobuk'),
    "청주시 상당구": ('sangdang-gu', 'sangdang district', 'sangdang'),
    "청주시 서원구": ('seowon-gu', 'seowon district', 'seowon'),
    "청주시 청원구": ('cheongwon-gu', 'cheongwon district', 'cheongwon'),
    "청주시 흥덕구": ('heungdeok-gu', 'heungdeok district', 'heungdeok'),
    "고양시 일산동구": ('ilsandong-gu', 'ilsandong district', 'ilsandong'),
    "고양시 일산서구": ('ilsanseo-gu', 'ilsanseo district', 'ilsanseo'),
    "창원시 마산합포구": ('masanhappo-gu', 'masanhappo district', 'masanhappo'),
    "창원시 마산회원구": ('masanhoewon-gu', 'masanhoewon district', 'masanhoewon'),
}

_SIGUNGU_JA_HINTS: dict[str, tuple[str, ...]] = {
    "금정구": ("金井区", "金井"),
    "기장군": ("機張郡", "機張"),
    "남구": ("南区",),
    "동구": ("東区",),
    "동래구": ("東莱区", "東萊区"),
    "부산진구": ("釜山鎮区", "釜山鎮"),
    "북구": ("北区",),
    "사상구": ("沙上区",),
    "사하구": ("沙下区",),
    "서구": ("西区",),
    "수영구": ("水营区", "水營区"),
    "연제구": ("莲堤区", "蓮堤区"),
    "영도구": ("影岛区", "影島区"),
    "해운대구": ("海雲台区", "海雲台"),
    "대덕구": ("大德区",),
    "유성구": ("儒城区", "儒城"),
}


def build_hotel_search_query(sido: str, sigungu: str) -> str:
    """Google Places Text Search용 쿼리 (시·도 + 시·군·구 포함)."""
    sido = (sido or "").strip()
    sigungu = (sigungu or "").strip()
    if sigungu and sido:
        return f"{sido} {sigungu} 호텔"
    if sigungu:
        return f"{sigungu} 호텔"
    if sido:
        return f"{sido} 호텔"
    return ""


def _addr_parts(address: str) -> tuple[str, str]:
    raw = (address or "").strip()
    return raw, raw.lower()


def _has_any(raw: str, lower: str, needles: Iterable[str]) -> bool:
    for n in needles:
        if not n:
            continue
        if n.isascii():
            if n.lower() in lower:
                return True
        elif n in raw:
            return True
    return False


def _sigungu_tokens(sigungu: str) -> list[str]:
    return re.findall(r"[\uac00-\ud7a3]+(?:시|군|구)", sigungu)


def _sigungu_korean_match(raw: str, sigungu: str) -> bool:
    if sigungu in raw:
        return True
    parts = _sigungu_tokens(sigungu)
    if len(parts) >= 2:
        return all(p in raw for p in parts)
    if len(parts) == 1:
        return parts[0] in raw
    return False


def _hint_in_address(hint: str, lower: str) -> bool:
    """영문 힌트 매칭. *-gu 는 gangseo-gu 안의 seo-gu 같은 부분 일치를 막는다."""
    h = (hint or "").strip().lower()
    if not h:
        return False
    if h.endswith("-gu") or h.endswith(" district"):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(h)}(?![a-z0-9])", lower))
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(h)}(?![a-z0-9])", lower))


def _composite_sigungu_parts(sigungu: str) -> tuple[str, str] | None:
    """'고양시 일산동구' → ('고양시', '일산동구'). 단일 구·군·시면 None."""
    tokens = _sigungu_tokens(sigungu)
    if len(tokens) < 2:
        return None
    return tokens[0], tokens[-1]


def _sigungu_english_match(lower: str, sigungu: str) -> bool:
    hints = _SIGUNGU_EN_HINTS.get(sigungu, ())
    if not hints:
        return False

    composite = _composite_sigungu_parts(sigungu)
    if composite is None:
        return any(_hint_in_address(h, lower) for h in hints)

    city_si, _gu = composite
    city_hints = _CITY_SI_EN_HINTS.get(city_si, ())
    gu_ok = any(_hint_in_address(h, lower) for h in hints)
    if not gu_ok:
        return False
    if city_hints and not any(_hint_in_address(h, lower) for h in city_hints):
        return False
    return True


def _sigungu_japanese_match(raw: str, sigungu: str) -> bool:
    hints = _SIGUNGU_JA_HINTS.get(sigungu, ())
    if not hints:
        return False

    composite = _composite_sigungu_parts(sigungu)
    if composite is None:
        return any(h in raw for h in hints)

    city_si, gu_token = composite
    city_hints = _SIGUNGU_JA_HINTS.get(city_si, ())
    gu_ok = any(h in raw for h in hints) or gu_token in raw
    if not gu_ok:
        return False
    if city_hints and not any(h in raw for h in city_hints):
        return False
    return True


def _sigungu_matches(raw: str, lower: str, sigungu: str) -> bool:
    if not sigungu:
        return True
    if _sigungu_korean_match(raw, sigungu):
        return True
    if _sigungu_english_match(lower, sigungu):
        return True
    return _sigungu_japanese_match(raw, sigungu)


def _sido_matches(raw: str, lower: str, sido: str) -> bool:
    if not sido:
        return True
    pos = _SIDO_POSITIVE.get(sido, (sido,))
    return _has_any(raw, lower, pos)


def _cross_metro_ok(raw: str, lower: str, sido: str) -> bool:
    pos = _SIDO_POSITIVE.get(sido)
    if not pos:
        return True
    has_home = _has_any(raw, lower, pos)
    for ex in _SIDO_CROSS_EXCLUDE.get(sido, ()):
        if _has_any(raw, lower, (ex,)):
            if not has_home:
                return False
    return True


def address_matches_hotel_area(address: str, sido: str, sigungu: str) -> bool:
    """선택한 시·도·시군구와 주소가 일치하는지 판별."""
    raw, lower = _addr_parts(address)
    if not raw:
        return not sigungu
    if sigungu and not _sigungu_matches(raw, lower, sigungu):
        return False
    if sido and not _sido_matches(raw, lower, sido):
        return False
    if sido and not _cross_metro_ok(raw, lower, sido):
        return False
    return True


def filter_hotel_places(
    places: list[dict],
    *,
    sido: str = "",
    sigungu: str = "",
) -> tuple[list[dict], int]:
    """places dict 목록을 시·도·시군구 기준으로 필터. (결과, 제외 건수) 반환."""
    sido = (sido or "").strip()
    sigungu = (sigungu or "").strip()
    if not sido and not sigungu:
        return places, 0

    seen: set[str] = set()
    kept: list[dict] = []
    removed = 0
    for p in places:
        addr = str(p.get("address") or "")
        if not address_matches_hotel_area(addr, sido, sigungu):
            removed += 1
            continue
        key = f"{p.get('name')}|{addr}"
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(p)
    return kept, removed
