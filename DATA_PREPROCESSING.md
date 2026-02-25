# 데이터 수집 및 전처리 (Japan Tour Project)

## 📋 개요

`japantour_project`는 **한국을 방문하는 일본인 관광객**에게 여행 정보를 안내하는 챗봇을 목표로 합니다.  
이를 위해 AI Hub에서 제공하는 관광/문화 도메인의 일본어 말뭉치와 QA 데이터를 기반으로,
로컬 `./data` 디렉터리에 **Q&A 중심 지식베이스**를 구축하고,  
챗봇이 쓰기 좋은 형태(JSONL)로 전처리하는 전체 프로세스를 이 문서에 정리합니다.

---

## 1. 데이터 소스

### 1.1 AI Hub 관광 일본어 말뭉치

**데이터셋 이름**: 생성형AI K-Culture 관광 콘텐츠 특화 일본어 말뭉치 데이터  
**페이지**: `https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71789`

**데이터 특징**:
- ✅ 한국 관광에 특화된 일본어 텍스트
- ✅ 각 문단에 대한 **일본어 질의응답(QA) 라벨 데이터** 포함
- ✅ 자연관광 / 문화·역사관광 / 음식 / 숙박 / 쇼핑 / 레포츠 등 카테고리 분류
- ✅ CSV·JSON 기반의 구조화 데이터 (문단 메타데이터 + 본문 + QA 배열)

**주요 필드 (라벨링 JSON 기준 요약)**:
- `classification` : 문단 대분류 (자연관광, 문화/역사관광, 숙박, 음식점, 쇼핑, 레포츠 등)
*- `title` : 문단 제목 (관광지/시설 이름 등)
*- `text` : 일본어 설명 텍스트
*- `QA` : 질문/답변 배열
  - `question` : 일본어 질문
  - `answer` : 일본어 답변

### 1.2 내부 지식베이스 (`tour_knowledge.csv`)

AI Hub 원본 형식은 매우 크고 복잡하기 때문에,  
이 프로젝트에서는 챗봇이 다루기 쉽게 **얇은 Q&A 테이블** 형태로 변환합니다.

**파일 위치**: `data/raw/tour_knowledge.csv`

**스키마 (권장)**:

| 컬럼명         | 타입    | 설명 |
|---------------|---------|------|
| `id`          | str/int | 고유 ID (없으면 전처리 시 자동 생성 가능) |
| `category`    | str     | 카테고리 (예: `nature`, `culture`, `food`, `stay`, `shopping`, `leisure`, `tips` 등) |
| `area`        | str     | 지역/도시 (예: `Seoul`, `Busan`, `Jeju` 등, 없으면 비워도 됨) |
| `question_ja` | str     | 일본인 여행자가 실제로 할 법한 질문 (일본어) |
| `answer_ja`   | str     | 위 질문에 대한 일본어 답변 (가이드 멘트) |
| `answer_ko`   | str     | 동일 내용의 한국어 설명 (선택이지만 권장) |

예시 레코드:

| id | category | area  | question_ja                              | answer_ja                                     | answer_ko                                   |
|----|----------|-------|------------------------------------------|-----------------------------------------------|--------------------------------------------|
| 1  | spot     | Seoul | ソウルで初めての人におすすめのエリアは？ | 初めてなら明洞（ミョンドン）エリアがおすすめです… | 처음 방문이라면 명동 일대를 추천합니다…    |

> 실제로는 AI Hub 라벨링 JSON/CSV에서 `classification`, `title`, `QA.question`, `QA.answer` 등을 읽어  
> 위 스키마에 맞춰 가공한 뒤, `tour_knowledge.csv`로 모으는 과정을 거칩니다.  
> 다운로드/정리는 `DATA_SETUP.md`를, 전처리 단계는 아래 내용을 참고하세요.

---

## 2. 데이터 수집 프로세스

### 2.1 전체 흐름

```mermaid
graph LR
    A[AI Hub<br/>관광 일본어 말뭉치<br/>(dataSetSn=71789)] --> B[aihubshell<br/>-mode d -datasetkey 71789]
    B --> C[압축 해제된 원본 폴더<br/>(CSV/JSON/이미지 등)]
    C --> D[관광/QA 관련 파일 선별]
    D --> E[필요 필드만 추출<br/>classification, title, QA.question, QA.answer 등]
    E --> F[수동/스크립트로<br/>tour_knowledge.csv 구성]
    F --> G[data/raw/tour_knowledge.csv]
    G --> H[tour_preprocess.py<br/>전처리]
    H --> I[data/processed/tour_knowledge.jsonl]
```

