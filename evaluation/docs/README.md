# 📊 RAG 평가 시스템

FDA 의약품 정보 RAG 시스템의 성능을 평가하기 위한 파일 및 도구 모음입니다.

---

## 📁 폴더 구조

```
evaluation/
├── scripts/              # 평가 스크립트
│   ├── evaluate_rag.py            # 기본 평가 스크립트
│   ├── evaluate_single.py         # 단일 버전 평가
│   ├── evaluate_only.py           # 평가만 실행 (답변 재사용)
│   └── compare_optimizations.py   # 8개 버전 일괄 비교
│
├── data/                 # 테스트 데이터
│   ├── test_dataset.json          # 50개 한국어 질문 + 정답
│   └── generated_answers.json     # 시스템이 생성한 답변
│
├── results/              # 평가 결과
│   └── evaluation_baseline.json   # Baseline 평가 점수
│
└── docs/                 # 문서
    ├── EVALUATION_README.md       # 평가 시스템 사용법
    ├── EVALUATION_REPORT.md       # 평가 결과 상세 보고서
    └── OPTIMIZATION_GUIDE.md      # 8가지 최적화 버전 가이드
```

---

## 🚀 빠른 시작

### 1. 의존성 설치
```bash
cd C:\Workspaces\SKN22-3rd-1Team\DJAeun
pip install -r requirements.txt
```

### 2. 평가 실행

#### A. 전체 평가 (답변 생성 + 평가)
```bash
cd evaluation\scripts
python evaluate_single.py --config baseline
```

#### B. 평가만 실행 (답변 재사용)
```bash
cd evaluation\scripts
python evaluate_only.py
```

#### C. 8개 버전 일괄 비교
```bash
cd evaluation\scripts
python compare_optimizations.py
```

---

## 📊 데이터 설명

### test_dataset.json (문제 데이터)
- **규모**: 50개 케이스
- **형식**: 
  ```json
  {
    "question": "타이레놀은 어떤 약인가요?",
    "ground_truth": "타이레놀은 아세트아미노펜을 주성분으로...",
    "category": "brand_name",
    "search_keyword": "Tylenol"
  }
  ```

### generated_answers.json (정답 데이터)
- 시스템이 생성한 답변 및 검색 컨텍스트
- Ragas 평가에 사용됨

---

## 📈 평가 지표

| 지표 | 설명 | 목표 |
|------|------|------|
| **Faithfulness** | 답변이 문서에 충실한가 | 0.8+ |
| **Answer Relevancy** | 답변이 질문과 관련 있는가 | 0.6+ |
| **Context Precision** | 검색이 정확한가 | 0.8+ |
| **Context Recall** | 필요한 정보를 모두 검색했는가 | 0.7+ |

---

## 🎯 Baseline 결과

```
평균: 0.612

- Faithfulness: 0.825 ✅
- Answer Relevancy: 0.113 ❌ (개선 필요)
- Context Precision: 0.780 ⚠️
- Context Recall: 0.730 ⚠️
```

**최우선 개선 과제**: Answer Relevancy (프롬프트 최적화)

---

## 🔗 관련 문서

- [평가 시스템 사용법](docs/EVALUATION_README.md)
- [평가 결과 상세 보고서](docs/EVALUATION_REPORT.md)
- [8가지 최적화 버전 가이드](docs/OPTIMIZATION_GUIDE.md)

---

## 💡 다음 단계

1. **프롬프트 최적화** - Answer Relevancy 향상 (최우선)
2. **나머지 7개 버전 평가** - 최적 조합 발견
3. **결과 분석 및 적용** - 프로덕션 배포
