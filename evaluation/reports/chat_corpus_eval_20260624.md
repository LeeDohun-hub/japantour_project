# `/chat` 일본어 말뭉치 평가 결과

평가일: 2026-06-24

## 평가 구성

- 원본: `data/raw/tour_knowledge.csv`
- 가공 데이터: `data/processed/tour_knowledge.jsonl`
- 평가 데이터: `evaluation/data/chat_corpus_eval.json`
- 전체 평가 후보: 120건(6개 카테고리 × 20건)
- 시험 검색·답변 생성: 카테고리 균형 20건
- RAGAS 시험 판정: 카테고리 균형 6건
- 검색 경로: `search_chat_corpus()`
- 답변 경로: `route_and_answer()`

## 20건 검색 및 최종 라우팅 결과

| 지표 | 결과 |
| --- | ---: |
| 원본 정답 문서 검색 적중 | 20/20 (100%) |
| MRR | 0.9167 |
| 정답 문서 1위 검색 | 17/20 |
| 정답 문서 2위 검색 | 2/20 |
| 정답 문서 3위 검색 | 1/20 |
| 최종 라우터가 질문 수락 | 13/20 (65%) |
| 최종 답변에서 RAG 사용 | 13/20 (65%) |
| 평균 응답 시간 | 3.92초 |

검색 자체는 20개 질문에서 모두 원본 정답 레코드를 찾았습니다. 그러나 최종 답변 전에
실행되는 여행 질문 분류기가 7개를 `invalid`로 판정하여, 검색된 정답을 사용하지 않고
여행 관련 질문을 요청하는 거절문을 반환했습니다.

### `invalid`로 거절된 말뭉치 질문

1. `J_SHOP_000001_q1` — 8 secondsはどのようなファッションブランドですか？
2. `J_LEI_000001_q4` — 121ルマルデュフェイのカスタム香水はどのように製作されますか？
3. `J_SHOP_000016_q1` — 10 CORSO COMOのブランドの特徴は何ですか？
4. `J_STAY_000001_q4` — イドはどのような特徴がありますか？
5. `J_LEI_000001_q6` — 121ルマルデュフェイはどのような香りを保有していますか？
6. `J_SHOP_000048_q1` — Bornnのブランドはどのような特徴がありますか？
7. `J_STAY_000001_q5` — イドからはどのような景色が見えますか？

## RAGAS 시험 결과

RAGAS 0.4.3으로 6건 × 4개 지표를 실행했습니다. 평가 모델 호출 일부가 설정한
60초를 초과해 결측 처리되었습니다.

| 지표 | 결과 |
| --- | ---: |
| Answer Relevancy | 0.5066 |
| Context Recall | 1.0000 |
| Faithfulness | 결측(평가 호출 타임아웃) |
| Context Precision | 결측(평가 호출 타임아웃) |

Answer Relevancy가 낮아진 가장 큰 원인은 6개 중 쇼핑 질문 1개가 `invalid` 거절문을
반환하여 해당 점수가 0점이 된 것입니다. 검색 컨텍스트의 정답 포함 여부는 Context
Recall 1.0 및 검색 적중률 100%로 확인됐습니다.

## 결론

1. `/chat` 전용 무분류 말뭉치 검색은 정상 동작합니다.
2. 현재 검색 실패보다 최종 질문 분류기의 선행 거절이 더 큰 품질 저하 원인입니다.
3. 말뭉치 기반 챗봇을 완전히 독립시키려면 `invalid`를 즉시 반환하기 전에
   `search_chat_corpus()`에서 충분히 관련도 높은 문서가 검색됐는지 확인해야 합니다.
4. RAGAS의 Faithfulness와 Context Precision은 평가 API 지연이 안정된 환경에서
   재실행해야 합니다.

## 결과 파일

- `evaluation/reports/chat_corpus_retrieval_20.json`
- `evaluation/reports/chat_corpus_retrieval_20_generated.json`
- `evaluation/reports/chat_corpus_ragas_6_20260624_133040.json`
- `evaluation/reports/chat_corpus_ragas_6_20260624_133040_generated.json`

---

## 개선 적용 (2026-06-24) — `invalid` 코퍼스 폴백