### 2.2 QA 추출·매핑 규칙 (권장)

AI Hub 라벨링 JSON 한 건에는 다음과 같은 정보가 들어 있습니다.

- `classification` : 자연관광 / 문화·역사관광 / 숙박 / 음식점 / 쇼핑 / 레포츠
- `title` : 관광지/숙소/음식점 등 제목
- `text` : 본문 설명
- `QA` : 여러 개의 (question, answer) 쌍

이를 `tour_knowledge.csv`로 옮길 때 권장 규칙은 다음과 같습니다.

1. **category 매핑**
   - `자연관광` → `nature`
   - `문화/역사관광` → `culture`
   - `숙박` → `stay`
   - `음식점` → `food`
   - `쇼핑` → `shopping`
   - `레포츠` → `leisure`

2. **area 추정**
   - 메타데이터(예: 지역명 필드)가 있으면 해당 값을 사용
   - 없으면 빈 문자열 또는 상위 지역명(예: `Seoul`, `Busan`)을 수동으로 채우는 것을 권장

3. **question_ja / answer_ja**
   - AI Hub `QA` 배열의 각 원소:
     - `QA[i].question` → `question_ja`
     - `QA[i].answer` → `answer_ja`
   - 한 문단에서 QA가 4개라면, `tour_knowledge.csv`에도 4개의 행이 생깁니다.

4. **answer_ko (선택)**
   - 필요하다면:
     - 원문 한국어 문단(`text`의 한국어 버전) + QA를 참고해 **사람이 직접 한국어 요약/답변**을 작성하거나,
     - 번역기를 활용한 뒤 사람이 후편집(post-edit)하는 방식을 사용할 수 있습니다.

---

## 3. 데이터 전처리

### 3.1 추출 필드 (tour_preprocess 기준)

**구현 파일**: `tour_preprocess.py`

이 스크립트는 `data/raw/tour_knowledge.csv`에서 다음 컬럼들을 읽어들입니다.

| 컬럼명         | 설명                           | 필수 여부 |
|----------------|--------------------------------|-----------|
| `id`           | 레코드 고유 ID                | 🔴 필수 (없으면 자동 생성) |
| `category`     | 관광 카테고리                 | 🟡 권장 |
| `area`         | 지역/도시                     | 🟡 권장 |
| `question_ja`  | 일본어 질문                   | 🔴 필수 |
| `answer_ja`    | 일본어 답변                   | 🔴 필수 |
| `answer_ko`    | 한국어 설명/답변              | 🟢 선택 |

> 필수 컬럼(`question_ja`, `answer_ja`)이 비어 있는 행은 전처리 과정에서 제거됩니다.

### 3.2 텍스트 정제

**처리 작업 (tour_preprocess.py)**:

1. ✅ 필요 컬럼만 선택 (`REQUIRED_COLUMNS + OPTIONAL_COLUMNS`)
2. ✅ 문자열 컬럼 앞뒤 공백 제거 (`str.strip()`)
3. ✅ `question_ja`, `answer_ja`가 비어 있는 행 제거
4. ✅ `id` 컬럼이 없으면 DataFrame 인덱스로 자동 부여
5. ✅ 각 행을 JSON 객체로 직렬화하여 JSONL로 저장

간단한 정제 로직 예시:

```python
for col in keep_cols:
    if df[col].dtype == "object":
        df[col] = df[col].astype(str).str.strip()
```

### 3.3 JSONL 포맷 (최종 산출물)

**출력 파일**: `data/processed/tour_knowledge.jsonl`

각 줄은 하나의 Q&A 레코드를 나타내는 JSON 객체입니다:

```json
{
  "id": "1",
  "category": "spot",
  "area": "Seoul",
  "question_ja": "ソウルで初めての人におすすめのエリアは？",
  "answer_ja": "初めてなら明洞（ミョンドン）エリアがおすすめです...",
  "answer_ko": "처음 방문이라면 명동 일대를 추천합니다..."
}
```

