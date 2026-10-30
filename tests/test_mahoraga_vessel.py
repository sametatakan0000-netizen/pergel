"""Tests for Mahoraga Vessel Core and all AGI modules."""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mahoraga.vessel import Vessel, ModuleState
from src.mahoraga.websurf_oracle import WebsurfOracle, OracleResponse
from src.mahoraga.synapse_profiler import SynapseProfiler, SynapseMap, FeatureMap
from src.mahoraga.filter_detector import FilterDetector, FilterMap
from src.mahoraga.component_merger import ComponentMerger, MergeExperiment
from src.mahoraga.self_evolution import (
    SelfEvolutionLoop, ExternalVerifier, RewardHackDetector, EvolutionIteration
)


class TestVessel(unittest.TestCase):
    """Vessel Core — minimal kernel tests."""

    def test_boot_under_2s(self):
        vessel = Vessel()
        status = vessel.status()
        self.assertLess(status["uptime_ms"], 2000)
        self.assertTrue(status["boot_ok"])

    def test_register_and_load_module(self):
        vessel = Vessel()
        vessel.register_module("test", lambda cfg: {"loaded": True})
        mod = vessel.get_module("test")
        self.assertEqual(mod, {"loaded": True})
        self.assertEqual(vessel.module_states["test"], "ready")

    def test_lazy_loading(self):
        vessel = Vessel()
        loaded = []
        vessel.register_module("lazy1", lambda cfg: loaded.append(1) or "obj1")
        vessel.register_module("lazy2", lambda cfg: loaded.append(2) or "obj2")
        # Only load one
        vessel.get_module("lazy1")
        self.assertEqual(len(loaded), 1)  # lazy2 NOT loaded yet

    def test_duplicate_registration_rejected(self):
        vessel = Vessel()
        vessel.register_module("dup", lambda cfg: "x")
        with self.assertRaises(ValueError):
            vessel.register_module("dup", lambda cfg: "y")

    def test_unregistered_module_rejected(self):
        vessel = Vessel()
        with self.assertRaises(KeyError):
            vessel.get_module("nonexistent")

    def test_module_error_state(self):
        def bad_loader(cfg):
            raise RuntimeError("boom")
        vessel = Vessel()
        vessel.register_module("bad", bad_loader)
        with self.assertRaises(RuntimeError):
            vessel.get_module("bad")
        self.assertEqual(vessel.module_states["bad"], "error")

    def test_action_log(self):
        vessel = Vessel()
        vessel.log_action("test_action", {"key": "value"})
        self.assertEqual(len(vessel.action_log), 1)
        self.assertEqual(vessel.action_log[0]["action"], "test_action")

    def test_config_passthrough(self):
        vessel = Vessel({"custom_key": "custom_val"})
        vessel.register_module("cfg_test", lambda cfg: cfg)
        mod = vessel.get_module("cfg_test")
        self.assertEqual(mod["custom_key"], "custom_val")


class TestWebsurfOracle(unittest.TestCase):
    """Websurf Oracle — live data access tests."""

    def test_initialization(self):
        oracle = WebsurfOracle()
        status = oracle.status()
        self.assertEqual(status["tools_registered"], 0)
        self.assertEqual(status["cache_size"], 0)

    def test_tool_registration_and_call(self):
        oracle = WebsurfOracle()
        oracle.register_tool("add", lambda a, b: a + b)
        result = oracle.call_tool("add", a=2, b=3)
        self.assertEqual(result, 5)

    def test_unregistered_tool_rejected(self):
        oracle = WebsurfOracle()
        with self.assertRaises(KeyError):
            oracle.call_tool("nonexistent")

    def test_tool_names(self):
        oracle = WebsurfOracle()
        oracle.register_tool("t1", lambda: 1)
        oracle.register_tool("t2", lambda: 2)
        self.assertIn("t1", oracle.tool_names)
        self.assertIn("t2", oracle.tool_names)

    def test_model_metadata_cache(self):
        oracle = WebsurfOracle({"cache_ttl_seconds": 300})
        r1 = oracle.fetch_model_metadata("test/model")
        self.assertFalse(r1.from_cache)
        r2 = oracle.fetch_model_metadata("test/model")
        self.assertTrue(r2.from_cache)

    def test_search_returns_grounded_response(self):
        oracle = WebsurfOracle()
        result = oracle.search("test query")
        self.assertIsInstance(result, OracleResponse)
        self.assertEqual(result.query, "test query")