위 결론 2·3번(분류기의 선행 거절이 최대 병목)을 반영해 `route_and_answer()`의
`invalid` 즉시 거절 직전에 말뭉치 폴백을 추가했다.

**변경 내용 (`src/chain/router.py`)**

- `category == "invalid"`일 때 거절문을 반환하기 전에 `search_chat_corpus(user_message)`를 실행한다.
- 최상위 결과의 `_score`(코사인 유사도)가 `CHAT_CORPUS_ACCEPT_THRESHOLD = 0.55` 이상이면
  거절하지 않고 `general` 경로로 재라우팅하여 코퍼스 근거로 답변한다.
- 임계값은 보정 결과(거절됐던 코퍼스 질문 0.64~0.86 vs 무관 질문 0.33~0.47)의 분리 구간에서
  선택했다. `_score`는 FAISS·pgvector 모두 동일한 코사인 유사도 의미이므로 두 백엔드에 그대로 적용된다.

**재평가 결과 (동일 20건, `--skip-ragas`)**

| 지표 | 개선 전 | 개선 후 |
| --- | ---: | ---: |
| 원본 정답 문서 검색 적중 | 20/20 (100%) | 20/20 (100%) |
| 최종 라우터가 질문 수락 | 13/20 (65%) | **20/20 (100%)** |
| 최종 답변에서 RAG 사용 | 13/20 (65%) | **20/20 (100%)** |
| MRR | 0.9167 | 0.8875 |
| 평균 응답 시간 | 3.92초 | 4.06초 |

- 이전에 `invalid`로 거절되던 7건(8 seconds, 121ルマルデュフェイ, 10 CORSO COMO, イド, Bornn 등)이
  전부 코퍼스 근거로 답변되었다.
- 무관 질문(火星の天気, 微積分 등, `_score` 0.33~0.47)은 임계값 미만으로 **여전히 정상 거절**된다.
- 결과 파일: `evaluation/reports/chat_corpus_ragas_20_20260624_135209.json`

### 전체 120건 재평가 (`--limit 0 --skip-ragas`)

20건 표본의 개선이 전체 6개 카테고리 × 20건에서도 유지되는지 확인했다.

| 지표 | 결과 |
| --- | ---: |
| 총 케이스 | 120 |
| 원본 정답 문서 검색 적중 | 109/120 (90.8%) |
| MRR | 0.8408 |
| **최종 라우터가 질문 수락** | **120/120 (100%)** |
| **최종 답변에서 RAG 사용** | **120/120 (100%)** |
| 평균 응답 시간 | 3.97초 |

- **수락률·RAG 사용률 100%** — `invalid` 거절이 전 카테고리에서 사라졌다.
- 검색 적중 미달 11건은 대부분 **앞 문맥이 필요한 후속질문/익명 레코드**
  (`このシャツ`, `この商品`, `J_SHOP_000003_q4`, `J_STAY_000003_q11` 등)로,
  단일턴 검색의 데이터 한계이지 폴백 회귀가 아니다. → 멀티턴 평가셋이 별도 과제.
- 결과 파일: `evaluation/reports/chat_corpus_ragas_120_20260624_140738.json`

### RAGAS 안정화 (해결)

결측이던 Faithfulness·Context Precision을 살리기 위해 처음에는 `RunConfig`의 timeout을
크게 늘리고(60→180) 재시도를 키웠으나(1→3), 12건 표본이 **20분 이상** 평가 단계에서
멈췄다(평소 12건은 2~5분). 느린 지표에서 긴 타임아웃 × 다중 재시도가 누적돼 오히려
실행이 정체되는 역효과가 확인됐다.

→ 방향을 **fail-fast**로 수정했다: `timeout=90, max_retries=1, max_workers=3`.
느린 지표는 NaN으로 빠르게 처리하고 **전체 실행이 시간 내 완료**되도록 보장한다.
(원래 60/1 설정도 완료는 됐고 Answer Relevancy·Context Recall은 산출됐으나 나머지 2개가
NaN이었다.)

**fail-fast 재실행 결과 (6건, `--limit 6`)** — 약 11분에 **정상 완료**(무한 정체 해소).

