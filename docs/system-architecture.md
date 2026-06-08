# Japan Tour Project — 시스템 구성도

> 한국 여행 플래너 웹 서비스 / 아키텍처 전체 개요

---

## 전체 구성도

```mermaid
flowchart TB

    subgraph CLIENT["🖥️ CLIENT"]
        direction TB
        USER["사용자\n· 여행 조건 8단계 입력\n· 플랜 확인 / AI 채팅\n· 지도·카드 탐색"]
        ADMIN["운영자\n· git push → 자동 배포\n· .env / 로그 관리"]
    end

    subgraph INFRA["⚙️ INFRA"]
        direction TB
        GHA["GitHub Actions\n· main push 시 EC2 SSH 배포\n· git pull + systemd restart"]
        EC2["AWS EC2\n· systemd: japantour\n· Gunicorn + Django 단일 프로세스"]
        DOCKER["Docker Compose (로컬 전용)\n· pgvector/pgvector:pg17\n· 개발 DB 로컬 실행"]
    end

    subgraph FRONTEND["🎨 FRONTEND"]
        direction TB
        WIZ["wizard.js\n· 8단계 여행 조건 UI\n· 플랜 카드·지도 렌더링\n· SSE 스트림 수신\n· 장소 enrich 요청"]
        PLANMAP["plan-map.js\n· Day 탭 일정 지도\n· Naver 지도 핀·경로"]
        APP["app.js\n· AI 채팅 UI\n· 히스토리·세션 관리"]
        AUTH["auth.js\n· 소셜 로그인\n· 게스트 모드"]
    end

    subgraph BACKEND["🔧 BACKEND  —  Django tour_api"]
        direction TB
        VIEWS["views.py\n· POST /api/chat/\n· GET  /api/chat/stream/ (SSE)\n· POST /api/places/enrich/\n· GET  /api/flights/\n· GET  /api/places/nearby/\n· POST /api/plan/save/"]
        LLM_SVC["llm_service.py\n· route_and_answer() 호출\n· 스트리밍 응답 래핑"]
        PERSIST["chat_persistence.py\n· ChatSession / Message 저장\n· TravelPlanSnapshot 저장\n· 공유 링크 발급"]
    end

    subgraph AICORE["🧠 AI Core  —  src/chain"]
        direction TB
        ROUTER["router.py  ★ 핵심\n· 질문 분류 (itinerary / chat / lookup)\n· 장소·항공·이벤트 검색 통합\n· LLM 프롬프트 조립 및 생성"]
        RAG["rag_chain.py\n· 하이브리드 RAG\n· pgvector + FAISS 병행"]
        VECSTORE["vector_store.py\n· 임베딩 검색\n· 문서 청크 매핑"]
        AIRPORT["airport_transport.py\n· AREX · 리무진 안내"]
        CONCERT["concert_lookup_helpers.py\n· KOPIS 지역 필터링"]
    end

    subgraph EXTERNAL["🌐 External APIs"]
        direction LR
        OPENAI["OpenAI\n· GPT-4o / GPT-4o-mini\n· text-embedding-3-small"]
        NAVER_M["Naver Maps\n· 지도 · 지오코딩"]
        NAVER_S["Naver Search\n· 장소 검색 · 리뷰"]
        GOOGLE["Google Places\n· 장소 후보 보완"]
        KOPIS["KOPIS / 티켓플랫폼\n· 공연 · 콘서트"]
        SPORTS["Sports Schedule\n· KBO · K리그 · K2"]
        FLIGHT["Korea Airports\n· 항공편 스케줄"]
        VISITKOREA["VisitKorea / JUSO\n· 관광지 · 주소 검색"]
    end

    subgraph DATA["💾 DATA"]
        direction TB
        PG[("PostgreSQL + pgvector\n· ChatSession / ChatMessage\n· TravelerProfile\n· TravelPlanSnapshot\n· RAG 임베딩 벡터")]
        JSONL["JSONL 지식 베이스\n· tour_knowledge.jsonl\n· K-Culture RAG 문서"]
        FAISS["FAISS 인덱스\n· 벡터 파일 (로컬 폴백)"]
    end

    %% ── 흐름 연결 ──────────────────────────────────────────
    ADMIN -->|git push| GHA
    GHA -->|SSH + systemd restart| EC2
    EC2 -->|서빙| FRONTEND

    USER -->|HTTP 요청| WIZ
    USER -->|채팅| APP
    WIZ & APP & PLANMAP -->|REST / SSE| VIEWS
    AUTH -->|인증 쿠키| VIEWS

    VIEWS --> LLM_SVC
    VIEWS --> PERSIST
    LLM_SVC --> ROUTER

    ROUTER --> RAG
    ROUTER --> AIRPORT
    ROUTER --> CONCERT
    RAG --> VECSTORE

    ROUTER -->|API 호출| OPENAI
    ROUTER -->|장소 검색| NAVER_S
    ROUTER -->|지도 · 지오코딩| NAVER_M
    ROUTER -->|장소 보완| GOOGLE
    ROUTER -->|공연 정보| KOPIS
    ROUTER -->|경기 일정| SPORTS
    ROUTER -->|항공 스케줄| FLIGHT
    ROUTER -->|관광지 · 주소| VISITKOREA

    VIEWS -->|enrich| NAVER_S
    VIEWS -->|지도| NAVER_M

    PERSIST <-->|읽기/쓰기| PG
    VECSTORE <-->|벡터 검색| PG
    VECSTORE <-->|폴백| FAISS
    RAG -->|문서 로드| JSONL

    DOCKER -.->|로컬 개발 시| PG

    %% ── 색상 스타일 ─────────────────────────────────────────
    classDef client   fill:#1a3a5c,stroke:#4fc3f7,color:#e0f7fa
    classDef infra    fill:#1b3a1b,stroke:#81c784,color:#e8f5e9
    classDef frontend fill:#3a1a3a,stroke:#ce93d8,color:#f3e5f5
    classDef backend  fill:#3a2a00,stroke:#ffb74d,color:#fff8e1
    classDef aicore   fill:#1a1a3a,stroke:#7986cb,color:#e8eaf6
    classDef external fill:#2a1a1a,stroke:#ef9a9a,color:#ffebee
    classDef data     fill:#1a2a2a,stroke:#80cbc4,color:#e0f2f1

    class USER,ADMIN client
    class GHA,EC2,DOCKER infra
    class WIZ,PLANMAP,APP,AUTH frontend
    class VIEWS,LLM_SVC,PERSIST backend
    class ROUTER,RAG,VECSTORE,AIRPORT,CONCERT aicore
    class OPENAI,NAVER_M,NAVER_S,GOOGLE,KOPIS,SPORTS,FLIGHT,VISITKOREA external
    class PG,JSONL,FAISS data
```

