# router.py Refactor Map

This note is a working map for splitting `src/chain/router.py` without changing behavior first.
Use it as the extraction order, not as a design rewrite.

## Current Shape

`router.py` is the AI orchestration module for chat and wizard itinerary generation. It currently owns:

- project help intent detection and chat routing helpers
- RAG loading/search/formatting
- airport and flight context formatting
- traveler destination, area, and accommodation helpers
- itinerary place query construction
- Naver/Places/VisitKorea candidate collection
- food/cafe/attraction candidate filtering
- wizard itinerary URL repair and safety repair
- wizard quality scoring and retry logic
- festival, vacation, KTO, and direct lookup context assembly
- top-level `route_and_answer`

The safest extraction path is to move tested, low-I/O helper groups first, then move API-heavy groups.

## Extraction Status

- 2026-06-17: 6개 모듈 추출 완료 (commit 5bc6f7b).
  - `itinerary_repair.py` 901줄 — URL 수리, 슬롯 파싱, 식사 타이밍, area focus
  - `itinerary_places.py` 381줄 — place classifier, 쿼리 빌더, 후보 병합
  - `itinerary_regions.py` 513줄 — 지역 판별, zone 체크, 에리어 결정
  - `itinerary_quality.py` 382줄 — 퀄리티 스코어링, vacation fallback
  - `travel_context.py` 430줄 — 공항/항공편/예산/여행자 포맷터
  - `live_context.py` 783줄 — VisitKorea/KTO/festival/vacation 포맷터
  - `router.py` 9657 → 6626줄 (31% 감소)
- 모든 기존 심볼 `router.py`에서 re-export 유지, 기존 테스트 59/60 통과 (나머지 1개는 추출 전부터 실패).

## Proposed Modules

| Target module | Source responsibility | First extraction candidates |
| --- | --- | --- |
| `src/chain/itinerary_repair.py` | Postprocess generated wizard plans so map cards, meals, cafes, and attraction slots stay consistent. | `_repair_itinerary_place_urls`, `_repair_wizard_itinerary_rules`, slot/day parsing helpers, map URL/name helpers. |
| `src/chain/itinerary_places.py` | Build, merge, filter, and format food/cafe/attraction candidates for itinerary generation. | `_build_itinerary_food_queries`, `_build_itinerary_attraction_queries`, `_combine_itinerary_place_candidates`, `_merge_itinerary_places`. |
| `src/chain/itinerary_regions.py` | Resolve profile regions, city ids, area fallback, and daily area binding. | `_tourism_search_areas`, `_detect_itinerary_areas`, `_fmt_itinerary_daily_area_binding`, region-city helpers. |
| `src/chain/itinerary_quality.py` | Score wizard plans and append deterministic fallback sections. | `_score_wizard_plan_quality`, `_append_vacation_section_fallback`. |
| `src/chain/travel_context.py` | Format airport, flight, transport, budget, and traveler constraints. | airport/flight formatters and traveler constraint helpers. |
| `src/chain/live_context.py` | Fetch/format VisitKorea, festivals, vacation stays, KTO, and web data. | VisitKorea/KTO/festival/vacation helpers. |

## Recommended Order

1. Keep `route_and_answer` in `router.py`.
2. Extract `itinerary_repair.py` first because regression coverage already exists in `tests/test_region_resolution.py`.
3. Re-export imported helpers from `router.py` only if existing tests import private names directly.
4. Run Python and JS regression tests after each small move.
5. Extract region and place helpers only after repair extraction is stable.

## Itinerary Repair Boundary

Initial extraction boundary:

- `_MAPS_URL_IN_TEXT_RE`
- `_norm_plan_place_name`
- `_extract_jp_name_map`
- `_apply_jp_names_to_places`
- `_repair_itinerary_place_urls`
- `_ITINERARY_SLOT_MARKERS`
- `_ITINERARY_DAY_RE`
- `_ITINERARY_BAD_PLACEHOLDER_RE`
- `_CAFE_SLOT_ONLY_RE`
- `_EMPTY_COMBINED_SLOT_RE`
- `_queue_places_for_repair`
- `_plan_maps_url_key`
- `_itinerary_slot_from_line`
- `_itinerary_day_number`
- `_late_arrival_blocks_meals`
- `_early_departure_blocks_meals`
- `_itinerary_line_foodish`
- `_looks_like_plain_itinerary_place_line`
- `_BUSAN_DAY_AREA_ALIASES`
- `_JPN_CITY_TO_KO`
- `_day_focus_area_tokens`
- `_place_matches_day_focus`
- `_repair_wizard_itinerary_rules`

Known dependencies to import or pass in:

- `NearbyPlace`
- `re`, `math`, `dataclasses`
- place classifiers: `_is_cafe_candidate_place`, `_is_meal_candidate_place`, `_foodish_signal`
- trip/profile helpers: `_is_wizard_plan_request`, `_has_cafe_hopping_interest`, `_parse_hhmm`
- area helpers: `_parse_region_city_tokens`, `_tourism_search_areas`, `_accommodation_food_areas`, `_needs_accommodation_buffer_candidates`, `_place_in_stay_zone`, `_accom_is_sudogwon`, `_place_in_seoul_zone`, `_place_in_goyang_zone`, `_place_in_incheon_zone`

Because this boundary still has many dependencies, the first mechanical move should keep imports explicit and avoid changing function signatures.

## Regression Commands

Current reliable commands from this workspace:

```powershell
uv run --with-requirements requirements.txt python -m unittest tests.test_web_search_triggers tests.test_region_resolution
node --check frontend\wizard.js
node tests\test_plan_map_parser.js
```

The plain `python` command may resolve to the WindowsApps stub on this machine. Prefer the `uv run` command until the local Python environment is fixed.
