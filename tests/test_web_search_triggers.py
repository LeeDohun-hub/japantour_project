from __future__ import annotations

import unittest
from datetime import date, datetime

from src.api.web_search_client import needs_web_search
from src.chain.router import (
    _arex_next_train_reply,
    _chat_concert_region_area_keys,
    _chat_lookup_date_window,
    _concert_artist_query,
    _is_arex_next_train_question,
    _icn_to_seoul_transport_reply,
    _is_icn_to_seoul_transport_question,
    _is_project_help_question,
    _is_wizard_plan_request,
    _trim_history_content,
)
from src.api.aviation_client import AirportRailroadOperation


class WebSearchTriggerTests(unittest.TestCase):
    def test_leisure_landmark_keywords_trigger_web_search(self) -> None:
        self.assertTrue(
            needs_web_search("부산 야경 명소 추천", "부산 야경 명소", "leisure")
        )
        self.assertTrue(
            needs_web_search("ソウルの夜景スポット", "ソウル 夜景", "general")
        )

    def test_plain_leisure_without_current_signal_does_not_trigger(self) -> None:
        self.assertFalse(
            needs_web_search("부산에서 산책하기 좋은 곳", "부산 산책", "leisure")
        )


class DirectConcertLookupParsingTests(unittest.TestCase):
    def test_month_only_kpop_query_uses_full_month_window(self) -> None:
        start_d, end_d = _chat_lookup_date_window("7월 kpop 콘서트 일정")

        self.assertEqual((start_d.month, start_d.day), (7, 1))
        self.assertEqual((end_d.month, end_d.day), (7, 31))

    def test_explicit_year_month_query_uses_that_month(self) -> None:
        start_d, end_d = _chat_lookup_date_window("2026년 7월 kpop 콘서트 일정")

        self.assertEqual(start_d, date(2026, 7, 1))
        self.assertEqual(end_d, date(2026, 7, 31))

    def test_generic_kpop_month_query_does_not_become_artist(self) -> None:
        self.assertEqual(_concert_artist_query("7월 kpop 콘서트 일정"), "")

    def test_artist_survives_when_month_is_present(self) -> None:
        self.assertEqual(_concert_artist_query("세븐틴 7월 콘서트 일정"), "세븐틴")

    def test_city_hint_becomes_concert_region_filter(self) -> None:
        self.assertEqual(_chat_concert_region_area_keys("부산 7월 kpop 콘서트"), ["busan"])


class ProjectHelpQuestionTests(unittest.TestCase):
    def test_detects_app_feature_question(self) -> None:
        self.assertTrue(_is_project_help_question("AI 채팅은 어떤 질문에 답할 수 있어?"))
        self.assertTrue(_is_project_help_question("저장된 플랜은 어떻게 불러오나요?"))

    def test_source_lookup_question_still_can_use_direct_lookup(self) -> None:
        self.assertFalse(_is_project_help_question("KOPIS에서 7월 콘서트 일정 알려줘"))


class HistoryTrimTests(unittest.TestCase):
    def test_history_content_is_capped(self) -> None:
        trimmed = _trim_history_content("a" * 2500, limit=2000)

        self.assertLessEqual(len(trimmed), 2025)
        self.assertIn("history truncated", trimmed)


class IcnSeoulTransportReplyTests(unittest.TestCase):
    def test_wizard_plan_request_survives_transport_keywords(self) -> None:
        self.assertTrue(
            _is_wizard_plan_request(
                {"plan_mode": True, "regions": ["seoul"], "nights": 4, "days": 5},
                "韓国旅行プランを作成してください。仁川空港からソウル市内への移動方法も含めてください。",
            )
        )

    def test_detects_arex_next_train_question(self) -> None:
        self.assertTrue(
            _is_arex_next_train_question(
                "지금 시간 이후로 바로 탈수 있는 AREX 열차는 뭔가요",
                "AREX 다음 열차",
            )
        )

    def test_arex_next_train_reply_lists_upcoming_departures(self) -> None:
        reply = _arex_next_train_reply("한국어", datetime(2026, 6, 3, 18, 20))

        self.assertIn("18:20", reply)
        self.assertIn("18:43 출발", reply)
        self.assertIn("19:26 도착", reply)
        self.assertIn("어른 13,000원", reply)
        self.assertIn("AREX 공식", reply)

    def test_arex_next_train_reply_prefers_api_operations(self) -> None:
        operations = [
            AirportRailroadOperation(
                operation_date="20260603",
                train_no="A9999",
                station_code="100",
                operation_serial="1",
                stop_code="",
                arrival_scheduled="20260603191300",
                departure_scheduled="20260603185600",
                arrival_actual="",
                departure_actual="",
                train_class="Dirc",
            )
        ]

        reply = _arex_next_train_reply("한국어", datetime(2026, 6, 3, 18, 20), operations)

        self.assertIn("18:56 출발", reply)
        self.assertIn("19:13 도착", reply)
        self.assertIn("공항철도 운행정보 API", reply)

    def test_detects_icn_to_seoul_transport_question(self) -> None:
        self.assertTrue(
            _is_icn_to_seoul_transport_question(
                "인천공항에서 서울시내 가는 주요 이동방법 알려줘",
                "인천공항 서울시내 교통",
            )
        )

    def test_korean_reply_contains_readable_sections_and_links(self) -> None:
        reply = _icn_to_seoul_transport_reply("한국어")

        self.assertIn("1. AREX", reply)
        self.assertIn("시간표/요금", reply)
        self.assertIn("어른 13,000원", reply)
        self.assertIn("회원 12,500원", reply)
        self.assertIn("https://www.airportrailroad.com", reply)
        self.assertIn("https://klimousine.com", reply)
        self.assertIn("경로맵", reply)
        self.assertIn("Kakao T", reply)


if __name__ == "__main__":
    unittest.main()