class TestSynapseProfiler(unittest.TestCase):
    """Synapse Profiler — mechanistic interpretability tests."""

    def test_initialization(self):
        profiler = SynapseProfiler()
        self.assertEqual(len(profiler.profiled_models), 0)

    def test_profile_model_creates_map(self):
        profiler = SynapseProfiler()
        smap = profiler.profile_model("test/model")
        self.assertIsInstance(smap, SynapseMap)
        self.assertEqual(smap.model_id, "test/model")

    def test_profile_idempotent(self):
        profiler = SynapseProfiler()
        m1 = profiler.profile_model("test/model")
        m2 = profiler.profile_model("test/model")
        self.assertIs(m1, m2)

    def test_feature_classification(self):
        smap = SynapseMap(model_id="test")
        smap.features.append(FeatureMap(layer=5, feature_id="f1", description="refusal",
                                         is_refusal_related=True))
        smap.features.append(FeatureMap(layer=8, feature_id="f2", description="reasoning",
                                         is_reasoning_related=True))
        self.assertEqual(len(smap.refusal_features), 1)
        self.assertEqual(len(smap.reasoning_features), 1)


class TestFilterDetector(unittest.TestCase):
    """Filter Detector — alignment detection/removal tests."""

    def test_initialization(self):
        detector = FilterDetector()
        self.assertEqual(len(detector.analyzed_models), 0)

    def test_detect_creates_map(self):
        detector = FilterDetector()
        fmap = detector.detect_filters("test/model")
        self.assertIsInstance(fmap, FilterMap)
        self.assertEqual(fmap.model_id, "test/model")

    def test_apply_removal(self):
        detector = FilterDetector()
        fmap = detector.apply_removal("test/model", technique="norm_preserving")
        self.assertIn("norm_preserving", fmap.techniques_applied)

    def test_hidden_potential_calculation(self):
        fmap = FilterMap(
            model_id="test",
            capability_before={"mmlu": 80.0, "gsm8k": 70.0},
            capability_after={"mmlu": 82.0, "gsm8k": 75.0},
        )
        # avg_before = 75, avg_after = 78.5 → (3.5/75)*100 = 4.67%
        self.assertAlmostEqual(fmap.hidden_potential, 4.667, places=1)

    def test_hidden_potential_empty(self):
        fmap = FilterMap(model_id="test")
        self.assertEqual(fmap.hidden_potential, 0.0)


class TestComponentMerger(unittest.TestCase):
    """Component Merger — cross-model merging tests."""

    def test_initialization(self):
        merger = ComponentMerger()
        self.assertEqual(len(merger.experiments), 0)

    def test_merge_creates_experiment(self):
        merger = ComponentMerger()
        exp = merger.merge(["model_a", "model_b"], technique="ties")
        self.assertIsInstance(exp, MergeExperiment)
        self.assertEqual(exp.source_models, ["model_a", "model_b"])
        self.assertEqual(exp.technique, "ties")

    def test_improvement_calculation(self):
        exp = MergeExperiment(
            experiment_id="test",
            benchmark_before={"mmlu": 80.0, "gsm8k": 70.0},
            benchmark_after={"mmlu": 84.0, "gsm8k": 73.0},
        )
        # avg_before = 75, avg_after = 78.5 → (3.5/75)*100 = 4.67%
        self.assertAlmostEqual(exp.improvement, 4.667, places=1)

    def test_successful_merges_filter(self):
        merger = ComponentMerger()
        e1 = merger.merge(["a", "b"])
        e1.success = True
        e2 = merger.merge(["c", "d"])
        e2.success = False
        self.assertEqual(len(merger.successful_merges), 1)


