"""평가 데이터·Few-shot 예시 누수(leakage) 감사 스크립트.

판정 기준:
  1. exact          : 질문 문자열이 few-shot 예시와 완전히 일치
  2. substring      : few-shot 예시가 질문의 부분 문자열 (또는 반대)
  3. keyword_overlap: 의미 있는 토큰 ≥2개 겹치고 few-shot 토큰의 ≥60% 포함
  4. cross_lang     : 다른 언어로 동일 개념 (한국어↔일본어 주요 토큰 매핑)

실행:
    python -m evaluation.scripts.audit_eval_leakage
    python -m evaluation.scripts.audit_eval_leakage --strict   # 누수 발견 시 exit 1
    python -m evaluation.scripts.audit_eval_leakage --no-write # seen/unseen 파일 생성 생략
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import io
if hasattr(sys.stdout, "buffer") and (not sys.stdout.encoding or sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig")):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROUTER_PATH = PROJECT_ROOT / "src" / "chain" / "router.py"
PROMPTS_PATH = PROJECT_ROOT / "src" / "chain" / "prompts.py"
EVAL_PATH = PROJECT_ROOT / "evaluation" / "data" / "tour_eval.json"
SEEN_PATH = PROJECT_ROOT / "evaluation" / "data" / "tour_eval_seen.json"
UNSEEN_PATH = PROJECT_ROOT / "evaluation" / "data" / "tour_eval_unseen.json"

_FEW_SHOT_RE = re.compile(r'- "([^"]+)"\s*->')

# 한국어↔일본어 의미 동등 쌍 (substring 체크에 사용)
# 각 튜플: (한국어, 일본어) — 질문과 few-shot 텍스트에 문자열 포함 여부로 판단
_CROSS_LANG_PAIRS: list[tuple[str, str]] = [
    ("겨울", "冬"),
    ("서울", "ソウル"),
    ("명동", "明洞"),
    ("쇼핑", "ショッピング"),
    ("호텔", "ホテル"),
    ("공항", "空港"),
    ("옷차림", "服装"),
    ("맛집", "グルメ"),
    ("제주도", "済州"),
    ("부산", "釜山"),
    ("음식", "料理"),
    ("교통", "交通"),
    ("식당", "食堂"),
    ("한복", "韓服"),
    ("궁궐", "宮殿"),
    ("환전", "両替"),
    ("지하철", "地下鉄"),
    ("관광지", "観光地"),
]

_STOPWORDS = {
    # Korean particles / endings
    "추천", "알려줘", "해줘", "어디야", "좋아", "어때", "이야", "주세요", "줘",
    "은", "는", "이", "가", "을", "를", "에서", "에", "으로", "로", "의",
    "와", "과", "도", "만", "에게", "하고", "부터", "까지", "있는", "없는",
    "가는", "오는", "보는", "먹는", "방법", "곳", "것", "데", "때", "안",
    # Travel-domain overly common words (appear in almost every query)
    "여행", "관광", "코스", "일정", "추천해줘", "알려줘",
    # Japanese particles / endings
    "から", "で", "は", "を", "が", "の", "に", "へ", "と", "も", "か",
    "ね", "よ", "て", "し", "な", "たら", "けど", "って", "くれ", "ください",
    "教えて", "おすすめ", "ところ", "こと", "もの", "どこ", "いい", "ある",
    # Travel-domain overly common (Japanese)
    "旅行", "観光", "コース", "日程",
}


def _parse_few_shots(path: Path) -> list[tuple[str, str]]:
    """파일에서 few-shot 예시 목록 추출. (question, source) 튜플 반환."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [(m.group(1), path.name) for m in _FEW_SHOT_RE.finditer(text)]


def _tokenize(text: str) -> set[str]:
    tokens = set(re.split(r"[\s\.,?！？!。、・]+", text.lower()))
    return tokens - _STOPWORDS - {""}


def _cross_lang_hits(question: str, few_shot: str) -> list[str]:
    """질문과 few-shot 간 cross-language 의미 쌍 매칭 수 반환.

    일본어는 공백이 없어 토큰화가 어려우므로 순수 문자열 포함(substring) 검사 사용.
    각 쌍에 대해: (Korean ∈ question AND Japanese ∈ few-shot) 또는 (Japanese ∈ question AND Korean ∈ few-shot)
    """
    q_lower = question.lower()
    fs_lower = few_shot.lower()
    hits = []
    for ko, ja in _CROSS_LANG_PAIRS:
        ja_lower = ja.lower()
        if ko in q_lower and ja_lower in fs_lower:
            hits.append(f"{ko}↔{ja}")
        elif ja_lower in q_lower and ko in fs_lower:
            hits.append(f"{ja}↔{ko}")
    return hits


