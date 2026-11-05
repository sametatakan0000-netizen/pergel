"""TDD: Mahoraga Faz 1 - Synapse Profiler (sinaps anatomisi sınıflandırıcısı).

SOTA dayanağı: MLP = bilgi deposu (Geva 2021; Meng/ROME 2022),
attention = bilgi yönlendirme, norm = ölçek, filtre (refusal) = artık-akış yönü
(Arditi 2024) — tensör değil, tüm artık-akış yazan matrislerden geçer.
"""
import unittest

from src.mahoraga.synapse_inventory import classify_key, summarize, ROLE_MAP


class TestClassifyKey(unittest.TestCase):
    CASES = [
        # gömme / baş
        ("model.embed_tokens.weight", "embedding_in"),
        ("transformer.wte.weight", "embedding_in"),
        ("lm_head.weight", "embedding_out"),
        # dikkat (Llama/Mistral/DeepSeek/Qwen stili)
        ("model.layers.5.self_attn.q_proj.weight", "attention_q"),
        ("model.layers.5.self_attn.k_proj.weight", "attention_k"),
        ("model.layers.5.self_attn.v_proj.weight", "attention_v"),
        ("model.layers.5.self_attn.o_proj.weight", "attention_out"),
        ("model.layers.5.self_attn.q_proj.bias", "attention_q"),
        # birleşik QKV varyantları
        ("transformer.h.0.attn.c_attn.weight", "attention_qkv"),
        ("model.layers.0.self_attn.query_key_value.weight", "attention_qkv"),
        # dense MLP (SwiGLU + klasik)
        ("model.layers.5.mlp.gate_proj.weight", "mlp_gate"),
        ("model.layers.5.mlp.up_proj.weight", "mlp_up"),
        ("model.layers.5.mlp.down_proj.weight", "mlp_down"),
        ("model.layers.3.mlp.w1.weight", "mlp_gate"),
        ("model.layers.3.mlp.w2.weight", "mlp_down"),
        # MoE uzmanları (Mixtral w1/w2/w3, DeepSeek gate/up/down)
        ("model.layers.2.block_sparse_moe.experts.3.w1.weight", "moe_expert_gate"),
        ("model.layers.2.block_sparse_moe.experts.3.w2.weight", "moe_expert_down"),
        ("model.layers.2.block_sparse_moe.experts.3.w3.weight", "moe_expert_up"),
        ("model.layers.2.mlp.experts.7.gate_proj.weight", "moe_expert_gate"),
        ("model.layers.2.mlp.experts.7.up_proj.weight", "moe_expert_up"),
        ("model.layers.2.mlp.experts.7.down_proj.weight", "moe_expert_down"),
        ("model.layers.2.mlp.shared_experts.gate_proj.weight", "moe_expert_gate"),
        # MoE yönlendirici (Mixtral + DeepSeek stilleri)
        ("model.layers.2.block_sparse_moe.gate.weight", "moe_router"),
        ("model.layers.2.mlp.gate.weight", "moe_router"),
        # normlar (attn geçişinden ÖNCE eşleşmeli)
        ("model.layers.5.input_layernorm.weight", "norm"),
        ("model.layers.5.post_attention_layernorm.weight", "norm"),
        ("model.layers.5.post_self_attn_layernorm.weight", "norm"),
        ("model.norm.weight", "norm"),
        ("model.layers.5.input_layernorm.bias", "norm"),
        # Mistral-Large/internlm stili feed_forward
        ("layers.0.feed_forward.w1.weight", "mlp_gate"),
        ("layers.0.feed_forward.w2.weight", "mlp_down"),
        ("layers.0.feed_forward.w3.weight", "mlp_up"),
        # birleşik SwiGLU (Phi-4 dense + Qwen3.8 MoE uzmanları)
        ("model.layers.20.mlp.gate_up_proj.weight", "mlp_gate_up"),
        ("model.language_model.layers.0.mlp.experts.gate_up_proj",
         "moe_expert_gate_up"),
        # ortak uzman kapısı = yönlendirici
        ("model.layers.0.mlp.shared_expert_gate.weight", "moe_router"),
        # çoklu-token tahmin başlığı
        ("mtp.fc.weight", "mtp_head"),
        ("model.layers.0.mtp.fc.weight", "mtp_head"),
        # hiper-bağlantılar artık-ışak karıştırıcıları
        ("model.language_model.hyper_connection_mixer.input_mix_weight_down.weight",
         "hyper_mixer"),
        ("model.layers.0.attn_hyper_connection.block_inject_weight.weight",
         "hyper_mixer"),
        # görsel kule (VL modelleri)
        ("model.visual.blocks.0.mlp.linear_fc1.bias", "vision_tower"),
        ("vision_model.radio_model.model.blocks.0.attn.proj.bias", "vision_tower"),
        ("model.visual.merger.linear_fc1.bias", "vision_tower"),
        # Mamba/SSM karıştırıcı (Nemotron-Bolt)
        ("language_model.backbone.layers.0.mixer.A_log", "ssm_mixer"),
        ("language_model.backbone.layers.0.mixer.out_proj.weight", "ssm_mixer"),
        # DeepSeek Engram bellek modülü
        ("layers.14.engram.k_weight", "engram_memory"),
        # Qwen3.8 PLE = n-gram arama tablosu bellek modülü (Engram akrabası)
        ("model.language_model.layers.1.ple.key_proj.weight", "lookup_memory"),
        ("model.language_model.layers.1.ple.value_proj.weight", "lookup_memory"),
        ("model.language_model.layers.1.ple.conv1d.weight", "lookup_memory"),
        ("model.language_model.layers.2.ple.ple_embedding.ngram_embedding.shard_0.weight",
         "lookup_memory"),
        # Qwen3-Next doğrusal (GDN) attention — routing, ama bilinçli olarak other
        ("model.language_model.layers.0.linear_attn.A_log", "attention_other"),
        ("model.language_model.layers.0.linear_attn.in_proj_qkv.weight",
         "attention_qkv"),
    ]

    def test_known_categories(self):
        for key, expected in self.CASES:
            with self.subTest(key=key):
                self.assertEqual(classify_key(key), expected)

    def test_unknown_keys_reported(self):
        self.assertEqual(classify_key("foo.bar.baz.weight"), "unknown")
        self.assertEqual(classify_key("transformer.h.0.attn.c_proj.weight"),
                         "attention_out")

    def test_every_category_has_role(self):
        roles = {exp for _, exp in self.CASES} | {"unknown"}
        for cat in roles:
            self.assertIn(cat, ROLE_MAP, f"{cat} ROLE_MAP'te yok")


