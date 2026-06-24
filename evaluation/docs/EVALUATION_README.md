# RAG 시스템 평가 가이드

## 개요

이 디렉터리는 **Japan Tour**의 `/chat` 응답 품질을 측정하는 도구를 제공합니다.
평가는 **K-Culture 관광 일본어 말뭉치**(`data/processed/tour_knowledge.jsonl`, 37,275건)를
기준 데이터로 사용하며, 실제 운영 경로(`search_chat_corpus()` + `route_and_answer()`)를
그대로 호출해 검색·라우팅·생성 품질을 함께 측정합니다.

> 과거 `test_dataset.json` / `evaluate_rag.py`(의약품 도메인 샘플)는 다른 프로젝트의
> 잔재였으며 더 이상 사용하지 않습니다. 관광 도메인 평가는 아래 chat-corpus 파이프라인을
> 사용하세요.

## 평가 구성 요소

### 1. 평가 데이터셋 빌드 (`build_chat_corpus_eval.py`)

`docs/chat_answerable_questions.md`의 질문과 원본 CSV(`data/raw/tour_knowledge.csv`)의
정답을 결합해 평가셋(`evaluation/data/chat_corpus_eval.json`)을 생성합니다.

- 6개 카테고리(culture / food / leisure / nature / shopping / stay) × 20건 = 120건
- 질문은 일본어 원문, ground_truth는 원본 말뭉치 답변

### 2. 평가 실행 (`evaluate_chat_corpus_ragas.py`)

생성된 평가셋으로 실제 채팅 경로를 실행하고 지표를 산출합니다.

#### 로컬 지표 (API 비용 없음)

- **retrieval_hit_rate**: 원본 정답 문서가 검색 결과에 포함된 비율
- **retrieval_mrr**: 정답 문서의 평균 역순위(Mean Reciprocal Rank)
- **route_accept_rate**: 라우터가 질문을 거절(`invalid`)하지 않고 수락한 비율
- **route_rag_used_rate**: 최종 답변에서 RAG 컨텍스트를 사용한 비율
- **avg_latency_ms**: 평균 응답 시간

#### RAGAS 지표 (OpenAI 평가 모델 호출 — API 비용 발생)

1. **Faithfulness (충실도)**: 답변이 검색된 컨텍스트에 근거하는지(환각 감지)
2. **Answer Relevancy (답변 관련성)**: 답변이 질문과 관련 있는지
3. **Context Precision (컨텍스트 정밀도)**: 검색 결과의 신호 대 노이즈 비율
4. **Context Recall (컨텍스트 재현율)**: 필요한 정보를 모두 검색했는지

## 사용 방법

### 1. 환경 준비

```powershell
pip install -r requirements.txt
# .env 에 OPENAI_API_KEY 설정
```

벡터 백엔드는 `.env`의 `VECTOR_BACKEND`(`pgvector` 또는 `faiss`)를 따릅니다.

### 2. 평가셋 빌드

```powershell
python -m evaluation.scripts.build_chat_corpus_eval
```

### 3. 평가 실행

검색·라우팅 지표만 빠르게 보려면(API 비용 최소, RAGAS 생략):

```powershell
python -m evaluation.scripts.evaluate_chat_corpus_ragas --limit 20 --skip-ragas
```

RAGAS 4개 지표까지 포함(카테고리 균형 표본 권장):

```powershell
python -m evaluation.scripts.evaluate_chat_corpus_ragas --limit 12
```

전체 120건 실행:

```powershell
python -m evaluation.scripts.evaluate_chat_corpus_ragas --limit 0
```

주요 옵션:

| 옵션 | 설명 |
| --- | --- |
| `--limit N` | 평가 건수(0=전체 120건). 카테고리 균형으로 추출 |
| `--top-k K` | 검색 상위 K건(기본값은 스크립트 `DEFAULT_TOP_K`) |
| `--skip-ragas` | RAGAS(API 비용) 생략, 로컬 지표만 산출 |
| `--output PATH` | 결과 JSON 저장 경로 지정 |

### 4. 결과 확인

- **터미널 출력**: 건별 검색 적중/순위, 마지막에 요약 지표 표시
- **결과 파일**: `evaluation/reports/chat_corpus_ragas_<N>_<timestamp>.json`
  - `_generated.json` 체크포인트에는 RAGAS 실행 전 생성 답변이 저장됩니다.

## 점수 해석

- **0.8 이상**: 우수
- **0.6 ~ 0.8**: 양호(개선 여지 있음)
- **0.6 미만**: 개선 필요

## 문제 해결

### RAGAS 지표가 결측(NaN)으로 나오는 경우
- Faithfulness·Context Precision은 건당 LLM 호출이 많아 평가 모델 지연 시 가장 먼저
  타임아웃됩니다. `run_ragas()`는 **fail-fast** 설정(`timeout=90, max_retries=1,
  max_workers=3`)으로 느린 지표를 NaN 처리하고 전체 실행을 **시간 내 완료**시킵니다.
  (timeout을 크게 늘리고 retries를 많이 주면 재시도가 누적돼 평가가 사실상 멈추므로
  권장하지 않습니다.)
- 표본 수를 줄이거나(`--limit`) 시간대를 바꿔 API 지연을 피하세요.
- 4개 지표를 안정적으로 모두 얻으려면 설정 튜닝이 아니라 구조 개선이 필요합니다:
  평가 모델 경량화, 건별 캐싱+재개 가능한 체크포인트, 지표 분리 실행 등.

### OpenAI API 오류
- `.env`의 `OPENAI_API_KEY`와 사용량 한도를 확인하세요.

## 참고 자료

- [Ragas 공식 문서](https://docs.ragas.io/)
- 답변 가능 질문 예시: `docs/chat_answerable_questions.md`
- 최신 평가 리포트: `evaluation/reports/chat_corpus_eval_20260624.md`