def _check_leakage(question: str, few_shots: list[tuple[str, str]]) -> dict:
    q_lower = question.lower().strip()
    q_tokens = _tokenize(question)

    for fs_text, fs_source in few_shots:
        fs_lower = fs_text.lower().strip()
        fs_tokens = _tokenize(fs_text)

        # 1. Exact match
        if q_lower == fs_lower:
            return {
                "leaked": True,
                "type": "exact",
                "matched": fs_text,
                "source": fs_source,
            }

        # 2. Substring (either direction, min 4 chars)
        if len(fs_lower) >= 4 and (fs_lower in q_lower or q_lower in fs_lower):
            return {
                "leaked": True,
                "type": "substring",
                "matched": fs_text,
                "source": fs_source,
            }

        # 3. Keyword overlap (monolingual, token-level)
        if len(fs_tokens) >= 2 and len(q_tokens) >= 2:
            overlap = fs_tokens & q_tokens
            if len(overlap) >= 2 and len(overlap) / len(fs_tokens) >= 0.6:
                return {
                    "leaked": True,
                    "type": "keyword_overlap",
                    "matched": fs_text,
                    "source": fs_source,
                    "overlap": sorted(overlap),
                }

        # 4. Cross-language substring overlap (Korean↔Japanese pair matching)
        hits = _cross_lang_hits(question, fs_text)
        if len(hits) >= 2:
            return {
                "leaked": True,
                "type": "keyword_overlap_cross_lang",
                "matched": fs_text,
                "source": fs_source,
                "overlap": hits,
            }

    return {"leaked": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="평가 데이터 누수 감사")
    parser.add_argument("--strict", action="store_true", help="누수 발견 시 exit 1")
    parser.add_argument("--no-write", action="store_true", help="seen/unseen 파일 생성 생략")
    parser.add_argument(
        "--eval",
        default=str(EVAL_PATH),
        help=f"평가 데이터 경로 (기본: {EVAL_PATH})",
    )
    args = parser.parse_args()

    router_shots = _parse_few_shots(ROUTER_PATH)
    prompts_shots = _parse_few_shots(PROMPTS_PATH)
    all_shots: list[tuple[str, str]] = []
    seen_questions: set[str] = set()
    for q, src in router_shots + prompts_shots:
        if q not in seen_questions:
            all_shots.append((q, src))
            seen_questions.add(q)

    print(f"[감사 대상]")
    print(f"  few-shot 예시 : {len(all_shots)}개 (router.py: {len(router_shots)}, prompts.py: {len(prompts_shots)})")
    print(f"  router.py     : {ROUTER_PATH}")
    print(f"  prompts.py    : {PROMPTS_PATH}")

    eval_path = Path(args.eval)
    if not eval_path.exists():
        print(f"[오류] 평가 데이터 없음: {eval_path}")
        sys.exit(1)
    with open(eval_path, encoding="utf-8") as f:
        cases = json.load(f)

    seen: list[dict] = []
    unseen: list[dict] = []
    leakage_found = False

    print(f"\n{'─'*75}")
    print(f"{'ID':5}  {'질문':45}  {'판정':10}  {'유형·근거'}")
    print(f"{'─'*75}")

    for case in cases:
        result = _check_leakage(case["question"], all_shots)
        if result["leaked"]:
            leakage_found = True
            mark = "SEEN"
            info = f"{result['type']}  ← \"{result['matched'][:35]}\""
            seen_case = {
                **case,
                "leakage_type": result["type"],
                "matched_few_shot": result["matched"],
                "leakage_source": [result["source"]],
            }
            seen.append(seen_case)
        else:
            mark = "ok"
            info = ""
            unseen.append(case)

        q_display = case["question"][:43].ljust(45)
        mark_display = f"{'🚨 ' + mark if result['leaked'] else '✅ ' + mark:10}"
        print(f"{case['id']:5}  {q_display}  {mark_display}  {info}")

    print(f"{'─'*75}")
    print(f"\nSEEN   : {len(seen)}건  {[c['id'] for c in seen]}")
    print(f"UNSEEN : {len(unseen)}건  {[c['id'] for c in unseen]}")

    # T004 특수 경고: few-shot 카테고리 충돌
    t004_in_unseen = any(c["id"] == "T004" for c in unseen)
    if t004_in_unseen:
        print(
            "\n[⚠ 주의] T004 '제주도에서 하루 여행 코스': few-shot '제주도 여행' → leisure 매핑이 있으나"
            "\n         T004의 expected_category='itinerary'. 누수는 아니지만 분류 오류 위험."
        )

    if not args.no_write:
        SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
        UNSEEN_PATH.write_text(json.dumps(unseen, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장: {SEEN_PATH}  ({len(seen)}건)")
        print(f"저장: {UNSEEN_PATH}  ({len(unseen)}건)")

    print()
    if args.strict and leakage_found:
        print("[STRICT] 누수 발견 → exit 1")
        sys.exit(1)
    elif leakage_found:
        print("[경고] 누수가 있지만 --strict 미지정이므로 계속 진행합니다.")


if __name__ == "__main__":
    main()
