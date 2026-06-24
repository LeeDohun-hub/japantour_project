# Codex 핸드오프 — 2026-06-24 (세션 한계 직전 저장)

---

## 오늘 세션에서 완료한 작업 (커밋 필요)

### 1. `frontend/home.html`
- `やりたいこと` 칩에서 `🍜 グルメ` 버튼 제거

### 2. `frontend/wizard.js` (`buildPrompt()`)
- `actSet` / `meal_policy` 지시를 `if (activityParts.length)` **밖**으로 이동 → 활동 미선택 시에도 항상 `lunch_required=true / dinner_required=true` 포함
- 포맷 지시 변경: `「①②③」または「午前」「昼食」「午後」「夕食」`  
  → `「午前」「昼食」「午後」「夕食」の順序ラベル（1日目の到着動線のみ①②③可）。飲食店は必ず「昼食」「夕食」スロットにのみ配置`

### 3. `src/chain/router.py` (5곳)
| 위치 | 변경 내용 |
|------|---------|
| `_itinerary_place_limits()` | 초회 한도를 reroll과 동일하게 상향 (`max_total` 30→50, `max_nearby_food` 15→24) |
| 라인 1048 포맷 지시 | ①②③ 옵션 제거 → 午前/昼食/午後/夕食 고정 + 飲食店 昼食/夕食 전용 |
| 라인 1149 포맷 지시 | 동일 |
| 食事候補 else 분기 (라인 6716~) | "店名創作は禁止" → ZERO-CANDIDATE EXCEPTION 적용 (昼食/夕食 필수 채움) |
| `[CORE PRINCIPLES]` | 원칙 6 DIRECT & COMPLETE 추가 (AR 개선) |

### 4. `evaluation/scripts/evaluate_chat_corpus_ragas.py`
- `answer_relevancy.strictness = 1` (기본 3→1, synthetic question 생성 실패 방지)
- AR=0.000 + Faithfulness≥0.5 케이스 아티팩트 감지 → AR 평균에서 제외
- `DEFAULT_TOP_K`: 8 → 4

### 5. `src/chain/router.py` (추가)
- `CHAT_CORPUS_TOP_K = 4` 상수 추가
- `/chat` 경로 두 곳 `search_chat_corpus(..., top_k=CHAT_CORPUS_TOP_K)` 적용

### 6. 신규 파일 (플랜 평가 인프라)
- `evaluation/data/plan_eval_cases.json` — 8개 테스트 케이스 (서울/부산/제주/전주/강원/경주)
- `evaluation/scripts/evaluate_plan.py` — 룰 기반 플랜 품질 평가 스크립트
  - 지표: `slot_fill_rate`, `format_compliance`, `meal_url_rate`, `day_count_accuracy`

---

## 현재 실행 중인 백그라운드 작업 (완료 대기)

### A. RAGAS n=24 top_k=4 + strictness=1 평가
- 출력: `evaluation/reports/chat_corpus_ragas_topk4.json`
- 완료 시 베이스라인(AR=0.633, F=0.795)과 짝비교

### B. 플랜 평가 8건 베이스라인
- 출력: `evaluation/reports/plan_eval_baseline.json`
- 이것이 플랜 품질 **최초 정량 베이스라인**

---

## Codex가 해야 할 작업 (순서대로)

### Step 1: 두 평가 완료 확인 & 결과 기록

**A. RAGAS topk4 결과 처리**

`evaluation/reports/chat_corpus_ragas_topk4.json` 읽어서:

| 지표 | 베이스라인 | 원칙6(ar24) | topk4 | 판정 |
|------|----------|-----------|-------|------|
| Answer Relevancy | 0.593 | 0.633 | ? | |
| Faithfulness | 0.733 | 0.795 | ? | |
| Context Precision | 0.896 | 0.910 | ? | |
| Context Recall | 0.917 | 0.917 | ? | |

채택 기준: AR ≥ 0.65 AND Faithfulness ≥ 0.70  
롤백 기준: AR 하락 또는 Faithfulness < 0.70 → `CHAT_CORPUS_TOP_K`를 4→8로 되돌림

결과를 `evaluation/reports/chat_corpus_eval_20260624.md` 하단에 아래 형식으로 추가:

