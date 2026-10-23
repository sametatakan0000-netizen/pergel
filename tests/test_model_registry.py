import json
import os
import tempfile
import unittest

from src.router.model_registry import (
    build_profiles,
    build_profiles_from_openrouter,
    clamp_effort,
    load_snapshot,
    save_snapshot,
)

OPENROUTER = {"data": [
    {
        "id": "vendor/strong", "name": "Strong", "description": "Frontier agentic coder",
        "context_length": 1000000,
        "architecture": {"input_modalities": ["text", "image"]},
        "top_provider": {"context_length": 262144, "max_completion_tokens": 64000},
        "supported_parameters": ["tools", "tool_choice", "reasoning_effort"],
        "reasoning": {"mandatory": True, "supported_efforts": ["max", "high", "low"], "default_effort": "high"},
        "pricing": {"prompt": "0.000004", "completion": "0.00002", "input_cache_read": "0.0000004"},
        "benchmarks": {"artificial_analysis": {"intelligence_index": 57.6, "coding_index": None, "agentic_index": 61.0}},
        "knowledge_cutoff": "2026-03-01",
    },
    {
        "id": "vendor/cheap", "name": "Cheap", "context_length": 128000,
        "architecture": {"input_modalities": ["text"]},
        "supported_parameters": ["max_tokens"],
        "reasoning": None,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {"id": "vendor/router", "pricing": {"prompt": "-1", "completion": "-1"}},
]}

CATALOG = {
    "version": 1,
    "providers": {"nous": {"models": [
        {"id": "vendor/strong"},
        {"id": "vendor/cheap", "default": True},
        {"id": "vendor/textonly"},
        {"id": "vendor/catalog-only"},
    ]}},
}

MODELS_DEV = {"openrouter": {"models": {
    "vendor/strong": {
        "name": "Strong", "description": "Frontier agentic coder", "family": "s",
        "tool_call": True, "reasoning": True,
        "reasoning_options": [{"type": "effort", "values": ["low", "medium", "high", "max"]}],
        "modalities": {"input": ["text", "image"], "output": ["text"]},
        "limit": {"context": 1000000, "output": 128000},
        "cost": {"input": 4, "output": 20, "cache_read": 0.4},
        "release_date": "2026-09-01", "knowledge": "2026-03",
    },
    "vendor/cheap": {
        "name": "Cheap", "description": "Fast summarizer", "tool_call": True,
        "reasoning": True,
        "reasoning_options": [{"type": "effort", "values": ["none", "high", "xhigh"]}],
        "modalities": {"input": ["text"], "output": ["text"]},
        "limit": {"context": 262144, "output": 32000},
        "cost": {"input": 0.05, "output": 0.2},
    },
    "vendor/textonly": {
        "name": "No Tools", "tool_call": False,
        "modalities": {"input": ["text"], "output": ["text"]},
        "limit": {"context": 128000}, "cost": {"input": 0.1, "output": 0.1},
    },
    "vendor/not-in-catalog": {"name": "Ignored", "tool_call": True},
}}}


class TestModelRegistry(unittest.TestCase):
    def setUp(self):
        self.profiles = build_profiles(CATALOG, MODELS_DEV, fetched_at="2026-10-23T00:00:00Z")

    def test_only_nous_catalog_ids_are_included(self):
        self.assertEqual(
            set(self.profiles),
            {"vendor/strong", "vendor/cheap", "vendor/textonly", "vendor/catalog-only"},
        )

    def test_real_metadata_is_copied_not_guessed(self):
        p = self.profiles["vendor/strong"]
        self.assertEqual(p.status, "verified_metadata")
        self.assertEqual(p.description, "Frontier agentic coder")
        self.assertTrue(p.supports_vision)
        self.assertTrue(p.supports_tools)
        self.assertEqual(p.effort_levels, ("low", "medium", "high", "max"))
        self.assertEqual(p.context_window, 1000000)
        self.assertEqual(p.list_cost_in, 4)
        self.assertEqual(p.metadata_source, "models.dev:openrouter")
        self.assertTrue(self.profiles["vendor/cheap"].is_silent_default)

    def test_missing_metadata_is_catalog_only_and_not_routable(self):
        p = self.profiles["vendor/catalog-only"]
        self.assertEqual(p.status, "catalog_only")
        self.assertFalse(p.routable)
        self.assertIsNone(p.context_window)
        self.assertFalse(self.profiles["vendor/textonly"].routable)  # no tool calling
        self.assertTrue(self.profiles["vendor/strong"].routable)

    def test_effort_is_clamped_to_model_supported_levels(self):
        cheap = self.profiles["vendor/cheap"]
        strong = self.profiles["vendor/strong"]
        self.assertEqual(clamp_effort(cheap, "medium"), "high")   # nearest supported at or above
        self.assertEqual(clamp_effort(cheap, "max"), "xhigh")      # cap at strongest supported
        self.assertEqual(clamp_effort(strong, "xhigh"), "max")
        self.assertEqual(clamp_effort(strong, "high"), "high")
        self.assertIsNone(clamp_effort(self.profiles["vendor/textonly"], "high"))  # drop field

    def test_snapshot_round_trip_preserves_profiles_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "registry.json")
            save_snapshot(path, self.profiles, fetched_at="2026-10-23T00:00:00Z")
            loaded, fetched_at = load_snapshot(path)
            self.assertEqual(fetched_at, "2026-10-23T00:00:00Z")
            self.assertEqual(loaded["vendor/strong"], self.profiles["vendor/strong"])
            with open(path, encoding="utf-8") as f:
                self.assertIn("Frontier agentic coder", f.read())

    def test_openrouter_source_adds_benchmarks_and_reasoning_contract(self):
        profiles = build_profiles_from_openrouter(CATALOG, OPENROUTER, fetched_at="t")
        strong = profiles["vendor/strong"]
        self.assertEqual(strong.metadata_source, "openrouter:/api/v1/models")
        self.assertEqual(strong.context_window, 262144)  # conservative: effective provider limit
        self.assertEqual(strong.max_output, 64000)
        self.assertEqual(strong.effort_levels, ("low", "high", "max"))  # canonical ascending order
        self.assertEqual(strong.default_effort, "high")
        self.assertTrue(strong.reasoning_mandatory)
        self.assertAlmostEqual(strong.list_cost_in, 4.0)
        self.assertAlmostEqual(strong.list_cost_cache_read, 0.4)
        self.assertEqual(strong.intelligence_index, 57.6)
        self.assertIsNone(strong.coding_index)
        self.assertEqual(strong.agentic_index, 61.0)
        self.assertTrue(strong.supports_vision and strong.supports_tools and strong.routable)

    def test_openrouter_missing_tools_or_reasoning_is_reported_honestly(self):
        profiles = build_profiles_from_openrouter(CATALOG, OPENROUTER, fetched_at="t")
        cheap = profiles["vendor/cheap"]
        self.assertFalse(cheap.supports_tools)
        self.assertFalse(cheap.routable)
        self.assertEqual(cheap.effort_levels, ())
        self.assertIsNone(cheap.intelligence_index)
        self.assertEqual(cheap.list_cost_in, 0.0)
        self.assertEqual(profiles["vendor/textonly"].status, "catalog_only")

    def test_malformed_sources_raise(self):
        with self.assertRaises(ValueError):
            build_profiles_from_openrouter(CATALOG, {"data": "bad"}, fetched_at="x")
        with self.assertRaises(ValueError):
            build_profiles({"version": 2}, MODELS_DEV, fetched_at="x")
        with self.assertRaises(ValueError):
            build_profiles(CATALOG, {"openrouter": "bad"}, fetched_at="x")


if __name__ == "__main__":
    unittest.main()
