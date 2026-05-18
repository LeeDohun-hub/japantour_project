# 평가 누수(Leakage) 감사 가이드

## 개요

평가 누수(Evaluation Leakage)란 평가 케이스의 질문이 모델 프롬프트의 few-shot 예시에 노출되어
분류·생성 점수가 실제 역량보다 높게 나오는 현상입니다.

본 프로젝트에서는 두 곳에 few-shot 예시가 있습니다.

| 파일 | 역할 | few-shot 수 |
|------|------|------------|
| `src/chain/router.py` — `_CLASSIFIER_SYSTEM` | 프로덕션 분류기 (실제 사용) | 23개 |
| `src/chain/prompts.py` — `CLASSIFIER_SYSTEM` | LangChain 파이프라인용 (레거시) | 5개 |

---

## 누수 판정 기준

`audit_eval_leakage.py` 는 네 가지 기준을 순서대로 검사합니다.

| 우선순위 | 유형 | 설명 |
|---------|------|------|
| 1 | `exact` | 질문 문자열이 few-shot과 완전히 일치 |
| 2 | `substring` | few-shot이 질문의 부분 문자열 (또는 역방향) |
| 3 | `keyword_overlap` | 의미 토큰 ≥2개 겹치고 few-shot 토큰의 ≥60% 포함 (동일 언어) |
| 4 | `keyword_overlap_cross_lang` | 한↔일 번역 매핑 후 동일 조건 충족 |

---

## 감사 결과 (2026-05 기준)

### SEEN 케이스 (4건) — 누수 심각도 분류

| 심각도 | 설명 |
|--------|------|
| **critical** | `ground_truth` / `expected_*` 값이 생성 단계에 입력됨 — **해당 없음** |
| **eval_bias** | 질문이 few-shot 예시에 노출 → 분류 점수 과대 가능성 있음 |
| **benign** | 문서 수준 노출만 (생성/분류에 직접 영향 없음) — **해당 없음** |

> **이 프로젝트의 모든 SEEN 케이스는 `eval_bias`** — `ground_truth`는 생성에 절대 입력되지 않으며 Ragas 평가 단계에서만 reference로 사용됩니다.

| ID | 질문 | 탐지 유형 | 심각도 | 매칭 few-shot |
|----|------|-----------|--------|--------------|
| T001 | 성수동 맛집 추천해줘 | `exact` | **eval_bias** | "성수동 맛집 추천해줘" (router.py + prompts.py) |
| T002 | 한국 식당 예절 알려줘 | `substring` | **eval_bias** | "한국 식당 예절" (router.py) |
| T003 | 명동에서 쇼핑하기 좋은 곳이 뭐야 | `keyword_overlap_cross_lang` | **eval_bias** | "明洞でショッピング" (router.py) |
| T006 | 겨울 서울 여행 옷차림 알려줘 | `keyword_overlap_cross_lang` | **eval_bias** | "冬のソウルで服装は？" (router.py + prompts.py) |

→ `evaluation/data/tour_eval_seen.json`

### UNSEEN 케이스 (8건)

T004, T005, T007, T008, T009, T010, T011, T012

→ `evaluation/data/tour_eval_unseen.json`

---

## T004 특수 주의사항

`"제주도에서 하루 여행 코스 추천해줘"` (expected: `itinerary`)

few-shot에 `"제주도 여행" → leisure` 가 존재합니다. 이는 **누수가 아니라 충돌**입니다.

- 질문 자체가 few-shot에 없으므로 UNSEEN 분류
- 그러나 분류기가 `"제주도 여행"` 패턴을 학습하여 `leisure`로 분류할 가능성 있음
- 실제 평가에서 T004가 `leisure`로 잘못 분류되면 **few-shot 충돌에 의한 오류** 가능성 검토 필요

권장 조치: few-shot에 `"제주도에서 하루 여행 코스" → itinerary` 예시 추가.

---

## 파일 구조

