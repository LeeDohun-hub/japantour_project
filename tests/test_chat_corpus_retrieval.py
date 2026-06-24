from __future__ import annotations

import unittest
from unittest.mock import patch

from src.chain.router import (
    _chat_generic_place_query,
    _filter_generic_chat_places,
    search_chat_corpus,
)
from src.chain.router_models import RagSearchBundle
from src.chain.vector_store import BM25Index, load_jsonl_records
from src.api.naver_search_client import NaverPlace


class ChatCorpusRetrievalTests(unittest.TestCase):
    def test_hongdae_club_is_converted_to_naver_place_query(self) -> None:
        self.assertEqual(
            _chat_generic_place_query("hongdaeのclub"),
            "홍대 클럽",
        )

    def test_japanese_pharmacy_query_is_converted_to_naver_place_query(self) -> None:
        self.assertEqual(
            _chat_generic_place_query("明洞の近くに薬局はありますか？"),
            "명동 약국",
        )

    def test_non_place_question_is_not_sent_to_naver(self) -> None:
        self.assertEqual(
            _chat_generic_place_query("韓国の歴史を説明してください"),
            "",
        )

    def test_generic_place_results_remove_wrong_business_types(self) -> None:
        def place(name: str, category: str) -> NaverPlace:
            return NaverPlace(
                name=name,
                category=category,
                address="서울특별시 마포구",
                latitude=None,
                longitude=None,
                rating=None,
                user_rating_count=None,
                google_maps_uri=None,
                is_open_now=None,
                distance_meters=None,
            )

        results = _filter_generic_chat_places(
            [
                place("클럽 FF", "생활,편의>클럽"),
                place("로얄짐 합정", "스포츠시설>헬스장"),
                place("하나로마트", "쇼핑,유통>마트"),
            ],
            "홍대 클럽",
        )

        self.assertEqual([item.name for item in results], ["클럽 FF"])

    def test_chat_search_does_not_pass_plan_category_or_area_filters(self) -> None:
        expected = RagSearchBundle(results=[], backend="test", area_filter="")

        with patch("src.chain.router.search_rag", return_value=expected) as mocked:
            result = search_chat_corpus("徳裕山国立公園で見られる具体的な動植物")

        self.assertIs(result, expected)
        mocked.assert_called_once_with(
            "徳裕山国立公園で見られる具体的な動植物",
            category="",
            area="",
            top_k=8,
        )

    def test_deogyusan_record_is_top_unfiltered_bm25_hit(self) -> None:
        index = BM25Index()
        index.build(load_jsonl_records())

        results = index.search(
            "徳裕山国立公園で見られる具体的な動植物",
            category="",
            area="",
            top_k=3,
        )

        self.assertTrue(results)
        self.assertEqual(results[0]["id"], "J_NAT_000001_q3")
        self.assertEqual(results[0]["category"], "nature")
        self.assertIn("約600種の動物", results[0]["answer_ja"])
        self.assertIn("約250種の植物群", results[0]["answer_ja"])


if __name__ == "__main__":
    unittest.main()
