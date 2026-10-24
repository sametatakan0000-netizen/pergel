import asyncio
import unittest
from src.search.query_fanout import decompose_query, execute_fanout_and_ground


class TestQueryFanout(unittest.TestCase):
    def test_decompose_query_splits_complex_prompt_into_subqueries(self):
        q = "Canlı indeks tabanlı arama mimarileri ve çok kademeli dinamik model yönlendirme karşılaştırması nedir?"
        subs = decompose_query(q, max_subqueries=4)
        self.assertGreaterEqual(len(subs), 2)
        self.assertTrue(any("arama" in s.lower() for s in subs))
        self.assertTrue(any("model" in s.lower() or "yönlendirme" in s.lower() for s in subs))

    def test_decompose_query_does_not_cut_phrases_without_a_conjunction(self):
        q = "lightpanda chromium playwright headless tarayici performans farki"
        self.assertEqual(decompose_query(q), [q])

    def test_decompose_query_drops_dangling_function_words(self):
        subs = decompose_query("Rust ve Go performans karşılaştırması nedir?")
        self.assertEqual(subs, ["Rust", "Go performans karşılaştırması"])

    def test_execute_fanout_and_ground_deduplicates_and_formats_inline_citations(self):
        async def fake_search(subquery: str):
            return [
                {
                    "url": f"https://docs.example.com/topic-{len(subquery)}",
                    "title": f"Guide for {subquery}",
                    "snippet": f"Verified fact about {subquery}",
                }
            ]

        res = asyncio.run(
            execute_fanout_and_ground(
                "Arama mimarileri ve dinamik model yönlendirme", search_fn=fake_search
            )
        )
        self.assertGreaterEqual(len(res["sources"]), 1)
        self.assertIn("[1]", res["grounded_context"])
        self.assertIn("https://docs.example.com/", res["grounded_context"])


if __name__ == "__main__":
    unittest.main()
