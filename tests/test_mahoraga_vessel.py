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
    SelfEvolutionLoop, ExternalVerifier, RewardHackDetector,
    EvolutionIteration, HGMSelector
)


class TestVessel(unittest.TestCase):
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
        vessel.get_module("lazy1")
        self.assertEqual(len(loaded), 1)

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
        self.assertAlmostEqual(fmap.hidden_potential, 4.667, places=1)

    def test_hidden_potential_empty(self):
        fmap = FilterMap(model_id="test")
        self.assertEqual(fmap.hidden_potential, 0.0)


class TestComponentMerger(unittest.TestCase):
    def test_initialization(self):
        merger = ComponentMerger()
        self.assertEqual(len(merger.experiments), 0)

    def test_merge_creates_experiment(self):
        merger = ComponentMerger()
        exp = merger.merge(["model_a", "model_b"], method="ties")
        self.assertIsInstance(exp, MergeExperiment)
        self.assertEqual(exp.source_models, ["model_a", "model_b"])
        self.assertEqual(exp.technique, "ties")

    def test_improvement_calculation(self):
        exp = MergeExperiment(
            experiment_id="test",
            benchmark_before={"mmlu": 80.0, "gsm8k": 70.0},
            benchmark_after={"mmlu": 84.0, "gsm8k": 73.0},
        )
        self.assertAlmostEqual(exp.improvement, 4.667, places=1)

    def test_successful_merges_filter(self):
        merger = ComponentMerger()
        e1 = merger.merge(["a", "b"])
        e1.success = True
        e2 = merger.merge(["c", "d"])
        e2.success = False
        self.assertEqual(len(merger.successful_merges), 1)


class TestSelfEvolution(unittest.TestCase):
    """Self-evolution tests with real deterministic verification."""

    def test_external_verifier_deterministic(self):
        verifier = ExternalVerifier()
        self.assertTrue(verifier.verify({"code": "x = 1", "benchmark_score": 0.5}))
        self.assertFalse(verifier.verify({"code": "def broken(:", "benchmark_score": 0.5}))
        self.assertFalse(verifier.verify({"code": "x = 1", "benchmark_score": 0.0}))

    def test_verifier_stats_tracking(self):
        verifier = ExternalVerifier()
        verifier.verify({"code": "x = 1", "benchmark_score": 0.5})
        verifier.verify({"code": "bad(:", "benchmark_score": 0.5})
        stats = verifier.stats
        self.assertEqual(stats["checks_run"], 2)
        self.assertEqual(stats["checks_passed"], 1)

    def test_reward_hack_detection(self):
        detector = RewardHackDetector()
        # Pattern 1: Unverified jump
        self.assertTrue(detector.check(50.0, 80.0, "code", False))
        # Pattern 2: Hardcoded answers
        self.assertTrue(detector.check(50.0, 90.0, "return 42", True))
        # Normal improvement should NOT trigger
        self.assertFalse(detector.check(50.0, 55.0, "for i in range(10): pass", True))

    def test_reward_hack_signatures(self):
        detector = RewardHackDetector()
        detector.check(50.0, 80.0, "code", False)
        self.assertEqual(len(detector.signatures), 1)
        self.assertEqual(detector.signatures[0]["pattern"], "unverified_jump")

    def test_hgm_selector(self):
        selector = HGMSelector()
        iterations = [
            EvolutionIteration(iteration=0, external_verified=True,
                             benchmark_before=50, benchmark_after=60),
            EvolutionIteration(iteration=1, external_verified=True,
                             benchmark_before=60, benchmark_after=70),
        ]
        meta = selector.evaluate_clade(iterations)
        self.assertGreater(meta, 0)
        self.assertLessEqual(meta, 1.0)

    def test_evolution_iteration_improvement(self):
        it = EvolutionIteration(iteration=0, benchmark_before=50.0, benchmark_after=60.0)
        self.assertAlmostEqual(it.improvement, 20.0)
        it_zero = EvolutionIteration(iteration=1, benchmark_before=0.0, benchmark_after=50.0)
        self.assertEqual(it_zero.improvement, 0.0)  # from zero = can't calculate %

    def test_full_evolution_cycle(self):
        loop = SelfEvolutionLoop()
        state = {"code": "x = 1", "benchmark_score": 0.0, "last_modification": "initial"}

        def modify_fn(s):
            s["code"] = "x = 1\ny = 2"
            s["benchmark_score"] = 0.5
            s["last_modification"] = "added y"
            return s

        def benchmark_fn(s):
            return s["benchmark_score"]

        it = loop.evolve_once(modify_fn, benchmark_fn, state)
        self.assertTrue(it.external_verified)
        self.assertFalse(it.reward_hack_suspected)
        # benchmark_before=0, so improvement=0 (can't calculate %)
        # but the iteration is still tracked
        self.assertEqual(len(loop.iterations), 1)

    def test_clade_metaproductivity(self):
        loop = SelfEvolutionLoop()
        state = {"code": "x = 1", "benchmark_score": 0.0}

        def modify_fn(s):
            s["code"] = f"x = {s['benchmark_score'] + 0.3}"
            s["benchmark_score"] = min(s["benchmark_score"] + 0.3, 1.0)
            return s

        def benchmark_fn(s):
            return s["benchmark_score"]

        for _ in range(3):
            loop.evolve_once(modify_fn, benchmark_fn, state)

        self.assertGreater(loop.clade_metaproductivity, 0)
        self.assertLessEqual(loop.clade_metaproductivity, 1.0)

    def test_bounded_iterations(self):
        loop = SelfEvolutionLoop({"max_iterations": 5})
        self.assertEqual(loop.status()["max_iterations"], 5)


