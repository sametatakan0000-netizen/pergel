"""Checkpoint / kaldığı yerden devam testleri.

USB kopması, restart veya crash'te ilerleme NVMe checkpoint'ine yazılır ve
işlenen safetensors dosyaları atlanır (ALTIN-KIRMIZI kural: sinapslar asla
kaybedilmez, ilerleme de kaybedilmemeli).
"""
import json
import shutil

import unittest, importlib.util
if importlib.util.find_spec("huggingface_hub") is None:
    raise unittest.SkipTest("huggingface_hub yok (agir opsiyonel bagimlilik, ameliyat ortami)")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
from safetensors.torch import save_file

from src.mahoraga.real_surgery import RealSurgery, sanitize


class TestSurgeryCheckpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.model_dir = self.tmp / "model"
        self.model_dir.mkdir()
        self.backup_dir = self.tmp / "backups"
        for i, name in enumerate(["model-00001-of-00002.safetensors",
                                  "model-00002-of-00002.safetensors"]):
            save_file(
                {f"model.layers.{i}.weight": torch.randn(4, 4),
                 f"model.layers.{i}.bias": torch.randn(4)},
                str(self.model_dir / name),
            )
        self.surgery = RealSurgery(backup_dir=str(self.backup_dir),
                                   work_dir=str(self.tmp / "work"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ckpt(self):
        return self.backup_dir / ".ckpt" / (sanitize("org/model-x") + ".jsonl")

    def test_checkpoint_written_and_resume_identical(self):
        full = self.surgery.extract_weight_synapses(str(self.model_dir), "org/model-x")
        ckpt = self._ckpt()
        self.assertTrue(ckpt.exists(), "checkpoint dosyası yazılmış olmalı")
        self.assertEqual(len(ckpt.read_text().strip().splitlines()), 2)
        # yeniden çalıştır: checkpoint'ten yüklenmeli, sonuç birebir aynı olmalı
        resumed = self.surgery.extract_weight_synapses(str(self.model_dir), "org/model-x")
        self.assertEqual(full["total_synapses"], resumed["total_synapses"])
        self.assertEqual(full["tensors"], resumed["tensors"])

    def test_partial_checkpoint_reprocesses_missing_file(self):
        self.surgery.extract_weight_synapses(str(self.model_dir), "org/model-x")
        ckpt = self._ckpt()
        lines = ckpt.read_text().strip().splitlines()
        ckpt.write_text(lines[0] + "\n")  # ikinci dosya kaybı simülasyonu (crash)
        resumed = self.surgery.extract_weight_synapses(str(self.model_dir), "org/model-x")
        keys = {t["key"] for t in resumed["tensors"]}
        self.assertEqual(len(keys), 4)  # 2 dosya x 2 tensör — eksiksiz
        self.assertEqual(resumed["total_synapses"], 2 * (16 + 4))  # 2 dosya x (4x4 + 4)

    def test_run_surgery_removes_checkpoint_after_verified_backup(self):
        with mock.patch.object(RealSurgery, "download_model",
                               return_value=str(self.model_dir)), \
             mock.patch.object(RealSurgery, "delete_model_body"):
            result = self.surgery.run_surgery("org/model-x")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(self._ckpt().exists(), "yedek doğrulanınca checkpoint silinmeli")
        self.assertTrue(Path(result["backup_path"]).exists())


if __name__ == "__main__":
    unittest.main()
