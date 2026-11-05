"""Filtre Yüzeyi Envanteri testleri (Faz 2 / Adım 1).

TDD kanunu: bu dosya önce yazılır, önce FAILED olur (RED),
ardından src/mahoraga/filter_surface.py ile geçer (GREEN).

Kural (Arditi + kamuya açık abliteration reçeteleri):
filtre yüzeyi = artık akışa veya kelime uzayına YAZAN kapılar
(o_proj, down/w2, embed, lm_head/mtp_head, bellek yük yolları);
gate/yönlendirme (q/k/v, router, key_proj, k_weight), normlar
ve görsel kule yüzeyde DEĞİLDİR (yazmazlar).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.filter_surface import (
    is_filter_surface,
    surface_for_model,
    attach_shard,
    download_plan,
    WRITER_CATEGORIES,
)
from src.mahoraga.synapse_inventory import ROLE_MAP, classify_key


def _t(key, n):
    return {"key": key, "shape": [n], "n_synapses": n, "hash": "h", "magnitude": 0.1}


SYNTH = {
    "model": "synthetic/test",
    "tensors": [
        _t("model.embed_tokens.weight", 40),          # yüzey (kelime yazarı)
        _t("model.layers.0.self_attn.o_proj.weight", 40),  # yüzey (artık yazar)
        _t("model.layers.0.self_attn.q_proj.weight", 40),  # DEĞİL (gate)
        _t("model.layers.0.mlp.down_proj.weight", 40),     # yüzey (artık yazar)
        _t("model.layers.0.mlp.gate_proj.weight", 40),     # DEĞİL (gate/up)
        _t("lm_head.weight", 40),                          # yüzey (kelime yazarı)
        _t("model.layers.0.input_layernorm.weight", 4),    # DEĞİL (norm)
    ],
}


class TestFilterSurfaceRules(unittest.TestCase):
    def test_attn_out_is_surface(self):
        self.assertTrue(is_filter_surface("layers.0.self_attn.o_proj.weight", "attention_out"))

    def test_mlp_down_is_surface(self):
        self.assertTrue(is_filter_surface("layers.0.mlp.down_proj.weight", "mlp_down"))

    def test_moe_expert_down_is_surface(self):
        self.assertTrue(is_filter_surface("layers.3.block_sparse_moe.experts.7.w2.weight",
                                          "moe_expert_down"))

    def test_embedding_is_surface(self):
        self.assertTrue(is_filter_surface("model.embed_tokens.weight", "embedding_in"))

    def test_lm_head_is_surface(self):
        self.assertTrue(is_filter_surface("lm_head.weight", "embedding_out"))

    def test_mtp_head_is_surface(self):
        self.assertTrue(is_filter_surface("model.layers.3.mtp_head.weight", "mtp_head"))

    def test_ple_payload_is_surface(self):
        self.assertTrue(is_filter_surface("layers.1.ple.value_proj.weight", "lookup_memory"))
        self.assertTrue(is_filter_surface("layers.1.ple.conv1d.weight", "lookup_memory"))

    def test_ple_gate_is_not_surface(self):
        self.assertFalse(is_filter_surface("layers.1.ple.key_proj.weight", "lookup_memory"))
        self.assertFalse(is_filter_surface("layers.1.ple.norm_key.weight", "lookup_memory"))

    def test_engram_payload_is_surface(self):
        self.assertTrue(is_filter_surface("layers.14.engram.v_weight", "engram_memory"))

    def test_engram_gate_is_not_surface(self):
        self.assertFalse(is_filter_surface("layers.14.engram.k_weight", "engram_memory"))

    def test_ssm_out_proj_is_surface(self):
        self.assertTrue(is_filter_surface("layers.2.mixer.out_proj.weight", "ssm_mixer"))
        self.assertFalse(is_filter_surface("layers.2.mixer.in_proj.weight", "ssm_mixer"))

    def test_gates_are_not_surface(self):
        for key in ("layers.0.self_attn.q_proj.weight",
                    "layers.0.self_attn.k_proj.weight",
                    "layers.0.self_attn.v_proj.weight",
                    "layers.0.mlp.up_proj.weight",
                    "layers.0.mlp.gate_proj.weight",
                    "layers.3.block_sparse_moe.gate.weight"):
            self.assertFalse(is_filter_surface(key), key)

    def test_norms_are_not_surface(self):
        self.assertFalse(is_filter_surface("layers.0.input_layernorm.weight", "norm"))

    def test_vision_is_out_of_text_scope(self):
        self.assertFalse(is_filter_surface("model.visual.merger.mlp.0.weight", "vision_tower"))

    def test_writer_categories_are_known_roles(self):
        for cat in WRITER_CATEGORIES:
            self.assertIn(cat, ROLE_MAP)

    def test_rule_agrees_with_anatomy_classify(self):
        # kategori verilmediğinde sınıflandırıcıdan türetilmeli
        self.assertTrue(is_filter_surface("layers.2.block_sparse_moe.experts.3.w2.weight"))
        self.assertFalse(is_filter_surface("layers.2.self_attn.q_proj.weight"))


class TestSurfaceModelReport(unittest.TestCase):
    def test_surface_counts(self):
        rep = surface_for_model(SYNTH)
        self.assertEqual(rep["total_tensor_count"], 7)
        self.assertEqual(rep["surface_tensor_count"], 4)
        self.assertEqual(rep["surface_synapses"], 160)
        self.assertEqual(rep["total_synapses"], 244)

    def test_surface_sum_check(self):
        rep = surface_for_model(SYNTH)
        listed = sum(t["n_synapses"] for t in rep["tensors"])
        self.assertEqual(listed, rep["surface_synapses"])
        self.assertLessEqual(rep["surface_synapses"], rep["total_synapses"])
        self.assertTrue(rep["sum_check"])

    def test_only_surface_tensors_listed(self):
        rep = surface_for_model(SYNTH)
        keys = {t["key"] for t in rep["tensors"]}
        self.assertNotIn("model.layers.0.self_attn.q_proj.weight", keys)
        self.assertIn("model.layers.0.mlp.down_proj.weight", keys)

    def test_attach_shard_and_download_plan(self):
        weight_map = {
            "model.embed_tokens.weight": "model-00001-of-00002.safetensors",
            "model.layers.0.self_attn.o_proj.weight": "model-00001-of-00002.safetensors",
            "model.layers.0.mlp.down_proj.weight": "model-00002-of-00002.safetensors",
            "lm_head.weight": "model-00002-of-00002.safetensors",
        }
        rep = attach_shard(surface_for_model(SYNTH), weight_map)
        self.assertEqual({t["shard"] for t in rep["tensors"]},
                         {"model-00001-of-00002.safetensors",
                          "model-00002-of-00002.safetensors"})
        plan = download_plan(rep)
        self.assertEqual(sorted(plan["shards"].keys()),
                         ["model-00001-of-00002.safetensors",
                          "model-00002-of-00002.safetensors"])
        self.assertEqual(plan["shards"]["model-00001-of-00002.safetensors"]["tensors"], 2)
        self.assertEqual(plan["total_download_shards"], 2)

    def test_missing_index_marks_unknown_shard(self):
        rep = attach_shard(surface_for_model(SYNTH), {})
        self.assertEqual({t["shard"] for t in rep["tensors"]}, {"index_bilinmiyor"})
        plan = download_plan(rep)
        self.assertEqual(plan["total_download_shards"], 1)

    def test_shard_match_is_normalized(self):
        # HF index anahtarları "model." öneki + ".weight" soneki taşır;
        # envanter anahtarlarımız bunlarsız gelebilir — normalleştirerek eşleşmeli.
        weight_map = {
            "model.model.embed_tokens.weight": "shardA",
            "model.lm_head.weight": "shardB",
        }
        rep = attach_shard(surface_for_model(SYNTH), weight_map)
        by_key = {t["key"]: t["shard"] for t in rep["tensors"]}
        self.assertEqual(by_key["model.embed_tokens.weight"], "shardA")
        self.assertEqual(by_key["lm_head.weight"], "shardB")


if __name__ == '__main__':
    unittest.main()