"""AI Hub 원본 JSON(data.zip)에서 tour_knowledge.csv를 생성하는 스크립트.

실행:
    python extract_tour_knowledge.py
    python extract_tour_knowledge.py --limit 500       # 카테고리당 최대 파일 수
    python extract_tour_knowledge.py --limit 0         # 전체 (매우 느림)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

# Windows 콘솔 한국어 출력 보장
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent
ZIP_PATH = PROJECT_ROOT / "data.zip"
OUTPUT_CSV = PROJECT_ROOT / "data" / "raw" / "tour_knowledge.csv"

LABEL_DIR_MARKER = "02."

CATEGORY_MAP = {
    "FOOD": "food",
    "HIS": "culture",
    "LEI": "leisure",
    "NAT": "nature",
    "SHOP": "shopping",
    "STAY": "stay",
}

DOMAIN_MAP = {
    "음식점": "food",
    "자연관광": "nature",
    "문화/역사관광": "culture",
    "역사": "culture",
    "숙박": "stay",
    "쇼핑": "shopping",
    "레포츠": "leisure",
}

# ─── 지역명 → 표준 area 값 매핑 ──────────────────────────────────────────
# 긴 키워드가 먼저 매치되도록 길이 내림차순 정렬 필요 (build_area_pattern에서 처리)
_AREA_KW: dict[str, str] = {
    # ── 서울 주요 동/지역 ─────────────────────────────────
    "경복궁": "Seoul", "광화문": "Seoul", "인사동": "Seoul", "북촌": "Seoul",
    "서촌": "Seoul", "익선동": "Seoul", "을지로": "Seoul", "낙원동": "Seoul",
    "동대문": "Seoul", "이태원": "Seoul", "한남동": "Seoul", "용산": "Seoul",
    "여의도": "Seoul", "합정": "Seoul", "망원동": "Seoul", "연남동": "Seoul",
    "홍대": "Seoul", "신촌": "Seoul", "마포": "Seoul", "상암": "Seoul",
    "성수동": "Seoul", "성수": "Seoul", "건대": "Seoul", "뚝섬": "Seoul",
    "잠실": "Seoul", "강남": "Seoul", "압구정": "Seoul", "청담": "Seoul",
    "신사동": "Seoul", "가로수길": "Seoul", "논현": "Seoul", "역삼": "Seoul",
    "선릉": "Seoul", "강동": "Seoul", "송파": "Seoul", "방이동": "Seoul",
    "종로": "Seoul", "명동": "Seoul", "남산": "Seoul", "서울역": "Seoul",
    "노원": "Seoul", "도봉": "Seoul", "강북": "Seoul", "은평": "Seoul",
    "서대문": "Seoul", "중구": "Seoul", "중랑": "Seoul", "도심": "Seoul",
    # ── 부산 ─────────────────────────────────────────────
    "해운대": "Busan", "광안리": "Busan", "센텀": "Busan", "기장": "Busan",
    "서면": "Busan", "남포동": "Busan", "자갈치": "Busan", "영도": "Busan",
    "동래": "Busan", "사하": "Busan", "강서": "Busan", "기장군": "Busan",
    # ── 인천 ─────────────────────────────────────────────
    "송도": "Incheon", "월미도": "Incheon", "차이나타운": "Incheon",
    "강화도": "Incheon", "강화": "Incheon",
    # ── 경기도 ───────────────────────────────────────────
    "수원": "Suwon", "화성": "Hwaseong", "오산": "Osan",
    "성남": "Seongnam", "판교": "Seongnam", "분당": "Seongnam",
    "용인": "Yongin", "에버랜드": "Yongin",
    "고양": "Goyang", "일산": "Goyang", "파주": "Paju",
    "가평": "Gapyeong", "남이섬": "Gapyeong", "춘천": "Chuncheon",
    "양평": "Yangpyeong", "하남": "Hanam", "광주": "Gwangju-Gyeonggi",
    "이천": "Icheon", "여주": "Yeoju",
    # ── 강원도 ───────────────────────────────────────────
    "강릉": "Gangneung", "정동진": "Gangneung", "경포": "Gangneung",
    "속초": "Sokcho", "설악산": "Sokcho", "양양": "Yangyang",
    "평창": "Pyeongchang", "알펜시아": "Pyeongchang",
    "정선": "Jeongseon", "태백": "Taebaek", "동해": "Donghae",
    "삼척": "Samcheok", "인제": "Inje", "원주": "Wonju",
    "홍천": "Hongcheon", "횡성": "Hoengseong",
    # ── 충청도 ───────────────────────────────────────────
    "청주": "Cheongju", "충주": "Chungju", "제천": "Jecheon",
    "단양": "Danyang", "보은": "Boeun",
    "천안": "Cheonan", "아산": "Asan", "서산": "Seosan",
    "태안": "Taean", "보령": "Boryeong", "공주": "Gongju",
    "부여": "Buyeo", "논산": "Nonsan", "당진": "Dangjin",
    # ── 전라도 ───────────────────────────────────────────
    "전주": "Jeonju", "군산": "Gunsan", "익산": "Iksan",
    "남원": "Namwon", "정읍": "Jeongeup",
    "목포": "Mokpo", "여수": "Yeosu", "순천": "Suncheon",
    "광양": "Gwangyang", "나주": "Naju", "담양": "Damyang",
    "구례": "Gurye", "고흥": "Goheung", "보성": "Boseong",
    "해남": "Haenam", "완도": "Wando", "진도": "Jindo",
    # ── 경상도 ───────────────────────────────────────────
    "경주": "Gyeongju", "불국사": "Gyeongju", "첨성대": "Gyeongju",
    "안동": "Andong", "하회마을": "Andong",
    "포항": "Pohang", "구미": "Gumi", "김천": "Gimcheon",
    "상주": "Sangju", "문경": "Mungyeong", "영주": "Yeongju",
    "영천": "Yeongcheon", "경산": "Gyeongsan",
    "창원": "Changwon", "진주": "Jinju", "통영": "Tongyeong",
    "거제": "Geoje", "사천": "Sacheon", "김해": "Gimhae",
    "밀양": "Miryang", "양산": "Yangsan", "거창": "Geochang",
    "하동": "Hadong", "남해": "Namhae", "함양": "Hamyang",
    # ── 제주 ─────────────────────────────────────────────
    "제주": "Jeju", "서귀포": "Seogwipo",
    "한라산": "Jeju", "성산": "Jeju", "우도": "Jeju",
    "협재": "Jeju", "애월": "Jeju", "중문": "Jeju",
    # ── 광역시 (단독 키워드) ──────────────────────────────
    "서울": "Seoul", "부산": "Busan", "인천": "Incheon",
    "대구": "Daegu", "대전": "Daejeon", "울산": "Ulsan", "세종": "Sejong",
}

# 긴 키워드 우선 매치를 위해 길이 내림차순으로 정렬
_AREA_SORTED: list[tuple[str, str]] = sorted(
    _AREA_KW.items(), key=lambda x: len(x[0]), reverse=True
)


def extract_area(title: str, text: str = "") -> str:
    """제목과 텍스트에서 지역명을 추출합니다.

    긴 키워드가 먼저 매치되어 오버랩을 방지합니다.
    예: "해운대 맛집" → "Busan", "제주 서귀포" → "Jeju"
    """
    combined = str(title or "") + " " + str(text or "")
    for keyword, area in _AREA_SORTED:
        if keyword in combined:
            return area
    return ""


def get_category(filename: str, domain: str) -> str:
    for prefix, cat in CATEGORY_MAP.items():
        if filename.startswith(f"J_{prefix}_"):
            return cat
    return DOMAIN_MAP.get(domain, "other")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Hub → tour_knowledge.csv 변환")
    parser.add_argument("--limit", type=int, default=1000,
                        help="카테고리당 최대 파일 수 (0=전체, 기본값=1000)")
    parser.add_argument("--zip", default=str(ZIP_PATH))
    parser.add_argument("--output", default=str(OUTPUT_CSV))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    zip_path = Path(args.zip)
    output_csv = Path(args.output)

    if not zip_path.exists():
        raise FileNotFoundError(f"data.zip 을 찾을 수 없습니다: {zip_path}")

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    per_cat_limit = args.limit if args.limit > 0 else None
    per_cat_count: dict[str, int] = {}
    total_rows = 0
    total_files = 0
    skipped = 0
    area_filled = 0

    print(f"[INFO] ZIP: {zip_path}")
    print(f"[INFO] Output: {output_csv}")
    print(f"[INFO] 카테고리당 최대 파일 수: {'전체' if per_cat_limit is None else per_cat_limit}")
    print()

    with zipfile.ZipFile(zip_path, "r") as zf, open(
        output_csv, "w", newline="", encoding="utf-8-sig"
    ) as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["id", "category", "area", "question_ja", "answer_ja", "answer_ko"],
        )
        writer.writeheader()

        entries = [
            e for e in zf.infolist()
            if LABEL_DIR_MARKER in e.filename and e.filename.endswith(".json")
        ]
        print(f"[INFO] 라벨 JSON 파일 총 수: {len(entries):,}")

        for entry in entries:
            filename = Path(entry.filename).name
            cat_prefix = None
            for prefix in CATEGORY_MAP:
                if filename.startswith(f"J_{prefix}_"):
                    cat_prefix = prefix
                    break

            cat_key = cat_prefix or "OTHER"

            if per_cat_limit is not None:
                if per_cat_count.get(cat_key, 0) >= per_cat_limit:
                    skipped += 1
                    continue

            try:
                raw = zf.read(entry.filename)
                data = json.loads(raw.decode("utf-8"))
            except Exception as e:
                print(f"[WARN] 파싱 실패: {filename} → {e}")
                continue

            data_info = data.get("data_info", {})
            doc_id = data_info.get("documentID", filename.replace(".json", ""))
            domain = data_info.get("domain", "")
            title = data_info.get("title", "")
            category = get_category(filename, domain)

            # area 추출: title 우선, 없으면 text에서
            text_snippet = (data.get("text") or "")[:200]
            area = extract_area(title, text_snippet)
            if area:
                area_filled += 1

            qa_list = data.get("QA", [])
            if not qa_list:
                continue

            for i, qa in enumerate(qa_list):
                question = (qa.get("question") or "").strip()
                answer = (qa.get("answer") or "").strip()
                if not question or not answer:
                    continue

                writer.writerow({
                    "id": f"{doc_id}_q{i + 1}",
                    "category": category,
                    "area": area,
                    "question_ja": question,
                    "answer_ja": answer,
                    "answer_ko": "",
                })
                total_rows += 1

            per_cat_count[cat_key] = per_cat_count.get(cat_key, 0) + 1
            total_files += 1

            if total_files % 500 == 0:
                print(f"  처리 완료: {total_files:,}개 파일, {total_rows:,}개 행, area 추출 {area_filled:,}개 ...")

    print()
    print(f"[INFO] 완료!")
    print(f"  처리 파일  : {total_files:,}개")
    print(f"  스킵 파일  : {skipped:,}개 (limit 초과)")
    print(f"  생성 행    : {total_rows:,}개")
    print(f"  area 추출  : {area_filled:,}개 ({area_filled * 100 // max(total_files, 1)}%)")
    print()
    print("카테고리별 파일 수:")
    for cat, count in sorted(per_cat_count.items()):
        mapped = CATEGORY_MAP.get(cat, cat)
        print(f"  {cat:6s} ({mapped:10s}): {count:,}개")
    print()
    print(f"[INFO] 저장됨: {output_csv}")


if __name__ == "__main__":
    main()
