# RAG 최적화 버전 비교 시스템

## 📋 개요

FDA 의약품 정보 RAG 시스템의 성능을 향상시키기 위한 **8가지 최적화 버전**을 구현하고 비교 평가하는 시스템입니다.

---

## 🎯 구현된 최적화 기법

### 1. GPT-4 업그레이드
- **현재**: `gpt-4o-mini`
- **개선**: `gpt-4o`
- **효과**: 더 정확한 답변 생성, 문맥 이해 향상

### 2. 검색 결과 중복 제거
- 동일 성분(generic_name)이 여러 제품에 있을 때 중복 제거
- 더 다양한 정보 제공

### 3. 두 단계 검색 (Two-Stage Retrieval)
- **1단계**: 광범위 검색 (20개)
- **2단계**: 관련성 점수로 재정렬 후 상위 5개 선택
- **효과**: Context Precision & Recall 향상

---

## 📊 8가지 평가 버전

| 버전 | GPT-4 | 중복제거 | 2단계검색 | 설명 |
|------|-------|----------|-----------|------|
| **baseline** | ❌ | ❌ | ❌ | 원본 (베이스라인) |
| **v1_gpt4** | ✅ | ❌ | ❌ | GPT-4만 적용 |
| **v2_dedup** | ❌ | ✅ | ❌ | 중복 제거만 적용 |
| **v3_twostage** | ❌ | ❌ | ✅ | 두 단계 검색만 적용 |
| **v4_gpt4_dedup** | ✅ | ✅ | ❌ | GPT-4 + 중복 제거 |
| **v5_gpt4_twostage** | ✅ | ❌ | ✅ | GPT-4 + 두 단계 검색 |
| **v6_dedup_twostage** | ❌ | ✅ | ✅ | 중복 제거 + 두 단계 검색 |
| **v7_all** | ✅ | ✅ | ✅ | 모든 최적화 적용 |

---

## 🗂️ 생성된 파일 구조

```
DJAeun/
├── src/
│   ├── optimization_config.py      # 8가지 설정 정의
│   ├── optimizations.py            # 최적화 기능 구현
│   └── chain/
│       └── optimized_rag_chain.py  # 최적화된 RAG 체인
├── compare_optimizations.py        # 8개 버전 일괄 비교 평가
├── evaluate_single.py              # 단일 버전 평가
├── test_dataset.json               # 50개 테스트 케이스
└── requirements.txt                # 업데이트된 의존성
```

---

## 🚀 사용 방법

### 1. 의존성 설치

```bash
cd C:\Workspaces\SKN22-3rd-1Team\DJAeun
pip install -r requirements.txt
```

새로 추가된 패키지:
- `pandas`: 결과 비교 테이블 생성

### 2-A. 전체 버전 일괄 비교 (권장)

**모든 8가지 버전을 한 번에 평가하고 비교**

```bash
python compare_optimizations.py
```

**예상 소요 시간**: 약 1-2시간 (50개 질문 × 8개 버전)

**출력 결과**:
- 터미널: 각 버전별 진행 상태 및 최종 비교 테이블
- `evaluation_results/comparison_results.json`: 상세 JSON 결과
- `evaluation_results/comparison_results.csv`: CSV 비교 테이블

**출력 예시**:
```
============================================================
                     📊 전체 비교 결과
============================================================

【 성능 순위 】

               faithfulness  answer_relevancy  context_precision  context_recall    평균
v7_all              0.8756          0.8923             0.8234          0.8012  0.8481
v5_gpt4_twostage    0.8543          0.8765             0.8123          0.7856  0.8322
v4_gpt4_dedup       0.8423          0.8623             0.7934          0.7745  0.8181
v1_gpt4             0.8234          0.8456             0.7823          0.7634  0.8037
baseline            0.7856          0.8123             0.7456          0.7423  0.7715

🏆 최고 성능: v7_all (평균: 0.8481)
📈 Baseline 대비 개선율: +9.93%
```

### 2-B. 단일 버전만 평가

**특정 버전 하나만 평가**

```bash
# 베이스라인 평가
python evaluate_single.py --config baseline

# GPT-4만 적용한 버전 평가
python evaluate_single.py --config v1_gpt4

# 모든 최적화 적용 버전 평가
python evaluate_single.py --config v7_all
```

**가능한 config 값**:
- `baseline`
- `v1_gpt4`
- `v2_dedup`
- `v3_twostage`
- `v4_gpt4_dedup`
- `v5_gpt4_twostage`
- `v6_dedup_twostage`
- `v7_all`

---

## 📈 예상 결과 분석

