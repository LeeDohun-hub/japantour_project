# Japan Tour Planner — 프로젝트 진행 요약

> 최종 업데이트: 2026-05-26

---

## 프로젝트 개요

일본 거주 한국인 여행자를 위한 **한국 여행 AI 플래너** 챗봇.
사용자가 위저드(wizard)를 통해 여행 기간, 숙소, 목적 관광지, 음식 취향 등을 입력하면,
LLM(GPT-4.1)이 Google Places API · VisitKorea API · 공연 티켓 플랫폼 데이터를 조합해
날짜별 관광 일정 + 식사 + 교통 플랜을 생성한다.

**스택**: Django(백엔드) · Vanilla JS(프론트) · PostgreSQL + pgvector(RAG) · Docker

---

## 구현 완료 항목

### 인프라 / 환경

| 항목 | 상태 | 비고 |
|------|------|------|
| Django 서버 + 인증(로그인/세션) | ✅ | CSRF 토큰, 세션 기반 Rate Limit |
| Docker + pgvector | ✅ | 로컬 · 집 컴 양쪽 환경 설정 완료 |
| 환경변수 `.env` 관리 | ✅ | GOOGLE_API_KEY, OPENAI_API_KEY 등 분리 |
| 평가 파이프라인(eval) | ✅ | ground_truth 분리, pgvector 기반 RAG 평가 |

---

### 위저드 (사용자 입력 단계)

| 항목 | 상태 | 비고 |
|------|------|------|
| 다단계 위저드 UI | ✅ | 여행 기간 · 인원 · 숙소 · 관광지 · 음식 취향 · 소비 성향 |
| 지역 칩 선택 (`regionChips`) | ✅ | seoul/gyeonggi/busan/gangwon 등 9개 리전 |
| 숙소 주소 자동완성 (도로명주소 API) | ✅ | `api_juso_search` |
| 음식 선호 카테고리 선택 | ✅ | grilled_meat/noodles/seafood 등 12개 카테고리 |
| `wizardData.regions` 보강 API 전달 | ✅ | `regions` 파라미터 → Enrich endpoint에 목적지 리전 전달 |

---

### 플랜 생성 파이프라인 (router.py)

| 항목 | 상태 | 비고 |
|------|------|------|
| 질문 분류 (itinerary / food / lodging 등) | ✅ | GPT-4.1-mini 분류기 |
| RAG (pgvector 기반 내부 지식) | ✅ | 관광지·축제·지역 정보 |
| Google Places Nearby/Text Search | ✅ | 음식점·관광지·숙박 |
| VisitKorea API (관광·축제·숙박) | ✅ | |
| 인천공항 항공편 스케줄 | ✅ | IncheonAirportClient |
| 스포츠 경기 일정 연동 | ✅ | SportsScheduleClient |
| 공연 티켓 플랫폼 (인터파크 NOL) | ✅ | TicketPlatformEventsClient |
| KINTEX · 경기이벤트 API | ✅ | GyeonggiEventsClient |
| 웹 검색 (최신 이벤트 보조) | ✅ | WebSearchClient |
| 음식 선호 기반 검색 쿼리 생성 | ✅ | `_food_queries_from_preferences` |

---

### 지역 필터링 (2026-05-25~26 주요 작업)

| 항목 | 상태 | 비고 |
|------|------|------|
| `KR_LOCATION_RESTRICTION` (한국 바운딩 박스) | ✅ | Google Places API hard filter — 일본 결과 완전 차단 |
| `find_for_plan_item` KR 제한 | ✅ | 보강 검색도 한국으로 제한 |
| 호텔 검색 KR 제한 | ✅ | `api_places_search` hotel에도 적용 |
| `_AREA_LOCATION_KEYWORDS` | ✅ | 고양·부산·강릉·제주 등 17개 에리어 키워드 맵 |
| `_place_in_area` / `_place_matches_travel_areas` | ✅ | 목적 관광지 기반 범용 장소 필터 |
| `_GYEONGGI_NON_GOYANG_KEYWORDS` | ✅ | 화성·부천·수원 등 고양시 오판 방지 |
| `_SUDOGWON_AREAS` / `_NON_SUDOGWON_AREAS` 분류 | ✅ | 수도권·비수도권 구분 |
| `_fmt_multi_region_transport_hint` | ✅ | 수도권+비수도권 동시 선택 시 KTX/항공 안내 자동 삽입 |
| `_accom_is_sudogwon` | ✅ | 숙소가 수도권인지 감지 (주소 텍스트 기반) |
| `_fmt_penultimate_day_return_rule` | ✅ | 비수도권 관광+수도권 숙소 → 최종일 전날 귀환 블록 LLM 지시 |

---

### Enrich (보강) 파이프라인

| 항목 | 상태 | 비고 |
|------|------|------|
| Maps URL → Places 상세 변환 | ✅ | `find_for_plan_item` |
| 비한국 주소 필터 (`_is_korea`) | ✅ | 일본·중국·대만 주소 차단 |
| 목적지 리전 주소 필터 (`_addr_matches_dest`) | ✅ | 강릉 일정에 서울 맛집 혼입 방지 |
| 프론트 일본 주소 2차 필터 (`_isJpAddress`) | ✅ | wizard.js에서 추가 필터링 |

---

### UI / 프론트엔드