class TestSummarize(unittest.TestCase):
    REC = [
        {"key": "model.embed_tokens.weight", "shape": [10, 4],
         "n_synapses": 40, "hash": "aa", "magnitude": 0.1},
        {"key": "lm_head.weight", "shape": [10, 4],
         "n_synapses": 40, "hash": "aa", "magnitude": 0.1},  # tied -> dup hash
        {"key": "model.layers.0.mlp.down_proj.weight", "shape": [4, 8],
         "n_synapses": 32, "hash": "bb", "magnitude": 0.0},
        {"key": "weird.thing.weight", "shape": [2, 2],
         "n_synapses": 4, "hash": "cc", "magnitude": 0.2},
    ]

    def test_aggregation(self):
        s = summarize(self.REC)
        self.assertEqual(s["categories"]["embedding_in"]["tensors"], 1)
        self.assertEqual(s["categories"]["embedding_in"]["synapses"], 40)
        self.assertEqual(s["categories"]["mlp_down"]["synapses"], 32)
        self.assertEqual(s["roles"]["knowledge"]["synapses"], 32)

    def test_residual_writers_two_dimensional(self):
        # down_proj = bilgi (ROME değer vektörü) AMA aynı zamanda artık-ışak
        # yazarı (Arditi filtre yönü buradan geçer); lm_head yazmaz.
        s = summarize(self.REC)
        self.assertEqual(s["roles"]["knowledge"]["synapses"], 32)
        self.assertEqual(s["residual_writers"]["synapses"], 40 + 32)
        self.assertEqual(s["residual_writers"]["tensors"], 2)

    def test_dup_hash_flagged(self):
        s = summarize(self.REC)
        self.assertEqual(len(s["dup_hash_pairs"]), 1)
        self.assertEqual(
            set(s["dup_hash_pairs"][0]),
            {"model.embed_tokens.weight", "lm_head.weight"})

    def test_zero_magnitude_flagged(self):
        s = summarize(self.REC)
        self.assertEqual(s["zero_magnitude"],
                         ["model.layers.0.mlp.down_proj.weight"])

    def test_unknown_keys_listed(self):
        s = summarize(self.REC)
        self.assertEqual(s["unknown_keys"], ["weird.thing.weight"])

    def test_synapse_sum_matches(self):
        s = summarize(self.REC)
        self.assertEqual(s["synapse_sum"], 116)
        self.assertTrue(s["sum_check"])


if __name__ == "__main__":
    unittest.main()
