"""tour_knowledge.jsonl 및 평가 데이터셋 요약 통계."""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "docs" / "DATASET_SUMMARY.md"


def _out(lines: list[str], text: str = "") -> None:
    if text:
        lines.append(text)
        print(text)


def analyze_jsonl(path: Path, lines: list[str]) -> None:
    cats: Counter[str] = Counter()
    areas: Counter[str] = Counter()
    empty_area = 0
    empty_ko = 0
    total = 0
    samples: dict[str, list] = {}

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            total += 1
            cat = r.get("category") or "other"
            cats[cat] += 1
            area = (r.get("area") or "").strip()
            if area:
                areas[area] += 1
            else:
                empty_area += 1
            if not (r.get("answer_ko") or "").strip():
                empty_ko += 1
            if cat not in samples:
                samples[cat] = []
            if len(samples[cat]) < 2:
                samples[cat].append(
                    {
                        "id": r.get("id", ""),
                        "area": area or "(empty)",
                        "q": (r.get("question_ja") or "")[:70],
                        "a": (r.get("answer_ja") or "")[:90],
                    }
                )

    _out(lines, f"\n## {path.relative_to(ROOT).as_posix()}\n")
    _out(lines, f"**총 레코드: {total:,}건**\n")
    _out(lines, "### 카테고리별\n")
    _out(lines, "| category | 건수 | 비율 |")
    _out(lines, "|----------|------|------|")
    for cat, n in cats.most_common():
        _out(lines, f"| `{cat}` | {n:,} | {100 * n / total:.1f}% |")
    _out(lines, f"\n- `area` 비어 있음: **{empty_area:,}건** ({100 * empty_area / total:.1f}%)")
    _out(lines, f"- `answer_ko` 비어 있음: **{empty_ko:,}건** (100%) — 일본어 Q&A만 사용\n")
    _out(lines, "### 상위 20개 지역 (area)\n")
    _out(lines, "| area | 건수 |")
    _out(lines, "|------|------|")
    for area, n in areas.most_common(20):
        _out(lines, f"| {area} | {n:,} |")
    seoul = sum(n for a, n in areas.items() if "Seoul" in a)
    busan = sum(n for a, n in areas.items() if "Busan" in a)
    jeju = sum(n for a, n in areas.items() if "Jeju" in a)
    _out(lines, f"\n주요 도시: Seoul {seoul:,} / Busan {busan:,} / Jeju {jeju:,}\n")
    _out(lines, "### 카테고리별 샘플 (각 2건)\n")
    for cat in sorted(samples.keys()):
        _out(lines, f"\n#### `{cat}`\n")
        for s in samples[cat]:
            _out(lines, f"- **{s['id']}** (area: {s['area']})")
            _out(lines, f"  - Q: {s['q']}")
            _out(lines, f"  - A: {s['a']}")


def analyze_eval_json(path: Path, lines: list[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    _out(lines, f"\n## {path.relative_to(ROOT).as_posix()} ({len(data)}건)\n")
    cats: Counter[str] = Counter()
    langs: Counter[str] = Counter()
    for row in data:
        cats[row.get("expected_category", "?")] += 1
        langs[row.get("reply_language", "?")] += 1
    _out(lines, "### expected_category\n")
    _out(lines, "| category | 건수 |")
    _out(lines, "|----------|------|")
    for c, n in cats.most_common():
        _out(lines, f"| `{c}` | {n} |")
    _out(lines, "\n### reply_language\n")
    for lang, n in langs.most_common():
        _out(lines, f"- {lang}: {n}건")
    _out(lines, "\n### 케이스 목록\n")
    _out(lines, "| ID | category | 질문 |")
    _out(lines, "|----|----------|------|")
    for row in data:
        q = (row.get("question") or "").replace("|", "/")[:55]
        _out(lines, f"| {row.get('id')} | `{row.get('expected_category')}` | {q} |")


def main() -> None:
    lines: list[str] = [
        "# 데이터셋 요약 (자동 생성)\n",
        "출처: AI Hub K-Culture 관광 일본어 코퍼스 → `data/processed/tour_knowledge.jsonl`\n",
        "생성: `python scripts/analyze_dataset.py`\n",
    ]
    analyze_jsonl(ROOT / "data/processed/tour_knowledge.jsonl", lines)
    for p in [
        ROOT / "evaluation/data/tour_eval.json",
        ROOT / "data/evaluation/tour_eval.json",
    ]:
        if p.exists():
            analyze_eval_json(p, lines)
    p = ROOT / "evaluation/scripts/test_dataset.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        _out(lines, f"\n## {p.relative_to(ROOT).as_posix()} ({len(data)}건, Ragas ground_truth)\n")
        _out(lines, "| ID | 질문 (요약) |")
        _out(lines, "|----|------------|")
        for row in data:
            q = (row.get("question") or "").replace("|", "/")[:50]
            _out(lines, f"| {row.get('id')} | {q} |")
    seen = ROOT / "evaluation/data/tour_eval_seen.json"
    unseen = ROOT / "evaluation/data/tour_eval_unseen.json"
    if seen.exists() and unseen.exists():
        s = json.loads(seen.read_text(encoding="utf-8"))
        u = json.loads(unseen.read_text(encoding="utf-8"))
        _out(lines, f"\n## 평가 분할 (누수 감사)\n")
        _out(lines, f"- **SEEN** (few-shot 노출): {', '.join(r['id'] for r in s)}")
        _out(lines, f"- **UNSEEN** (실제 점수용): {', '.join(r['id'] for r in u)}")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWritten: {OUT_MD}")


if __name__ == "__main__":
    main()