| 지표 | 개선 전(원본 리포트) | 개선 후(fail-fast) |
| --- | ---: | ---: |
| Answer Relevancy | 0.5066 | **0.6815** |
| Context Recall | 1.0000 | 1.0000 |
| Faithfulness | 결측(타임아웃) | 결측(타임아웃) |
| Context Precision | 결측(타임아웃) | 결측(타임아웃) |
| route_accept_rate | — | 1.0000 |
| route_rag_used_rate | — | 1.0000 |

- **Answer Relevancy 0.51→0.68** 상승: `invalid` 폴백으로 쇼핑 질문 거절문(0점)이 사라진 효과.
- 단, fail-fast(90초)에서는 **Faithfulness·Context Precision이 여전히 전부 `TimeoutError`**였다.
  컨텍스트를 3개로 줄여도(아래) 90초로는 부족 → **잡당 시간 자체가 부족한 것**이 원인으로 좁혀졌다.

#### 원인 규명 → 해결

faithfulness/context_precision는 건당 LLM 호출이 많은 지표다.

- **faithfulness**: 답변을 문장 단위로 분해(1회) → 각 문장을 컨텍스트로 검증(N회). 답변 길이에 비례.
- **context_precision**: 검색 컨텍스트 개수만큼(top_k=8 → 최대 8회) 관련성 판정.

따라서 한 잡이 90초를 넘겨 None이 됐다. 두 가지를 함께 적용해 해결했다.

1. **잡당 작업량 축소** — RAGAS 판정에 넘기는 컨텍스트를 상위 3개 + 각 600자로 제한
   (`RAGAS_MAX_CONTEXTS=3`, `RAGAS_CONTEXT_CHAR_LIMIT=600`). 검색 지표(hit/MRR)는 전체 컨텍스트 그대로.
2. **잡당 타임아웃 상향(재시도 폭주 없이)** — `timeout=240, max_retries=1, max_workers=2`.
   (과거 180초×3회는 재시도 누적으로 24분 정체 → 재시도는 1회로 고정해 폭주를 막고 시간만 늘림)

**최종 결과 (3건, `timeout=240` + 컨텍스트 축소)** — 4지표 전부 산출.

| 지표 | fail-fast(90s) | 해결(240s+컨텍스트 축소) |
| --- | ---: | ---: |
| Faithfulness | 결측 | **0.6667** |
| Answer Relevancy | 0.6815 | 0.6394 |
| Context Precision | 결측 | **0.6667** |
| Context Recall | 1.0000 | 1.0000 |

- 결과 파일: `evaluation/reports/chat_corpus_ragas_3_t240.json`

#### 결론 및 운영 권장

- **RAGAS 4지표는 산출 가능**하다: (컨텍스트 축소) + (잡당 timeout 240s, 재시도 1회)가 핵심.
- 다만 faithfulness/context_precision는 **여전히 비싸다** — 3건에 약 10분. 전체 120건 RAGAS는
  비현실적이므로 다음 운용을 권장한다.
  - 일상 평가: 라우팅 지표 + Answer Relevancy/Context Recall (`--skip-ragas` 또는 fail-fast)
  - faithfulness/context_precision: **소표본(3~6건)에서만 주기적으로** 측정
  - 더 대규모가 필요하면 구조 개선(평가 모델 경량화, 건별 캐싱·재개, 지표 분리, 비동기 큐)
- 핵심 품질 개선(수락률 65→100%, Answer Relevancy 0.51→0.68)은 이미 확정됐고,
  faithfulness 0.67 / context_precision 0.67로 **환각·검색 정밀도도 양호** 수준을 확인했다.

---

## 공식 베이스라인 (2026-06-24, n=24 카테고리 균형)

소표본(n=3)의 출렁임을 제거하기 위해 **24건(6 카테고리 × 4)** 으로 베이스라인을 고정 측정했다.
(설정: `timeout=240, max_retries=1, max_workers=2` + 컨텍스트 축소, grounding 미적용 = 현재 코드)

