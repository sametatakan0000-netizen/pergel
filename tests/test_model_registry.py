import json
import os
import tempfile
import unittest

from src.router.model_registry import (
    build_profiles,
    clamp_effort,
    load_snapshot,
    save_snapshot,
)

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

    def test_malformed_sources_raise(self):
        with self.assertRaises(ValueError):
            build_profiles({"version": 2}, MODELS_DEV, fetched_at="x")
        with self.assertRaises(ValueError):
            build_profiles(CATALOG, {"openrouter": "bad"}, fetched_at="x")


if __name__ == "__main__":
    unittest.main()