---

## 계층별 역할 요약

| 계층 | 구성 요소 | 역할 |
|------|-----------|------|
| **CLIENT** | 브라우저 | 여행 조건 입력, 플랜·지도·채팅 표시 |
| **INFRA** | GitHub Actions → EC2 (systemd) | push 시 자동 배포, 서버 실행 |
| **FRONTEND** | wizard.js / plan-map.js / app.js | 8단계 UI, 지도 렌더링, SSE 채팅 |
| **BACKEND** | Django `tour_api` | REST/SSE API, 세션·스냅샷 저장 |
| **AI Core** | `src/chain/router.py` ★ | 분류·RAG·외부 API 통합·LLM 생성 |
| **External API** | OpenAI, Naver, KOPIS 등 | 생성·장소·항공·공연·스포츠 정보 |
| **DATA** | PostgreSQL + pgvector, JSONL | 이력, 프로필, 플랜, 벡터 인덱스 |

---

## 주요 데이터 흐름

### 1. 플랜 생성
```
사용자 → wizard.js → POST /api/chat/ → llm_service.py
→ router.py [분류: itinerary]
  ├── Naver Search (장소 후보 수집)
  ├── KOPIS (공연 정보)
  ├── Sports Schedule (경기 일정)
  ├── Korea Airports (항공편)
  ├── RAG (K-Culture 지식 검색)
  └── OpenAI GPT-4o (플랜 텍스트 생성)
→ JSON 응답 → wizard.js (카드·지도 렌더링)
```

### 2. 장소 카드 Enrich
```
wizard.js → POST /api/places/enrich/ → Naver Search API
→ 실제 장소명 · 주소 · 사진 · 평점 반환
→ wizard.js 카드 렌더링
```

### 3. AI 채팅 (스트리밍)
```
사용자 → app.js → GET /api/chat/stream/ (SSE)
→ router.py [분류: chat / lookup]
  ├── RAG (pgvector / FAISS 하이브리드 검색)
  └── OpenAI GPT-4o (스트리밍 생성)
→ SSE token stream → app.js 실시간 출력
```

---

## 배포 구조

```
[로컬 워크스페이스]
    git push origin main
        ↓
[GitHub Actions]
    SSH → EC2
    git pull origin main
    sudo systemctl restart japantour
        ↓
[AWS EC2]
    systemd: japantour (Gunicorn + Django)
    ← .env (API 키, DB 접속 정보)
    ← PostgreSQL (EC2 내 또는 외부 DB)
```

> 로컬 개발 시에는 `docker compose up -d` 로 PostgreSQL + pgvector 컨테이너를 실행

---

## 외부 API 목록

| API | 클라이언트 파일 | 용도 |
|-----|----------------|------|
| OpenAI | (llm_service) | 플랜 생성, 채팅, 임베딩 |
| Naver Maps | `naver_maps_client.py` | 지도, 지오코딩 |
| Naver Search | `naver_search_client.py` | 장소 검색, 리뷰 시그널 |
| Google Places | `google_places_client.py` | 장소 후보 보완 |
| KOPIS / 티켓 | `ticket_platform_events_client.py` | 공연·콘서트 (지역 필터) |
| Sports Schedule | `sports_schedule_client.py` | KBO · K리그 · K2 경기 |
| Korea Airports | `korea_airports_flight_client.py` | 항공편 스케줄 |
| VisitKorea | `visitkorea_client.py` | 관광지, 축제 정보 |
| JUSO | `juso_client.py` | 한국 주소 검색 |
| ODSay | `odsay_client.py` | 대중교통 경로 |

---

*관련 문서: [README.md](../README.md) · [요件定義書](./要件定義書.md) · [基本設計書](./基本設計書.md)*