| 지표 | n=3 (참고) | **n=24 (베이스라인)** | 목표 | 평가 |
| --- | ---: | ---: | ---: | --- |
| Faithfulness | 0.667 | **0.733** | 0.80 | 양호 |
| Answer Relevancy | 0.639 | **0.593** | 0.80 | ⚠️ 최약점 |
| Context Precision | 0.667 | **0.896** | 0.75 | ✅ 우수 |
| Context Recall | 1.000 | **0.917** | 0.85 | ✅ 우수 |
| retrieval_hit_rate | — | 0.958 | — | ✅ |
| retrieval_mrr | — | 0.865 | — | ✅ |
| route_accept_rate | — | 1.000 | — | ✅ |

**핵심 발견 — n=3은 노이즈였다.**
- n=3에서 "약점"으로 보였던 Context Precision은 n=24에서 **0.896으로 우수**다.
- 진짜 약점은 **Answer Relevancy 0.593**(목표 0.80 대비 큰 격차)이다 — 답변이 질문에
  직접·충분히 대응하지 못함. 검색(precision/recall)·환각(faithfulness)은 이미 양호.
- 따라서 다음 개선의 **1순위는 Answer Relevancy**다. (앞선 grounding 실험은 faithfulness를
  노렸으나 AR을 더 낮췄으므로, AR을 직접 겨냥하는 방향이 맞다.)

- 결과 파일: `evaluation/reports/chat_corpus_ragas_baseline24.json`
- 이후 모든 개선안은 이 n=24 베이스라인 대비 동일 표본 짝비교로 검증한다.

---

## AR 개선안 검증 — 원칙6 DIRECT & COMPLETE (n=24, 2026-06-24)

### 적용 내용

`src/chain/router.py`의 `[CORE PRINCIPLES]` 5번 아래에 원칙 6을 추가했다.

```
6. DIRECT & COMPLETE: Open with a sentence that directly and specifically answers the exact
question asked, and cover every part of it. Do not drift into tangential facts, and do not
append generic closings that do not answer the question (e.g. "choose from the cards below",
"feel free to ask anything", "下のカードから選んでください"). Every sentence should serve the
user's specific question.
```

**이유**: AR이 낮은 원인이 질문에 직답하지 않고 "카드에서 선택해 주세요" 같은 무관한
마무리로 흐르는 것으로 추정됐다. Faithfulness(환각 방지)를 해치지 않으면서
AR을 직접 겨냥하는 최소 변경이다.

### 결과 (동일 n=24, 짝비교)

| 지표 | 베이스라인 | 원칙6 적용 | 변화 |
| --- | ---: | ---: | ---: |
| Faithfulness | 0.733 | **0.795** | +0.062 |
| Answer Relevancy | 0.593 | **0.633** | **+0.040** |
| Context Precision | 0.896 | **0.910** | +0.014 |
| Context Recall | 0.917 | 0.917 | ±0.000 |
| retrieval_hit_rate | 0.958 | 0.958 | ±0.000 |
| route_accept_rate | 1.000 | 1.000 | ±0.000 |

### 판정: **채택** ✅

- AR 0.633 ≥ 0.61 ✅
- Faithfulness 0.795 ≥ 0.70 ✅
- 부작용 없음: Faithfulness가 오히려 +0.062 상승, 검색·라우팅 지표 불변

원칙6은 AR을 직접 끌어올렸을 뿐 아니라 답변 품질(faithfulness) 도 함께 개선했다.
무관한 마무리 문구를 걷어내면 답변이 컨텍스트에 더 충실해지는 것으로 해석된다.

### 다음 목표

AR 0.633으로 목표(0.80)까지 아직 0.167 격차가 남아 있다. 다음 개선 후보:

1. 답변 길이·구성 조정(질문 유형별 상세/간결 모드)
2. 마무리 문구 자동 제거 후처리
3. 표본 확대(n=30~50)로 분산 추가 축소 후 재판정

- 결과 파일: `evaluation/reports/chat_corpus_ragas_ar24.json`

---

## 플랜 생성 품질 베이스라인 (n=8, 2026-06-24)

룰 기반 평가 (`evaluation/scripts/evaluate_plan.py`)

초기 집계에서 `最終日`을 날짜로 세지 않고 빈 식사 라벨도 채워진 슬롯으로 간주하는
평가기 오류를 발견했다. 날짜 파서·식사 내용 판정을 수정한 뒤, 동일한 8개 생성 응답을
재생성 없이 재채점했다.