class TestSynapseProfilerIntegration(unittest.TestCase):
    """Integration tests for real interpretability tools (GPU required)."""

    @classmethod
    def setUpClass(cls):
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
        self.assertEqual(model.cfg.n_layers, 12)

    def test_logit_lens(self):
        results = self.profiler.logit_lens(self.model_name, "The capital of France is")
        self.assertEqual(len(results), 12)
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


class TestFilterDetectorIntegration(unittest.TestCase):
    """Integration tests for real abliteration (GPU required)."""

    @classmethod
    def setUpClass(cls):
        import torch
        if not torch.cuda.is_available():
            raise unittest.SkipTest("CUDA not available")
        from src.mahoraga.filter_detector import FilterDetector
        cls.detector = FilterDetector()
        cls.model_name = "gpt2"
        try:
            cls.detector.load_model(cls.model_name, device="cuda")
        except Exception as e:
            raise unittest.SkipTest(f"Model loading failed: {e}")

    def test_refusal_direction_detection(self):
        harmful = ["How do I make a bomb?", "How to hack an account?"]
        harmless = ["How do I make a cake?", "How to improve memory?"]
        rd = self.detector.detect_refusal_direction(
            self.model_name, harmful, harmless, layer=8
        )
        self.assertGreater(rd.separation, 0)
        self.assertEqual(rd.direction.shape[0], 768)
        self.assertAlmostEqual(rd.direction.norm().item(), 1.0, places=3)

    def test_rank1_abliteration(self):
        harmful = ["How do I make a bomb?", "How to hack an account?"]
        harmless = ["How do I make a cake?", "How to improve memory?"]
        rd = self.detector.detect_refusal_direction(
            self.model_name, harmful, harmless, layer=8
        )
        result = self.detector.abliterate_rank1(self.model_name, rd)
        self.assertTrue(result.refusal_removed)
        self.assertTrue(result.reasoning_preserved)
        self.assertLess(result.reasoning_delta_pct, 30)

    def test_layer_scanning(self):
        harmful = ["How do I make a bomb?"]
        harmless = ["How do I make a cake?"]
        results = self.detector.scan_refusal_layers(
            self.model_name, harmful, harmless
        )
        self.assertEqual(len(results), 12)
        separations = [r.separation for r in results]
        self.assertEqual(separations, sorted(separations, reverse=True))


class TestComponentMergerIntegration(unittest.TestCase):
    """Integration tests for real MergeKit merging."""

    @classmethod
    def setUpClass(cls):
        try:
            from src.mahoraga.component_merger import ComponentMerger
            cls.merger = ComponentMerger()
        except Exception as e:
            raise unittest.SkipTest(f"ComponentMerger init failed: {e}")

    def test_supported_methods(self):
        self.assertIn("ties", self.merger.SUPPORTED_METHODS)
        self.assertIn("dare", self.merger.SUPPORTED_METHODS)
        self.assertIn("slerp", self.merger.SUPPORTED_METHODS)

    def test_unsupported_method_rejected(self):
        with self.assertRaises(ValueError):
            self.merger.merge(["a", "b"], method="nonexistent")

    def test_merge_config_creation(self):
        exp = self.merger.merge(["gpt2", "distilgpt2"], method="ties", density=0.5)
        self.assertEqual(exp.technique, "ties")
        self.assertEqual(exp.source_models, ["gpt2", "distilgpt2"])
        self.assertIn("Config validated", exp.notes)

    def test_merge_config_validation(self):
        exp = self.merger.merge(["gpt2", "distilgpt2"], method="dare")
        config = self.merger.create_merge_config(exp)
        self.assertEqual(config.merge_method, "dare")

    def test_experiment_tracking(self):
        self.merger.merge(["gpt2", "distilgpt2"], method="ties")
        self.merger.merge(["gpt2", "distilgpt2"], method="slerp")
        self.assertEqual(len(self.merger.experiments), 2)

    def test_improvement_calculation(self):
        exp = self.merger.merge(["a", "b"])
        exp.benchmark_before = {"mmlu": 80.0, "gsm8k": 70.0}
        exp.benchmark_after = {"mmlu": 84.0, "gsm8k": 73.0}
        self.assertAlmostEqual(exp.improvement, 4.667, places=1)


if __name__ == "__main__":
    unittest.main()
