"""classify_key düzeni + metadata-only kayıt toleransı için birim testler.

Kök neden (2026-11-05 DeepSeek-V4.1-Flash anomalisi):
- 'embed' kontrolü 'engram' kontrolünden ÖNCE idi ->
  layers.14.engram.embed.weight (98B) embedding_in/vocab_io'ya düşüyordu.
- Metadata-only envanter kayıtlarında hash/magnitude yoktur;
  summarize() bunları hata/sahte sıfır olarak saymamalı.
"""
from mahoraga.synapse_inventory import classify_key, summarize, ROLE_MAP


class TestClassifyOrder:
    def test_engram_embed_is_knowledge_not_vocab(self):
        # RED: 'engram.embed' adı 'embed' yüzünden yakalanıyordu
        assert classify_key("layers.14.engram.embed.weight") == "engram_memory"
        assert ROLE_MAP["engram_memory"] == "knowledge"

    def test_engram_scale(self):
        assert classify_key("layers.14.engram.embed.scale") == "engram_memory"

    def test_plain_vocab_embed_still_vocab(self):
        assert classify_key("embed.weight") == "embedding_in"
        assert classify_key("model.embed_tokens.weight") == "embedding_in"

    def test_ple_lookup_memory_before_embed(self):
        assert classify_key("model.layers.3.ple.ple_embedding.weight") == "lookup_memory"

    def test_vision_patch_embed_stays_vision(self):
        assert classify_key("vision.patch_embed.proj.weight") == "vision_tower"

    def test_engram_kv_pairs(self):
        assert classify_key("layers.14.engram.k_weight") == "engram_memory"
        assert classify_key("layers.1.engram.v_weight") == "engram_memory"


class TestMetadataOnlyRecords:
    def _rec(self, key, n, **extra):
        r = {"key": key, "shape": [n], "n_synapses": n}
        r.update(extra)
        return r

    def test_metadata_only_no_crash_no_fake_zero(self):
        recs = [
            self._rec("embed.weight", 10, hash="aa", magnitude=1.5),
            self._rec("layers.0.mlp.down_proj.weight", 20),  # metadata-only
        ]
        s = summarize(recs)
        assert s["synapse_sum"] == 30
        assert s["metadata_only"] == 1
        assert s["zero_magnitude"] == []          # bilinmeyen != sıfır
        assert s["dup_hash_pairs"] == []

    def test_real_zero_magnitude_still_flagged(self):
        recs = [self._rec("x.weight", 5, hash="bb", magnitude=0.0)]
        s = summarize(recs)
        assert s["zero_magnitude"] == ["x.weight"]