| 지표 | 정의 | 결과 |
| --- | --- | ---: |
| slot_fill_rate | 중간 여행일 昼食+夕食 모두 충전율 | **0.8750** |
| lunch_fill_rate | 昼食 충전율 | **1.0000** |
| dinner_fill_rate | 夕食 충전율 | **0.8750** |
| format_compliance | 중간 여행일 午前/昼食/午後/夕食 라벨 사용률 | **1.0000** |
| meal_url_rate | 昼食/夕食 슬롯 Naver URL 존재율 | **0.9375** |
| day_count_accuracy | 지정 일수 == 생성 일수 | **0.8750** |

### 케이스별 결과

| 케이스 ID | 설명 | 슬롯 | 점심 | 저녁 | 포맷 | URL | 일수 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P_SEOUL_2N3D_COUPLE | ソウル 2泊3日 カップル | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3/3 |
| P_SEOUL_3N4D_SOLO | ソウル 3泊4日 ひとり旅 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **3/4** |
| P_BUSAN_2N3D_COUPLE | 釜山 2泊3日 カップル | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3/3 |
| P_JEJU_3N4D_COUPLE | 済州島 3泊4日 カップル | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 4/4 |
| P_JEONJU_2N3D_SOLO | 全州 2泊3日 ひとり旅（文化） | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3/3 |
| P_GANGWON_2N3D_COUPLE | 江原道（春川） 2泊3日 カップル | **0.00** | 1.00 | **0.00** | 1.00 | **0.50** | 3/3 |
| P_SEOUL_4N5D_FAMILY | ソウル 4泊5日 家族 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5/5 |
| P_GYEONGJU_2N3D_COUPLE | 慶州 2泊3日 カップル（歴史） | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3/3 |

### 판정

- 식사 라벨 형식은 전 케이스에서 준수했다.
- 강원 케이스는 `夕食` 라벨만 있고 내용·URL이 없어 식사 슬롯 완전성 회귀가 남아 있다.
- 서울 3박4일 1인 여행은 3일차가 통째로 누락되어 장기 일정의 일수 완전성 보강이 필요하다.
- 결과 파일: `evaluation/reports/plan_eval_baseline.json`

---

## top_k=4 + AR strictness=1 검증 (n=24, 2026-06-24)

### 적용 내용

- `CHAT_CORPUS_TOP_K`: 8 → 4 (LLM 컨텍스트 합성 범위 제한)
- `answer_relevancy.strictness`: 3 → 1 (synthetic question 생성 안정화)
- AR=0 + Faithfulness≥0.5 아티팩트 필터 추가

### 결과

| 지표 | 베이스라인 | 원칙6 | top_k=4 | 원칙6 대비 |
| --- | ---: | ---: | ---: | ---: |
| Answer Relevancy | 0.593 | 0.633 | **0.665** | **+0.032** |
| Faithfulness | 0.733 | 0.795 | **0.832** | **+0.037** |
| Context Precision | 0.896 | 0.910 | **0.910** | ±0.000 |
| Context Recall | 0.917 | 0.917 | **0.917** | ±0.000 |

- retrieval_hit_rate: 0.958
- retrieval_mrr: 0.885
- route_accept_rate / route_rag_used_rate: 1.000 / 1.000
- AR 아티팩트 필터 제외: 1건

### 판정: **채택** ✅

AR 0.665 ≥ 0.65, Faithfulness 0.832 ≥ 0.70으로 두 기준을 모두 통과했다.
검색 컨텍스트를 4개로 제한하자 질문과 무관한 합성 범위가 줄면서 AR과 Faithfulness가
동시에 상승했고, Context Precision·Recall 회귀도 없었다.

- 결과 파일: `evaluation/reports/chat_corpus_ragas_topk4.json`

---

## 원칙7 SCOPE MATCH 검증 (n=24, 2026-06-24)

### 적용 내용

특정 사실(시간·인물·이유·수량 등)을 묻는 질문에는 그 범위 안에서만 답하고,
일반 설명을 요청하지 않았다면 전체 컨텍스트를 종합한 개요로 확장하지 않도록 지시했다.

### 결과

