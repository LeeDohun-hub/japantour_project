"""旅行プラン生成 品質評価スクリプト

RAGAS 非使用・ルールベース評価。
ground truth 不要で、生成プランの構造・完全性を自動検査する。

実行例:
  uv run python -m evaluation.scripts.evaluate_plan
  uv run python -m evaluation.scripts.evaluate_plan --limit 4
  uv run python -m evaluation.scripts.evaluate_plan --output evaluation/reports/plan_eval_custom.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
# VisitKorea 등 Django cache를 사용하는 모듈을 위해 backend 디렉토리를 경로에 추가
BACKEND_ROOT = PROJECT_ROOT / "backend"
if BACKEND_ROOT.exists():
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8")

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django
    django.setup()
except Exception:
    pass  # Django 미설치 환경에서도 동작하도록 (캐시 없이 진행)

DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "data" / "plan_eval_cases.json"
REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"

# ── 정규식 패턴 ────────────────────────────────────────────────────────────
# N日目/最終日 헤딩 — ## N日目 / **N日目** / N日目 (마크다운 없이 줄 단독) 모두 허용
_DAY_HEADING = re.compile(
    r"(?:^|\n)(?:#{1,3}\s*|\*{2})?(?:(\d+)日目|(最終日))(?:\*{2})?",
    re.MULTILINE,
)
# 슬롯 라벨 — **昼食** / 줄 단독 "昼食" / "### 昼食"(마크다운 헤더) 모두 허용 (후행 공백 허용)
_SLOT_LABEL = re.compile(
    r"\*\*(?:午前|昼食|午後|夕食|夜)\*\*"
    r"|^#{1,3}\s*(?:午前|昼食|午後|夕食|夜)\s*$"
    r"|^(?:午前|昼食|午後|夕食|夜)\s*$",
    re.MULTILINE,
)
_LUNCH_LABEL = re.compile(
    r"\*\*昼食\*\*|^昼食\s*$|#{1,3}\s*昼食",
    re.MULTILINE,
)
_DINNER_LABEL = re.compile(
    r"\*\*夕食\*\*|^夕食\s*$|#{1,3}\s*夕食",
    re.MULTILINE,
)
# 도착일에 사용하는 ①②③
_NUMBERED = re.compile(r"[①②③④⑤]")
# Naver 지도 URL
_NAVER_URL = re.compile(r"https://map\.naver\.com/\S+")
# 식사 슬롯 내용 추출: 昼食/夕食 라벨(bold·plain·"### 昼食" 헤더) 이후 다음 슬롯/섹션까지
_MEAL_SLOT_CONTENT = re.compile(
    r"(?:\*\*(?:昼食|夕食)\*\*|^#{1,3}\s*(?:昼食|夕食)\s*$|^(?:昼食|夕食)\s*$)(.*?)"
    r"(?=\*\*(?:午前|昼食|午後|夕食|夜)\*\*|^#{1,3}\s*(?:午前|昼食|午後|夕食|夜)\s*$"
    r"|^(?:午前|昼食|午後|夕食|夜)\s*$|^#{1,3}\s|\d+日目|\Z)",
    re.DOTALL | re.MULTILINE,
)


# ── 프롬프트 빌더 ──────────────────────────────────────────────────────────
_COMPANION_JA = {
    "solo": "ひとり旅",
    "couple": "夫婦・カップル",
    "family": "家族",
    "friends": "友人グループ",
}
_STYLE_JA = {
    "must_see": "有名観光地は必須",
    "healing": "ゆったり癒し",
    "culture": "文化・芸術・歴史",
    "nature": "自然と一緒に",
    "sns_hot": "SNS人気スポット",
    "experience": "体験・アクティビティ",
    "local_vibe": "旅行地の雰囲気たっぷり",
    "shop_hard": "ショッピングは本気",
    "food_first": "観光よりグルメ",
}


def build_plan_prompt(case: dict) -> str:
    """テストケースからプランリクエストプロンプトを生成"""
    nights: int = case["nights"]
    days = nights + 1
    extra: str = case.get("user_message_extra", "")
    add: dict = (case.get("traveler_profile") or {}).get("additional") or {}
    companion_ja = _COMPANION_JA.get(add.get("companion", ""), add.get("companion", ""))
    styles_ja = "・".join(
        _STYLE_JA.get(s, s) for s in (add.get("travelStyles") or [])
    )

    lines = [
        extra,
        f"【滞在期間】{nights}泊{days}日",
        f"【同行者】{companion_ja}",
    ]
    if styles_ja:
        lines.append(f"【旅行スタイル】{styles_ja}")

    lines += [
        "【内部方針 meal_policy】lunch_required=true / dinner_required=true"
        " / gourmet_selected=false / meal_detail_level=normal / cafe_as_afternoon_stop=false",
        "【表示形式】時刻レンジ（例:[10:00〜11:00]）は書かない。"
        "各日は「1日目」「2日目」見出し＋「午前」「昼食」「午後」「夕食」の順序ラベル"
        "（1日目の到着動線のみ①②③可）。"
        "飲食店は必ず「昼食」「夕食」スロットにのみ配置し、"
        "「午前」「午後」スロットへの飲食店記載は絶対禁止。",
        "【食事 — 厳守】朝食は入れない。観光可能な旅行日の食事は昼食1件・夕食1件の2回だけ。"
        "到着が遅い入国日・出国が早い最終日は食事ブロックを書かない。",
        "【日程密度】観光可能な旅行日は、観光/体験2〜3件＋昼食1件＋夕食1件を基本上限にする。",
    ]
    return "\n".join(l for l in lines if l)


# ── テキスト解析 ───────────────────────────────────────────────────────────
def split_by_day(text: str, total_days: int | None = None) -> list[tuple[int, str]]:
    """プランテキストを日別セクションに分割 → [(day_num, content), ...]"""
    matches = list(_DAY_HEADING.finditer(text))
    if not matches:
        return []
    result: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        if m.group(1):
            day_num = int(m.group(1))
        elif total_days is not None:
            day_num = total_days
        else:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result.append((day_num, text[start:end]))
    return result


def meal_slot_content(day_content: str, label: str) -> str:
    """지정 식사 라벨 뒤의 실제 내용을 다음 슬롯/날짜 전까지 추출."""
    pattern = re.compile(
        rf"(?:\*\*{label}\*\*|^#{{1,3}}\s*{label}\s*$|^{label}\s*$)(.*?)"
        r"(?=\*\*(?:午前|昼食|午後|夕食|夜)\*\*|^#{1,3}\s*(?:午前|昼食|午後|夕食|夜)\s*$"
        r"|^(?:午前|昼食|午後|夕食|夜)\s*$|^#{1,3}\s|\d+日目|最終日|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(day_content)
    return match.group(1).strip() if match else ""


def compute_metrics(reply: str, nights: int) -> dict:
    total_days = nights + 1
    days = split_by_day(reply, total_days=total_days)
    found_days = len({n for n, _ in days})

    # ── 1. 날짜 수 정확도 ─────────────────────────────────────────────────
    day_count_ok = found_days == total_days

    # ── 2. 슬롯 충전율 (식사 슬롯) ────────────────────────────────────────
    # 도착일(1日目)·출국일(最終日)은 식사 생략 허용 → 중간 날만 체크
    eligible = [(n, c) for n, c in days if n not in (1, total_days)]
    days_with_lunch = sum(1 for _, c in eligible if meal_slot_content(c, "昼食"))
    days_with_dinner = sum(1 for _, c in eligible if meal_slot_content(c, "夕食"))
    days_with_both = sum(
        1
        for _, c in eligible
        if meal_slot_content(c, "昼食") and meal_slot_content(c, "夕食")
    )
    eligible_count = len(eligible)
    slot_fill_rate = days_with_both / eligible_count if eligible_count else 1.0
    lunch_fill_rate = days_with_lunch / eligible_count if eligible_count else 1.0
    dinner_fill_rate = days_with_dinner / eligible_count if eligible_count else 1.0

    # ── 3. 포맷 준수율 ────────────────────────────────────────────────────
    # 도착일·출국일 제외: 관광 가능한 중간 날의 午前/昼食/午後/夕食 라벨 사용 여부
    days_with_slot_labels = sum(1 for _, c in eligible if _SLOT_LABEL.search(c))
    # ①②③만 사용하고 슬롯 라벨 없는 날 (위반)
    days_numbered_only = sum(
        1 for _, c in eligible
        if _NUMBERED.search(c) and not _SLOT_LABEL.search(c)
    )
    format_compliance = (
        days_with_slot_labels / len(eligible) if eligible else 1.0
    )

    # ── 4. 식사 슬롯 URL 존재율 ──────────────────────────────────────────
    meal_slot_contents = _MEAL_SLOT_CONTENT.findall(reply)
    total_meal_slots = len(meal_slot_contents)
    meal_slots_with_url = sum(1 for s in meal_slot_contents if _NAVER_URL.search(s))
    meal_url_rate = meal_slots_with_url / total_meal_slots if total_meal_slots else 0.0

    # ── 5. 도착일 형식 확인 (①②③ 사용 여부) ───────────────────────────
    arrival_content = next((c for n, c in days if n == 1), "")
    arrival_uses_numbers = bool(_NUMBERED.search(arrival_content))

    return {
        # 날짜
        "day_count_expected": total_days,
        "day_count_found": found_days,
        "day_count_ok": day_count_ok,
        # 식사 슬롯
        "eligible_meal_days": eligible_count,
        "days_with_lunch": days_with_lunch,
        "days_with_dinner": days_with_dinner,
        "days_with_both_meals": days_with_both,
        "slot_fill_rate": round(slot_fill_rate, 4),
        "lunch_fill_rate": round(lunch_fill_rate, 4),
        "dinner_fill_rate": round(dinner_fill_rate, 4),
        # 포맷
        "days_with_slot_labels": days_with_slot_labels,
        "days_numbered_only": days_numbered_only,
        "format_compliance": round(format_compliance, 4),
        # URL
        "total_meal_slots_found": total_meal_slots,
        "meal_slots_with_url": meal_slots_with_url,
        "meal_url_rate": round(meal_url_rate, 4),
        # 도착일
        "arrival_uses_numbers": arrival_uses_numbers,
    }


# ── 생성 ─────────────────────────────────────────────────────────────────
def generate_plan(case: dict, client) -> dict:
    from src.chain.router import route_and_answer

    user_message = build_plan_prompt(case)
    profile = dict(case.get("traveler_profile") or {})

    started = time.perf_counter()
    result = route_and_answer(
        user_message=user_message,
        reply_language="日本語",
        history=[],
        openai_client=client,
        traveler_profile=profile,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    reply = result.reply or ""
    metrics = compute_metrics(reply, case["nights"])

    return {
        "id": case["id"],
        "description": case["description"],
        "nights": case["nights"],
        "route_category": result.category,
        "latency_ms": elapsed_ms,
        "reply_length": len(reply),
        "metrics": metrics,
        "reply": reply,
    }


# ── 집계 ─────────────────────────────────────────────────────────────────
def aggregate(records: list[dict]) -> dict:
    def avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 4) if vals else None

    def pct(key: str) -> float | None:
        vals = [r["metrics"].get(key) for r in records if r.get("metrics")]
        return avg([v for v in vals if v is not None])

    slot_fill_rates = [r["metrics"]["slot_fill_rate"] for r in records if r.get("metrics")]
    format_compliances = [r["metrics"]["format_compliance"] for r in records if r.get("metrics")]
    meal_url_rates = [r["metrics"]["meal_url_rate"] for r in records if r.get("metrics")]
    day_ok = [r["metrics"]["day_count_ok"] for r in records if r.get("metrics")]

    return {
        "total_cases": len(records),
        "avg_latency_ms": avg([r["latency_ms"] for r in records]),
        # 핵심 지표
        "slot_fill_rate":    avg(slot_fill_rates),
        "lunch_fill_rate":   pct("lunch_fill_rate"),
        "dinner_fill_rate":  pct("dinner_fill_rate"),
        "format_compliance": avg(format_compliances),
        "meal_url_rate":     avg(meal_url_rates),
        "day_count_accuracy": sum(day_ok) / len(day_ok) if day_ok else None,
    }


# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="旅行プラン生成 品質評価")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=0, help="評価件数 (0=全件)")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--recompute-from",
        type=Path,
        help="기존 리포트의 reply를 재생성 없이 현재 평가 규칙으로 다시 채점",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    if args.recompute_from:
        report = json.loads(args.recompute_from.read_text(encoding="utf-8"))
        records = report.get("cases") or []
        if not records:
            raise SystemExit("재채점할 기존 cases가 없습니다.")
        for record in records:
            record["metrics"] = compute_metrics(record.get("reply", ""), record["nights"])
        report["summary"] = aggregate(records)
        report.setdefault("metadata", {})["recomputed_at"] = datetime.now().isoformat()
        report["metadata"]["recomputed_from"] = str(args.recompute_from)
        output = args.output or args.recompute_from
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        print(f"[SAVED] {output}")
        return

    cases: list[dict] = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.limit and args.limit < len(cases):
        cases = cases[: args.limit]

    from openai import OpenAI
    client = OpenAI()

    print(f"[PLAN EVAL] {len(cases)}件 プラン生成・評価開始")
    records: list[dict] = []

    for i, case in enumerate(cases, 1):
        print(f"  {i:02d}/{len(cases):02d} generating ... {case['id']} ({case['description']})")
        try:
            record = generate_plan(case, client)
            records.append(record)
            m = record["metrics"]
            print(
                f"         slot={m['slot_fill_rate']:.2f}"
                f"  fmt={m['format_compliance']:.2f}"
                f"  url={m['meal_url_rate']:.2f}"
                f"  days={m['day_count_found']}/{m['day_count_expected']}"
                f"  {record['latency_ms']}ms"
            )
        except Exception as exc:
            print(f"  {i:02d}/{len(cases):02d} ERROR {case['id']}: {exc}")
            traceback.print_exc()

    if not records:
        raise SystemExit("評価結果がありません。")

    summary = aggregate(records)

    print("\n[RESULT]")
    print(f"  {'total_cases':28s} {summary['total_cases']}")
    for key in ("slot_fill_rate", "lunch_fill_rate", "dinner_fill_rate",
                "format_compliance", "meal_url_rate", "day_count_accuracy"):
        v = summary.get(key)
        if v is not None:
            print(f"  {key:28s} {v:.4f}")
    print(f"  {'avg_latency_ms':28s} {summary['avg_latency_ms']:.1f}ms")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or (REPORTS_DIR / f"plan_eval_{timestamp}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "dataset": str(args.dataset),
                    "total_cases": len(records),
                },
                "summary": summary,
                "cases": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[SAVED] {output}")


if __name__ == "__main__":
    main()
