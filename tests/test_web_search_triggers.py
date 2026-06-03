from __future__ import annotations

import unittest

from src.api.web_search_client import needs_web_search
from src.chain.router import _trim_history_content


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


if __name__ == "__main__":
    unittest.main()