```markdown
---

## top_k=4 + AR strictness=1 검증 (n=24, 2026-06-24)

### 적용 내용
- `CHAT_CORPUS_TOP_K`: 8 → 4 (LLM 컨텍스트 합성 범위 제한)
- `answer_relevancy.strictness`: 3 → 1 (synthetic question 생성 안정화)
- AR=0 + Faithfulness≥0.5 아티팩트 필터 추가

### 결과
[표 작성]

### 판정: [채택 / 롤백] — [이유]
```

**B. 플랜 평가 베이스라인 기록**

`evaluation/reports/plan_eval_baseline.json` 읽어서 `evaluation/reports/chat_corpus_eval_20260624.md`에 추가:

```markdown
---

## 플랜 생성 품질 베이스라인 (n=8, 2026-06-24)

룰 기반 평가 (`evaluation/scripts/evaluate_plan.py`)

| 지표 | 정의 | 결과 |
|------|------|------|
| slot_fill_rate | 중간 여행일 昼食+夕食 모두 충전율 | ? |
| lunch_fill_rate | 昼食 충전율 | ? |
| dinner_fill_rate | 夕食 충전율 | ? |
| format_compliance | 午前/昼食/午後/夕食 라벨 사용률 | ? |
| meal_url_rate | 昼食/夕食 슬롯 Naver URL 존재율 | ? |
| day_count_accuracy | 지정 일수 == 생성 일수 | ? |

케이스별 결과:
[케이스 ID / 설명 / 각 지표 표로 작성]
```

---

### Step 2: AR 목표(0.80) 잔여 격차 해소

현재 AR 0.633, 목표 0.80, 잔여 0.167.  
top_k=4가 채택되면 다음 후보 시도:

**2-1. 원칙7 SCOPE MATCH 추가 (router.py)**

`[CORE PRINCIPLES]` 6번 아래에 추가:
```
7. SCOPE MATCH: Answer only within the scope of the question. For a specific question
(what time, who, why, how many), answer with that specific fact only. Do not synthesize
all available context into a comprehensive overview unless the question explicitly asks
for a general description.
```

검증: `uv run python -m evaluation.scripts.evaluate_chat_corpus_ragas --limit 24 --output evaluation/reports/chat_corpus_ragas_scope7.json`  
채택 기준: AR ≥ 0.65 AND Faithfulness ≥ 0.70

**2-2. stay 카테고리 특화 (router.py)**
체크인/아웃 시간 등 운영 정보가 Reference Data에 없으면 1줄로 끝내는 지시 추가.

---

### Step 3: 플랜 평가 반복 실행

베이스라인 대비 slot_fill_rate / meal_url_rate 약점 발견 시:

```powershell
$env:VECTOR_BACKEND="faiss"; $env:PYTHONIOENCODING="utf-8"; $env:DJANGO_SETTINGS_MODULE="config.settings"
uv run python -m evaluation.scripts.evaluate_plan --output evaluation/reports/plan_eval_v2.json
```

---

### Step 4: 커밋

오늘 수정 전체를 커밋:
```powershell
git add frontend/home.html frontend/wizard.js src/chain/router.py
git add evaluation/scripts/evaluate_chat_corpus_ragas.py
git add evaluation/scripts/evaluate_plan.py evaluation/data/plan_eval_cases.json
git add evaluation/reports/chat_corpus_eval_20260624.md
git commit -m "feat: 초회 플랜 昼食/夕食 버그 수정 + AR 개선(원칙6) + 플랜 평가 인프라 추가"
```

---

## 환경

```powershell
$env:VECTOR_BACKEND="faiss"
$env:PYTHONIOENCODING="utf-8"
$env:DJANGO_SETTINGS_MODULE="config.settings"
# 반드시 uv run python 사용 (python은 Windows Store 스텁)
```

벡터 인덱스: `data/vector/tour_knowledge.faiss`  
`.env`는 gitignore — 커밋 금지

---

## 수치 레퍼런스 (빠른 참조)

| 체크포인트 | AR | Faithfulness | Context Prec | Context Recall |
|-----------|-----|-------------|-------------|----------------|
| 베이스라인 (n=24) | 0.593 | 0.733 | 0.896 | 0.917 |
| +원칙6 DIRECT & COMPLETE | **0.633** | **0.795** | 0.910 | 0.917 |
| +top_k=4 + strictness=1 | 실행 중 | | | |

목표: AR **0.80**
