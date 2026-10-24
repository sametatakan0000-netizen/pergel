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


class TestLlmDecomposition(unittest.TestCase):
    LONG = "lightpanda chromium playwright headless tarayici performans farki"

    def test_llm_decompose_parses_json_array(self):
        from src.search.query_fanout import decompose_query_llm
        calls = []

        def fake_call(prompt):
            calls.append(prompt)
            return '["lightpanda performans", "chromium headless performans"]'

        subs = decompose_query_llm(self.LONG, fake_call)
        self.assertEqual(subs, ["lightpanda performans", "chromium headless performans"])
        self.assertEqual(len(calls), 1)
        self.assertLess(len(calls[0]), 1500)  # bounded prompt: cost policy

    def test_llm_decompose_tolerates_code_fence_and_prose(self):
        from src.search.query_fanout import decompose_query_llm
        raw = 'Tamam:\n```json\n["alt sorgu bir", "alt sorgu iki"]\n```'
        self.assertEqual(decompose_query_llm(self.LONG, lambda p: raw), ["alt sorgu bir", "alt sorgu iki"])

    def test_llm_decompose_rejects_garbage_returns_none(self):
        from src.search.query_fanout import decompose_query_llm
        for bad in ["", "not json", "[]", '["tek"]', '[1, 2]', '{"a": 1}', '["x"]']:
            self.assertIsNone(decompose_query_llm(self.LONG, lambda p, b=bad: b), bad)

    def test_llm_decompose_caps_subqueries_and_dedupes(self):
        from src.search.query_fanout import decompose_query_llm
        raw = '["aaaa bbbb", "aaaa bbbb", "cccc dddd", "eeee ffff", "gggg hhhh", "iiii jjjj"]'
        subs = decompose_query_llm(self.LONG, lambda p: raw, max_subqueries=3)
        self.assertEqual(subs, ["aaaa bbbb", "cccc dddd", "eeee ffff"])

    def test_llm_decompose_swallows_call_errors(self):
        from src.search.query_fanout import decompose_query_llm

        def boom(prompt):
            raise TimeoutError("upstream")

        self.assertIsNone(decompose_query_llm(self.LONG, boom))

    def test_fanout_uses_llm_only_when_lexical_yields_single_long_query(self):
        seen = []

        async def fake_search(sq):
            seen.append(sq)
            return [{"title": sq, "url": f"https://e.com/{len(seen)}", "snippet": "s"}]

        calls = []

        def fake_llm(q):
            calls.append(q)
            return ["alt bir", "alt iki"]

        res = asyncio.run(execute_fanout_and_ground(self.LONG, search_fn=fake_search, decompose_fn=fake_llm))
        self.assertEqual(res["subqueries"], ["alt bir", "alt iki"])
        self.assertEqual(res["decomposition"], "llm")
        self.assertEqual(len(calls), 1)

        calls.clear()
        res2 = asyncio.run(execute_fanout_and_ground("Rust ve Go performans", search_fn=fake_search,
                                                     decompose_fn=fake_llm))
        self.assertEqual(res2["decomposition"], "lexical")
        self.assertEqual(calls, [])  # conjunction split already worked: no model call

        res3 = asyncio.run(execute_fanout_and_ground("kisa sorgu", search_fn=fake_search, decompose_fn=fake_llm))
        self.assertEqual(res3["decomposition"], "lexical")
        self.assertEqual(calls, [])  # short query: no model call

    def test_fanout_falls_back_to_lexical_when_llm_returns_none(self):
        async def fake_search(sq):
            return [{"title": sq, "url": "https://e.com/1", "snippet": "s"}]

        res = asyncio.run(execute_fanout_and_ground(self.LONG, search_fn=fake_search,
                                                    decompose_fn=lambda q: None))
        self.assertEqual(res["subqueries"], [self.LONG])
        self.assertEqual(res["decomposition"], "lexical")