### 개선사항별 효과

**GPT-4 업그레이드**:
- **Faithfulness**: 큰 향상 예상 (더 정확한 답변)
- **Answer Relevancy**: 중간 향상

**중복 제거**:
- **Context Precision**: 향상 (노이즈 감소)
- **다양성**: 향상 (다양한 성분 정보)

**두 단계 검색**:
- **Context Precision**: 큰 향상 (관련성 높은 문서 선택)
- **Context Recall**: 향상 (충분한 정보 수집)

---

## 💡 최적화 기능 상세 설명

### 1. 중복 제거 로직

[src/optimizations.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/src/optimizations.py) - `deduplicate_by_generic_name()`

```python
# 예시:
# 검색 결과에 Tylenol, Tylenol Extra Strength 등 여러 제품
# --> acetaminophen 성분 기준으로 하나만 선택
```

### 2. 두 단계 검색

[src/optimizations.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/src/optimizations.py) - `rerank_by_relevance()`

**관련성 점수 계산**:
- 브랜드명 완전 일치: +20점
- 브랜드명 부분 일치: +10점
- 성분명 완전 일치: +20점
- 성분명 부분 일치: +10점
- 적응증 일치: +5점
- Purpose 일치: +3점

점수 순으로 정렬하여 상위 5개 선택

### 3. GPT-4 적용

[src/chain/optimized_rag_chain.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/src/chain/optimized_rag_chain.py) - `_get_generator()`

```python
# config.use_gpt4 = True인 경우
model = "gpt-4o"  # 더 강력한 모델

# config.use_gpt4 = False인 경우  
model = "gpt-4o-mini"  # 기본 모델
```

---

## 🔧 설정 커스터마이징

### 새로운 버전 추가

[src/optimization_config.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/src/optimization_config.py)에서 새 설정 추가:

```python
V8_CUSTOM = OptimizationConfig(
    name="v8_custom",
    use_gpt4=True,
    deduplicate_results=True,
    two_stage_retrieval=True,
    stage1_limit=30,  # 1단계 검색 개수 조정
    stage2_limit=10,  # 2단계 선택 개수 조정
)

ALL_CONFIGS.append(V8_CUSTOM)
```

### 두 단계 검색 파라미터 조정

```python
# stage1_limit: 1단계에서 가져올 결과 개수 (기본 20)
# stage2_limit: 2단계에서 선택할 최종 개수 (기본 5)

config = OptimizationConfig(
    name="custom",
    two_stage_retrieval=True,
    stage1_limit=50,  # 더 많이 수집
    stage2_limit=10,  # 더 많이 사용
)
```

---

## 📊 비교 결과 활용

### CSV 파일로 스프레드시트 분석

`evaluation_results/comparison_results.csv`를 Excel이나 Google Sheets에서 열어서:
- 그래프 생성
- 추가 통계 분석
- 팀과 공유

### JSON 파일로 상세 분석

```python
import json
with open('evaluation_results/comparison_results.json', 'r') as f:
    data = json.load(f)
    
# 각 버전의 상세 점수 확인
for config, metrics in data['results'].items():
    print(f"{config}: {metrics}")
```

---

## 🎯 다음 단계

1. **일괄 비교 실행**: `python compare_optimizations.py`로 모든 버전 평가
2. **최고 성능 확인**: 어떤 조합이 가장 효과적인지 확인
3. **프로덕션 적용**: 최고 성능 설정을 `app.py`에 적용
4. **추가 최적화**: 결과 분석 후 더 나은 개선 방법 탐색

---

## 💰 비용 고려사항

**GPT-4 사용 시 API 비용 증가**:
- GPT-4o: GPT-4o-mini 대비 약 15배 비용
- 50개 테스트 × 4개 GPT-4 버전 = 약 200회 호출
- 예상 비용: 약 $1-2 (테스트 전체)

**권장사항**:
1. 먼저 baseline, v2, v3 등 저비용 버전 평가
2. GPT-4 버전은 최종적으로 선택적 평가
3. 또는 테스트 데이터를 10개로 줄여서 파일럿 테스트

---

## 🔗 관련 파일

- [optimization_config.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/src/optimization_config.py) - 설정 정의
- [optimizations.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/src/optimizations.py) - 최적화 기능
- [optimized_rag_chain.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/src/chain/optimized_rag_chain.py) - 최적화된 체인
- [compare_optimizations.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/compare_optimizations.py) - 비교 평가
- [evaluate_single.py](file:///C:/Workspaces/SKN22-3rd-1Team/DJAeun/evaluate_single.py) - 단일 평가