```
evaluation/
├── data/
│   ├── tour_eval.json              # 전체 12건 (원본)
│   ├── tour_eval_seen.json         # 4건 — few-shot 노출 케이스
│   └── tour_eval_unseen.json       # 8건 — 기본 eval 기준
├── scripts/
│   ├── audit_eval_leakage.py       # 누수 감사 스크립트
│   ├── test_dataset.json           # 12건 + ground_truth (Ragas용)
│   ├── evaluate_router.py          # 분류 정확도 평가 (--dataset 플래그)
│   ├── evaluate_router_rag.py      # 프로덕션 full pipeline 평가 (route_and_answer)
│   ├── evaluate_router_ragas.py    # Ragas 평가 — route_and_answer() 기반 (프로덕션 경로)
│   ├── benchmark_vector_backends.py  # 벡터 검색 품질 벤치마크 (기본: pgvector)
│   └── run_full_eval.py            # 통합 실행 오케스트레이터
└── docs/
    └── EVAL_LEAKAGE.md             # 이 문서
```

---

## 실행 방법

```powershell
cd c:\WorkSpace\japantour_project

# (1) 통합 평가 — 기본 (Ragas 포함)
python -m evaluation.scripts.run_full_eval

# (2) Ragas 제외 (OpenAI 비용 절감)
python -m evaluation.scripts.run_full_eval --skip-ragas

# (3) compare_optimizations도 제외
python -m evaluation.scripts.run_full_eval --skip-ragas --skip-compare

# (4) production 모드 벡터 벤치마크 포함
python -m evaluation.scripts.run_full_eval --production
```

개별 실행:

```powershell
# 누수 감사 (누수 발견 시 exit 1)
python -m evaluation.scripts.audit_eval_leakage --strict

# 분류만 (unseen, 빠름)
python -m evaluation.scripts.evaluate_router --dataset unseen --no-answer

# 분류+답변 (unseen)
python -m evaluation.scripts.evaluate_router --dataset unseen

# 프로덕션 full pipeline
python -m evaluation.scripts.evaluate_router_rag --dataset unseen --check-reply-keywords

# 벡터 벤치마크 (pgvector 기준, 기본값)
python -m evaluation.scripts.benchmark_vector_backends --top-k 5

# 벡터 벤치마크 (production 모드 포함)
python -m evaluation.scripts.benchmark_vector_backends --top-k 5 --production

# Ragas — route_and_answer() 기반 프로덕션 경로 (권장)
python -m evaluation.scripts.evaluate_router_ragas --dataset unseen

# Ragas — rag_chain.py 경로 (레거시, KB 미연결)
python -m evaluation.scripts.evaluate_single --config baseline
python -m evaluation.scripts.evaluate_only
```

---

## 해석 주의사항

### 1. Seen vs Unseen

| 데이터셋 | 의미 |
|---------|------|
| `seen` (T001·T002·T003·T006) | few-shot 노출 → 분류 점수 **과대** 가능 |
| `unseen` (T004·T005·T007–T012) | 실제 역량 측정 기준 ← **기본 eval** |

### 2. Oracle vs Production (벡터 벤치마크)

| 모드 | 설명 |
|------|------|
| `no_filter` | 카테고리 필터 없음 (baseline) |
| `category` | **oracle** — expected_category 사용 (upper bound) |
| `category_area` | **oracle** — expected_category + expected_area 사용 (upper bound) |
| `production` | **실제** — 분류기 예측 카테고리 사용 (--production 플래그) |

`category`·`category_area` 점수 > `production` 점수 → 분류 오류가 검색 품질에 영향

### 3. 평가 경로 비교

| 스크립트 | 생성 경로 | Ragas 가능 | 비고 |
|---------|----------|-----------|------|
| `evaluate_single.py` | `optimized_rag_chain.py` (KB 미연결) | ✅ | 레거시, 낮은 faithfulness 예상 |
| `evaluate_router_rag.py` | `route_and_answer()` (프로덕션) | ❌ | 분류/RAG 정확도만 측정 |
| `evaluate_router_ragas.py` | `route_and_answer()` (프로덕션) | ✅ | **권장** — 실제 파이프라인 + Ragas |

`evaluate_router_ragas.py`는 생성에 `ground_truth`를 절대 입력하지 않으며, Ragas `reference` 필드에만 사용합니다.

---

## Few-shot 업데이트 시 주의

새 few-shot 예시를 추가하거나 기존을 수정할 때:

1. `python -m evaluation.scripts.audit_eval_leakage --strict` 재실행
2. SEEN/UNSEEN 분류가 변경되면 `tour_eval_seen.json`·`tour_eval_unseen.json` 업데이트
3. 이 문서의 "감사 결과" 표도 업데이트