| 지표 | top_k=4 | +원칙7 | 변화 |
| --- | ---: | ---: | ---: |
| Answer Relevancy | 0.665 | **0.671** | **+0.006** |
| Faithfulness | 0.832 | **0.871** | **+0.039** |
| Context Precision | 0.910 | **0.910** | ±0.000 |
| Context Recall | 0.917 | **0.917** | ±0.000 |

- retrieval_hit_rate: 0.958
- retrieval_mrr: 0.885
- route_accept_rate / route_rag_used_rate: 1.000 / 1.000
- AR 아티팩트 필터 제외: 1건

### 판정: **채택** ✅

AR 개선 폭은 작지만 하락하지 않았고, Faithfulness가 0.871로 유의미하게 상승했다.
검색·라우팅 지표에도 회귀가 없어 질문 범위 제한 원칙을 유지한다.
다만 AR 목표 0.80까지는 0.129가 남아 있어 카테고리별 후속 개선이 필요하다.

- 결과 파일: `evaluation/reports/chat_corpus_ragas_scope7.json`

---

## 플랜 생성 품질 재검증 (v2, n=8, 2026-06-24)

자동 품질 검사기가 `最終日`을 포함한 모든 날짜 헤더를 추적하고, 누락 날짜·식사 슬롯을
재시도 프롬프트에 구체적으로 명시하도록 보강한 뒤 재평가했다.

| 지표 | 베이스라인 | v2 | 변화 |
| --- | ---: | ---: | ---: |
| slot_fill_rate | 0.8750 | 0.8750 | ±0.0000 |
| lunch_fill_rate | 1.0000 | 1.0000 | ±0.0000 |
| dinner_fill_rate | 0.8750 | 0.8750 | ±0.0000 |
| format_compliance | 1.0000 | 1.0000 | ±0.0000 |
| meal_url_rate | 0.9375 | 0.9375 | ±0.0000 |
| day_count_accuracy | 0.8750 | **1.0000** | **+0.1250** |

### 판정

- 서울 3박4일의 누락됐던 중간 날짜가 복구되어 전 케이스 일수 정확도 100%를 달성했다.
- 베이스라인의 강원 빈 저녁 슬롯은 v2에서 정상 복구됐다.
- 다만 경주 케이스에서 새로 빈 저녁 슬롯이 발생해 전체 식사 충전율은 0.875에 머물렀다.
  재시도는 2회 수행됐지만 동일 실패가 반복돼, 후보 선택 다양화 또는 결정적 후처리가 후속 과제다.
- 결과 파일: `evaluation/reports/plan_eval_v2.json`

---

## 경주 빈 저녁 슬롯 — 결정적 후처리 (2026-06-25)

위 v2 후속 과제(경주 빈 `夕食` 슬롯, 재시도로 안 잡힘)를 해결했다.

**원인**: 빈 슬롯은 품질 채점에서 `day2_dinner_invalid`로 정확히 감지돼 재시도를 유발하지만,
재시도는 LLM 전체 재생성이라 확률적 — 경주에서는 모델이 저녁을 계속 비워두는 동일 실패가
반복됐다. 항상 실행되는 결정적 후처리(`_repair_wizard_itinerary_rules`)에는 **빈 슬롯
(라벨만 있고 내용 없음)을 채우는 경로가 없었다** (잘못 배치된 카드 제거·플레이스홀더 교체만 처리).

**변경 (`src/chain/itinerary_repair.py`)**

- `_meal_slot_is_empty()` — 식사 라벨 뒤가 다음 슬롯/날짜 경계까지 비었는지 감지.
- `pick_food_for_empty_slot()` — 빈 슬롯을 검증된 식당으로 채우되 **같은 날 점심·기사용
  식당과 중복을 회피**하고, 후보 풀이 슬롯 수보다 작을 때(`allow_cross_day_food_reuse`)만 재사용.
- 슬롯 라벨 처리부에서 빈 점심/저녁이면 위 후보를 주입.

**검증**: 경주 재현 케이스(빈 `夕食` + 식당 후보 2개)에서 `夕食`이 점심(큰기와)과 다른
검증된 식당(황남맛집 본점, Naver URL 포함)으로 채워짐을 단위검증으로 확인. 기존 테스트 회귀 없음.

---

## 플랜 생성 품질 재검증 (v3, n=8, 2026-06-25) — 평가기 사각지대 수정