| 항목 | 상태 | 비고 |
|------|------|------|
| 채팅 UI (플랜 출력) | ✅ | |
| 지도 카드 (plan-map.js) | ✅ | Google Maps 마커 연동 |
| 식당·관광지 카드 보강 표시 | ✅ | 평점·사진·지도 링크 |
| 항공편 카드 | ✅ | |
| 숙박 카드 | ✅ | |
| 음식 선호 필터 (`_placeMatchesUserFoodPref`) | ✅ | 미선택 카테고리 충돌 시만 제외 (양의 매칭 요구 제거) |

---

## 남은 보완점

### 🔴 High Priority (정확도·신뢰도에 직접 영향)

| # | 항목 | 내용 | 파일 |
|---|------|------|------|
| 1 | **보강 필터 과잉 차단 위험** | 첫날·마지막날 숙소 주변(예: 고양) 맛집 카드가 gangwon 필터에 의해 누락될 수 있음. 숙소 리전도 `dest_regions` allowlist에 포함 필요 | `views.py` |
| 2 | **`_accom_is_sudogwon` 미감지 케이스** | 숙소 type이 `"undecided"` 이고 address 텍스트가 없으면 귀환 규칙 미발동. 숙소 region 칩 선택값도 폴백으로 활용하는 로직 필요 | `router.py` |
| 3 | **LLM 환각 장소명 근본 차단** | "카페룸"처럼 실재하지 않는 장소명 생성 시 보강 실패 → 카드 미표시가 최선이지만, LLM이 리스트 외 이름을 생성하지 않도록 프롬프트 강화 가능 | `router.py` 시스템 프롬프트 |
| 4 | **`_REGION_ADDR_KW` 세부 시 보완** | 충남(천안·아산), 전북(군산·익산), 경남(거제·통영) 등 시 단위 키워드 누락 | `views.py` |

### 🟡 Medium Priority (UX·기능 완성도)

| # | 항목 | 내용 | 파일 |
|---|------|------|------|
| 5 | **숙소 리전 → 보강 allowlist 통합** | `wizardData.accommodation.region`을 파싱해 숙소 근처 시(고양 등)도 보강 가능 리전에 포함 | `wizard.js`, `views.py` |
| 6 | **평가 파이프라인 재실행** | 이번 세션 대규모 변경 후 정확도 수치 재측정 필요 (지역 필터·귀환 규칙 영향도 확인) | `evaluation/` |
| 7 | **귀환 이동 시간 정밀화** | 출발지·도착지 실제 KTX 시각표 반영 (현재는 고정 예시 시간대). Naver 지도 API or 코레일 API 연동 시 개선 가능 | `router.py` |
| 8 | **체인 식당 중복 제거 고도화** | 동일 브랜드의 다른 지점이 다른 날에 배치되는 경우 감지 로직 추가 | `router.py` |
| 9 | **이동 동선 최적화** | 같은 날 떨어진 두 에리어를 왔다갔다 하는 비효율 일정 생성 방지 (에리어별 하루 묶기) | `router.py` |

### 🟢 Low Priority (장기 개선)

| # | 항목 | 내용 |
|---|------|------|
| 10 | **실시간 영업시간 반영** | Google Places `currentOpeningHours`를 일정 배치에 더 적극 반영 |
| 11 | **항공편 ↔ 일정 연동** | 인천공항 도착 시간 기반으로 첫날 일정 자동 조정 |
| 12 | **일정 저장 / 공유** | 생성된 플랜 PDF 출력 또는 공유 링크 생성 |
| 13 | **다국어 지원** | 현재 LLM 출력이 일본어·한국어 혼재. 언어 선택 기능 추가 |
| 14 | **평가 자동화** | CI에 eval 파이프라인 통합 — 배포 전 정확도 회귀 자동 감지 |

---

## 파일별 주요 역할 요약

```
src/
  api/
    google_places_client.py   — Places API 클라이언트 (KR_LOCATION_RESTRICTION 포함)
    aviation_client.py        — 인천공항 항공편 API
    visitkorea_client.py      — 한국관광공사 API
    sports_schedule_client.py — 스포츠 경기 일정
    ticket_platform_events_client.py — 인터파크 공연 티켓
    gyeonggi_events_client.py — 경기도·KINTEX 이벤트
    web_search_client.py      — 웹 검색 보조
  chain/
    router.py                 — 핵심: 분류→데이터수집→컨텍스트조립→LLM 호출 파이프라인
    vector_store.py           — pgvector RAG
  security/
    response_validator.py     — 분류 결과 검증

backend/tour_api/
  views.py                   — Django API 엔드포인트 (chat, enrich, places, auth)

frontend/
  wizard.js                  — 위저드 단계 + 보강 로직
  plan-map.js                — Google Maps 카드 렌더링
```

---

## 버전 히스토리 (주요 커밋)

| 날짜 | 내용 |
|------|------|
| 2026-05-12 | 프로젝트 재시작 |
| 2026-05-14 | README 정비, Django 분리 UI |
| 2026-05-16 | pgvector 전환, 평가 파이프라인 구축, 인천공항 API |
| 2026-05-18 | 숙박 카드, Places/Aviation 파이프라인 |
| 2026-05-20 | 관광지 위주 출력, pgvector Docker 설정 |
| 2026-05-21 | 항공·지도·식사 개선, 웹 인증 |
| 2026-05-22 | 일정·Places·티켓 소스 보강, 20260520 보고 반영 |
| 2026-05-25 | 리팩토링: 지역 필터 범용화, KR 제한, 음식 선호 로직 개선 |
| 2026-05-26 | 귀환 규칙, 보강 목적지 필터, 수도권 숙소 감지 |
