from __future__ import annotations

import unittest
from datetime import datetime

from src.api.web_search_client import needs_web_search
from src.chain.router import (
    _arex_next_train_reply,
    _is_arex_next_train_question,
    _icn_to_seoul_transport_reply,
    _is_icn_to_seoul_transport_question,
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


class HistoryTrimTests(unittest.TestCase):
    def test_history_content_is_capped(self) -> None:
        trimmed = _trim_history_content("a" * 2500, limit=2000)

        self.assertLessEqual(len(trimmed), 2025)
        self.assertIn("history truncated", trimmed)


class IcnSeoulTransportReplyTests(unittest.TestCase):
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