이 파일은 이후:
- RAG용 벡터스토어 인덱싱
- 단순 룰 기반 검색(키워드, 카테고리, 지역)
- 평가용 GT 데이터
등에 그대로 활용할 수 있습니다.

---

## 4. 평가 데이터셋 (선택)

현재 프로젝트에는 별도의 평가 데이터 JSON이 포함되어 있지 않지만,  
향후 다음과 같은 구조로 평가 세트를 구성하는 것을 권장합니다.

**권장 위치**: `data/evaluation/tour_eval.json`  
**권장 스키마**:

```json
[
  {
    "question_ja": "ソウルで初めての人におすすめのエリアは？",
    "expected_answer_ja": "初めてなら明洞（ミョンドン）エリアがおすすめです...",
    "category": "spot",
    "area": "Seoul"
  },
  {
    "question_ja": "冬にソウル旅行をするときの服装は？",
    "expected_answer_ja": "ソウルの冬は東京より寒い日が多いので...",
    "category": "tips",
    "area": "Seoul"
  }
]
```

이렇게 구성해 두면:
- LLM 또는 RAG 기반 챗봇이 생성한 답변과 비교하여
  - 정확도/적합도/커버리지 등을 평가할 수 있습니다.

---

## 5. 데이터 최적화 기법 (권장)

### 5.1 중복 제거 (Deduplication)

**문제**: AI Hub 원본에는 내용이 비슷한 QA가 여러 번 등장할 수 있습니다.  
예: 같은 관광지에 대해 표현만 조금 다른 질문/답변이 다수 존재

**해결 아이디어**:
- `question_ja`를 기준으로 유사도(문자열 혹은 임베딩 기준)를 계산하여,
  너무 유사한 Q&A 쌍은 하나만 남기기
- 또는 `(category, area, title)` 단위로 대표 Q&A만 선별

이를 코드로 구현한다면, `tour_preprocess.py` 이후 별도의 스크립트에서
아래와 비슷한 로직을 사용할 수 있습니다.

```python
seen = set()
deduped = []
for record in records:
    key = (record["category"], record["area"], record["question_ja"])
    if key in seen:
        continue
    seen.add(key)
    deduped.append(record)
```

### 5.2 카테고리/지역 분포 균형

**문제**: 서울·음식 정보에만 Q&A가 집중되고, 지방·자연관광 관련 Q&A가 적을 수 있습니다.

**해결 아이디어**:
- `category`, `area`별 개수를 집계하여,  
  - 지나치게 많은 구간은 샘플링으로 줄이고,
  - 적은 구간은 추가 수집이나 확장 프롬프트로 보완

이 과정을 통해 챗봇이 특정 지역/주제에만 편향되지 않도록 할 수 있습니다.

---

## 6. 데이터 파이프라인 요약

```mermaid
graph TD
    A[AI Hub 관광 일본어 말뭉치<br/>(라벨링 JSON/CSV)] --> B[aihubshell 다운로드]
    B --> C[원본 폴더 정리<br/>(로컬 저장소)]
    C --> D[필요 필드 추출<br/>(classification, QA.question, QA.answer 등)]
    D --> E[data/raw/tour_knowledge.csv]
    E --> F[tour_preprocess.py<br/>전처리]
    F --> G[data/processed/tour_knowledge.jsonl]
    G --> H[향후 RAG/평가 파이프라인]
```

---

## 7. 관련 파일

- **데이터 세팅 가이드**: `DATA_SETUP.md`
- **데이터 전처리 가이드**: `DATA_PREPROCESSING.md` (현재 문서)
- **데이터 복원 스크립트**: `setup_data.py`
- **전처리 스크립트**: `tour_preprocess.py`
- **예시 템플릿**: `data/raw/tour_knowledge_template.csv`
- **전처리 결과**: `data/processed/tour_knowledge.jsonl`

---

## 8. 참고 자료

- AI Hub – 생성형AI K-Culture 관광 콘텐츠 특화 일본어 말뭉치 데이터  
  `https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71789`
- Python 공식 문서: `https://docs.python.org/3/`
- Pandas 공식 문서: `https://pandas.pydata.org/docs/`
- Streamlit 문서: `https://docs.streamlit.io/`
