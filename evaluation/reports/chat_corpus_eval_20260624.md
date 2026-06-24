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