class TestSelfEvolution(unittest.TestCase):
    """Self-Evolution Loop — DGM-style recursive improvement tests."""

    def test_initialization(self):
        loop = SelfEvolutionLoop()
        self.assertEqual(len(loop.iterations), 0)

    def test_external_verifier_default_rejects(self):
        verifier = ExternalVerifier()
        self.assertFalse(verifier.verify({"any": "state"}))

    def test_external_verifier_custom(self):
        verifier = ExternalVerifier(verify_fn=lambda s: s.get("score", 0) > 50)
        self.assertTrue(verifier.verify({"score": 60}))
        self.assertFalse(verifier.verify({"score": 30}))

    def test_reward_hack_detection(self):
        detector = RewardHackDetector()
        # Huge improvement without verification → suspicious
        self.assertTrue(detector.check(50.0, 80.0, False))
        # Normal improvement with verification → OK
        self.assertFalse(detector.check(50.0, 55.0, True))

    def test_evolution_iteration(self):
        loop = SelfEvolutionLoop()
        state = {"score": 50, "last_modification": "test_mod"}

        def modify_fn(s):
            s["score"] = 60
            s["last_modification"] = "improved"
            return s

        def benchmark_fn(s):
            return s["score"]

        it = loop.evolve_once(modify_fn, benchmark_fn, state)
        self.assertIsInstance(it, EvolutionIteration)
        self.assertEqual(it.benchmark_before, 50)
        self.assertEqual(it.benchmark_after, 60)
        self.assertGreater(it.improvement, 0)

    def test_verified_improvements_only_count_verified(self):
        loop = SelfEvolutionLoop()
        state = {"score": 50}

        def modify_fn(s):
            s["score"] = 60
            return s

        def benchmark_fn(s):
            return s["score"]

        it = loop.evolve_once(modify_fn, benchmark_fn, state)
        # Default verifier rejects → not counted as verified improvement
        self.assertEqual(len(loop.verified_improvements), 0)
        self.assertFalse(it.external_verified)

    def test_bounded_iterations(self):
        loop = SelfEvolutionLoop({"max_iterations": 5})
        self.assertEqual(loop.status()["max_iterations"], 5)


if __name__ == "__main__":
    unittest.main()


class TestSynapseProfilerIntegration(unittest.TestCase):
    """Integration tests for real interpretability tools (GPU required)."""

    @classmethod
    def setUpClass(cls):
        """Load model once for all tests."""
        import torch
        if not torch.cuda.is_available():
            raise unittest.SkipTest("CUDA not available")
        from src.mahoraga.synapse_profiler import SynapseProfiler
        cls.profiler = SynapseProfiler()
        cls.model_name = "gpt2"
        try:
            cls.profiler.load_model(cls.model_name, device="cuda")
        except Exception as e:
            raise unittest.SkipTest(f"Model loading failed: {e}")

    def test_model_loaded(self):
        self.assertIn(self.model_name, self.profiler.loaded_models)
        model = self.profiler._models[self.model_name]
        self.assertEqual(model.cfg.n_layers, 12)  # GPT-2 Small has 12 layers

    def test_logit_lens(self):
        results = self.profiler.logit_lens(self.model_name, "The capital of France is")
        self.assertEqual(len(results), 12)  # 12 layers
        self.assertTrue(all(r.predicted_token != "" for r in results))
        self.assertTrue(all(0 <= r.confidence <= 1 for r in results))

    def test_activation_patching(self):
        results = self.profiler.activation_patching(
            self.model_name,
            clean_text="The Eiffel Tower is in Paris",
            corrupted_text="The Eiffel Tower is in Berlin",
        )
        self.assertEqual(len(results), 12)
        self.assertTrue(all(isinstance(r.matches_clean, bool) for r in results))

    def test_loaded_models_tracking(self):
        self.assertIn(self.model_name, self.profiler.loaded_models)
        status = self.profiler.status()
        self.assertGreaterEqual(status["models_loaded"], 1)
