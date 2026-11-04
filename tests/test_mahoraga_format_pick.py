"""prefer_complete_format / pick_weight_index seçimi — unittest-uyumlu."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import huggingface_hub  # ağır opsiyonel bağımlılık (ameliyat ortamı)
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest(f"huggingface_hub yok: {exc}")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.mahoraga.real_surgery import prefer_complete_format, pick_weight_index


def _mk(d, names_sizes):
    for n, sz in names_sizes.items():
        with open(os.path.join(d, n), "wb") as f:
            f.truncate(sz)


class TestFormatPick(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_uses_complete_consolidated_when_shards_absent(self):
        names = {"consolidated-00001-of-00002.safetensors": 10,
                 "consolidated-00002-of-00002.safetensors": 20,
                 "model-00001-of-00002.safetensors": 10,
                 "model-00002-of-00002.safetensors": 20,
                 "config.json": 5}
        _mk(self.tmp, {"consolidated-00001-of-00002.safetensors": 10,
                       "consolidated-00002-of-00002.safetensors": 20})
        out, missing = prefer_complete_format(names, str(self.tmp))
        self.assertEqual(missing, [])
        self.assertNotIn("model-00001-of-00002.safetensors", out)
        self.assertIn("consolidated-00002-of-00002.safetensors", out)

    def test_keeps_shards_when_consolidated_incomplete(self):
        names = {"consolidated-00001-of-00002.safetensors": 10,
                 "consolidated-00002-of-00002.safetensors": 20,
                 "model-00001-of-00002.safetensors": 10,
                 "model-00002-of-00002.safetensors": 20}
        _mk(self.tmp, {"consolidated-00001-of-00002.safetensors": 10})
        out, missing = prefer_complete_format(names, str(self.tmp))
        self.assertIn("model-00002-of-00002.safetensors", out)
        self.assertTrue(missing)  # shard indirme hala gerekli

    def test_size_mismatch_counts_as_incomplete(self):
        names = {"consolidated-00001-of-00001.safetensors": 10,
                 "model-00001-of-00001.safetensors": 10}
        _mk(self.tmp, {"consolidated-00001-of-00001.safetensors": 7})
        out, missing = prefer_complete_format(names, str(self.tmp))
        self.assertIn("model-00001-of-00001.safetensors", out)
        self.assertTrue(missing)

    def test_index_choice_follows_complete_format(self):
        cons = {f"consolidated-0000{i}-of-00002.safetensors": 10 for i in (1, 2)}
        shd = {f"model-0000{i}-of-00002.safetensors": 10 for i in (1, 2)}
        _mk(self.tmp, cons)  # tam consolidated seti
        _mk(self.tmp, {"model-00001-of-00002.safetensors": 3})  # yarim shard
        (self.tmp / "consolidated.safetensors.index.json").write_text(json.dumps(
            {"weight_map": {"a": "consolidated-00001-of-00002.safetensors", "b": "consolidated-00002-of-00002.safetensors"}}))
        (self.tmp / "model.safetensors.index.json").write_text(json.dumps(
            {"weight_map": {"a": "model-00001-of-00002.safetensors", "b": "model-00002-of-00002.safetensors"}}))
        chosen = pick_weight_index(str(self.tmp))
        self.assertEqual(chosen.name, "consolidated.safetensors.index.json")


if __name__ == "__main__":
    unittest.main()