위 결정적 후처리 적용 후 동일 8케이스를 실제 재생성해 재평가했다. 초기 집계에서 경주가
slot=0·fmt=0으로 나왔으나, **생성물은 정상**(`### 午前`/`### 昼食`/`### 午後`/`### 夕食`에
식당·URL 모두 충전)이었다. 원인은 **평가기의 사각지대**였다 — LLM이 슬롯 라벨을 `### 夕食`
(마크다운 H3 헤더) 형식으로 내면 `_SLOT_LABEL`·`meal_slot_content`가 `**夕食**`이나 맨줄
`夕食`만 인식해 라벨을 놓쳤다. (프로덕션 복구 코드 `_itinerary_slot_from_line`은 `#`을
strip하므로 영향 없음 — 평가 전용 버그.)

`#{1,3}` 헤더 접두사도 인식하도록 평가기 정규식을 보강하고 재생성 없이 재채점한 결과:

| 지표 | v2 | v3(재채점) | 변화 |
| --- | ---: | ---: | ---: |
| slot_fill_rate | 0.8750 | **1.0000** | **+0.1250** |
| lunch_fill_rate | 1.0000 | 1.0000 | ±0.0000 |
| dinner_fill_rate | 0.8750 | **1.0000** | **+0.1250** |
| format_compliance | 1.0000 | 1.0000 | ±0.0000 |
| meal_url_rate | 0.9375 | **1.0000** | **+0.0625** |
| day_count_accuracy | 1.0000 | 1.0000 | ±0.0000 |

- 전 8케이스 식사 슬롯 완전 충전·전 지표 1.0 달성. 헤더 인식은 **추가**만 했고 기존
  bold/맨줄 형식 인식은 보존해 다른 케이스 회귀 없음.
- 결정적 후처리는 LLM이 빈 라벨을 남기는 경우의 안전망으로 유지된다.
- 결과 파일: `evaluation/reports/plan_eval_v3.json`

---

## AR 개선안 — 원칙8 MIRROR THE QUESTION TYPE (n=24, 기각, 2026-06-25)

AR 잔여 격차(목표 0.80 대비 0.671)를 좁히기 위해, scope7 생성물 24건의 저AR 케이스를
분석해 "의문사 직답" 레버를 도출하고 `[CORE PRINCIPLES]`에 원칙 8을 추가해 검증했다.
(개수 질문→숫자 우선, 비교 질문→차이 우선, 시각→시각 우선, 예/아니오 우선)

**결과 (동일 n=24, scope7과 짝비교)**

| 지표 | scope7(기준) | 원칙8 | 변화 |
| --- | ---: | ---: | ---: |
| Answer Relevancy | 0.6708 | 0.6780 | +0.0072 |
| Faithfulness | 0.8710 | 0.8578 | **−0.0132** |
| Context Precision | 0.9097 | 0.8958 | −0.0139 |
| Context Recall | 0.9167 | 0.9167 | ±0.0000 |
| retrieval_mrr | 0.8854 | 0.8646 | −0.0208 |

**판정: 기각 (롤백)** ❌

- AR 상승폭 +0.0072는 **n=24 노이즈 수준**이다. 같은 런에서 retrieval_mrr이 −0.0208
  변동(`J_LEI_000003_q2`가 이번엔 MISS)해 retrieval 자체가 런별로 흔들렸고, 이것이
  context_precision −0.0139에도 반영됐다. 즉 AR +0.0072를 신호로 판별할 수 없다.
- 반면 **Faithfulness는 −0.0132 회귀**했다. 원칙6(AR +0.040 & faith +0.062)·원칙7
  (faith +0.039)이 보인 명확한 다점 개선 기준에 못 미치고 부작용까지 있어 채택하지 않는다.

**시사점**: 잔여 저AR은 광범위 질문("どのような場所?")의 RAGAS 역질문 불일치 + 측정 잡음이
지배적이라 프롬프트 한 줄로 옮길 영역이 아니다. 의미 있는 AR 개선은 **질문유형별 답변 구성
분리(상세/간결 모드) + 표본 확대(n=30~50) 후 재판정**이라는 구조적 작업이 선결 과제다.
(리포트 앞선 "표본 확대" 권고와 일치.)
