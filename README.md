# Japan Tour Project

방한 일본인 관광객을 위한 한국 여행 플래너 및 AI 가이드 서비스입니다. 사용자는 8단계 여행 플랜 위저드에서 항공, 숙박, 교통, 방문 지역, 예산, 여행 성향을 입력하고, 시스템은 일본어 중심의 일정·교통·장소 추천을 생성합니다. 별도 AI 채팅 화면에서는 교통, 맛집, 숙소, 관광, 항공, 공연·이벤트 질문에 답변합니다.

일본어 README: [README_jp.md](./README_jp.md)

## 1. 프로젝트 개요

| 항목 | 내용 |
| --- | --- |
| 프로젝트명 | Japan Tour Project |
| 대상 사용자 | 한국 여행을 준비하는 일본인 관광객 |
| 핵심 목적 | 여행 조건 수집, 일정 생성, 실시간성 있는 여행 정보 보조 |
| 메인 화면 | Django 기반 `/` 플랜 위저드, `/chat/` AI 채팅 |
| AI 파이프라인 | 질문 분류 → RAG/외부 API 조회 → LLM 응답 생성 |
| 주요 언어 | 사용자 UI·일정: 일본어 중심, 관리자·문서: 한국어/일본어 병행 |

## 2. 주요 기능

- 8단계 플랜 위저드: 로그인, 항공, 숙박, 교통, 관광 지역, 예산, 상세 조건, 플랜 생성
- AI 채팅: 여행 질문 분류 후 교통·맛집·숙소·관광·항공·일정 답변
- RAG 검색: `tour_knowledge.jsonl` 기반 벡터 검색과 BM25 검색 결합
- 항공·공항 교통 연동: 인천공항 항공편, 공항버스, 택시, 공항철도 운행정보
- 장소 검색·지도: Naver Maps, Naver Local/Blog, Google Places 선택 연동
- 공연·이벤트 추천: Interpark/NOL, VisitKorea, 전국공연행사정보 등
- 인증: 이메일 로그인, Google OAuth, LINE OAuth, 게스트 진행

## 3. 기술 스택

| 구분 | 기술 |
| --- | --- |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Backend | Django, Django REST-style views |
| AI | OpenAI Chat/Embedding API |
| RAG | FAISS 또는 pgvector, BM25, RRF |
| DB | SQLite 개발 기본, PostgreSQL + pgvector 선택 |
| External APIs | Naver Maps/Search, Google Places, 공공데이터포털, VisitKorea, JUSO |
| Legacy UI | Streamlit `app_japan_tour.py` |

## 4. 프로젝트 구조

```text
japantour_project/
├── backend/                 # Django project and tour_api app
├── frontend/                # home/chat UI, wizard, map, link preview
├── src/
│   ├── api/                 # external API clients
│   ├── chain/               # router, RAG, vector store
│   └── security/            # input/output validation
├── data/                    # local data, ignored by Git
├── docs/                    # design documents and reports
├── evaluation/              # evaluation scripts and reports
├── tests/                   # unit tests
├── requirements.txt
└── README.md
```

## 5. 실행 방법

### 5.1 의존성 설치

```powershell
pip install -r requirements.txt
```

### 5.2 환경 변수 설정

```powershell
Copy-Item .env.example .env
```

필수 또는 주요 키:

| 변수 | 설명 |
| --- | --- |
| `OPENAI_API_KEY` | LLM 분류·답변·임베딩 |
| `INCHEONTRANSPORT_API_KEY` | 인천공항, 항공, 공항버스, 택시, 공항철도 API |
| `NAVER_MAPS_CLIENT_ID` | 브라우저 지도 |
| `NAVER_MAPS_CLIENT_SECRET` | 서버 지오코딩 |
| `NAVER_SEARCH_CLIENT_ID` / `NAVER_SEARCH_CLIENT_SECRET` | Naver Local/Blog 검색 |
| `GOOGLE_MAPS_API_KEY` | Google Places 선택 사용 |
| `DJANGO_SECRET_KEY` | 운영 배포 시 필수 |

### 5.3 Django 실행

```powershell
python backend\manage.py migrate
python backend\manage.py runserver 127.0.0.1:8000
```

- 홈: http://127.0.0.1:8000/
- AI 채팅: http://127.0.0.1:8000/chat/
- 헬스 체크: http://127.0.0.1:8000/api/health/

### 5.4 pgvector 개발 DB 선택

```powershell
.\scripts\dev-up.ps1
python backend\manage.py import_tour_knowledge --batch-size 200
```

`VECTOR_BACKEND=pgvector`를 사용하는 경우 Docker Desktop과 PostgreSQL/pgvector 컨테이너가 필요합니다.

## 6. 주요 API

| API | 설명 |
| --- | --- |
| `POST /api/chat/` | 일반 채팅 응답 |
| `POST /api/chat/stream/` | SSE 스트리밍 채팅 |
| `GET /api/flights/` | 항공편 조회 |
| `GET /api/places/search/` | 장소 검색 |
| `POST /api/places/enrich/` | LLM 일정 내 장소명 보강 |
| `GET /api/address/juso/` | 도로명주소 검색 |
| `GET /api/maps/config/` | 지도 설정 |
| `GET /api/link-preview/` | Interpark/NOL 링크 미리보기 |

## 7. 문서

| 문서 | 한국어 | 일본어 |
| --- | --- | --- |
| README | [README.md](./README.md) | [README_jp.md](./README_jp.md) |
| 요건정의서 | [docs/요건정의서.md](./docs/요건정의서.md) | [docs/要件定義書.md](./docs/要件定義書.md) |
| 시스템 설계 개요 | [docs/system-design-overview.md](./docs/system-design-overview.md) | [docs/system-design-overview_jp.md](./docs/system-design-overview_jp.md) |
| 기본설계서 | [docs/기본설계서.md](./docs/기본설계서.md) | [docs/基本設計書.md](./docs/基本設計書.md) |
| 상세설계서 | [docs/상세설계서.md](./docs/상세설계서.md) | [docs/詳細設計書.md](./docs/詳細設計書.md) |

## 8. 테스트

```powershell
python -m unittest
node --check frontend\app.js
node tests\test_plan_map_parser.js
```

## 9. 주의 사항

- `.env`와 `data/`는 Git에 커밋하지 않습니다.
- 공공데이터포털 API는 서비스별 활용신청 승인이 별도로 필요할 수 있습니다.
- Google Places는 비용 이슈가 있으므로 `ENABLE_GOOGLE_PLACES=1`일 때만 의도적으로 사용합니다.
- Streamlit 앱은 레거시 실행 경로이며, 제출·시연 기준은 Django `:8000`입니다.
