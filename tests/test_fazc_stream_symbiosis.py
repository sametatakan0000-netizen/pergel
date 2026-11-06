"""Faz-C Akış Bağlama (Stream Symbiosis) — davranış test yığını (TDD RED).

Tasarım: docs/fazc-akisa-baglama-tasarim.md §3. Pilot modül:
src/mahoraga/fazc_stream_symbiosis.py
"""
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.mahoraga.fazc_stream_symbiosis import (
    CrossArchMergeError,
    RedundancyError,
    StreamSymbiosis,
    sigma_wv,
)


def _write_safetensors(path: Path, tensors: dict) -> dict:
    """Gerçek safetensors formatında küçük fixture yazar (header + ham bayt).

    Dönüş: manifest 'tensors' listesi (mutlak bayt aralıkları — blok akışı
    os.pread ile yalnız bu aralıkları okur).
    """
    header = {}
    offset = 0
    for key, arr in tensors.items():
        arr = np.ascontiguousarray(arr, dtype=np.float32)
        nbytes = arr.nbytes
        header[key] = {
            "dtype": "F32",
            "shape": list(arr.shape),
            "data_offsets": [offset, offset + nbytes],
        }
        offset += nbytes
    hdr_bytes = json.dumps(header).encode("utf-8")
    data_start = 8 + len(hdr_bytes)
    entries = []
    for key, arr in tensors.items():
        arr = np.ascontiguousarray(arr, dtype=np.float32)
        entries.append({
            "key": key,
            "offset": data_start + header[key]["data_offsets"][0],
            "nbytes": arr.nbytes,
            "shape": list(arr.shape),
            "dtype": "F32",
        })
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(hdr_bytes)))
        f.write(hdr_bytes)
        for arr in tensors.values():
            f.write(np.ascontiguousarray(arr, dtype=np.float32).tobytes())
    return entries


def _build_fixture(root: Path) -> Path:
    """3 uzman + 1 düşük kaliteli uzman; 4-kopya yedek manifestiyle."""
    experts = {}
    specs = [
        ("kod-uzman", "kod", 0.90),
        ("guvenlik-uzman", "guvenlik", 0.85),
        ("dil-uzman", "dil", 0.80),
        ("eski-uzman", "kod", 0.65),  # kalite hunisi: eşik (%70) altı
    ]
    for name, role, score in specs:
        f = root / f"{name}.safetensors"
        tensors = {
            f"model.layers.{i}.mlp.up_proj.weight": np.full((64,), i + 1.0)
            for i in range(4)
        }
        entries = _write_safetensors(f, tensors)
        experts[name] = {
            "role": role,
            "behavior_score": score,
            "file": f.name,
            "tensors": entries,
            "copies": [str(root / f"{name}.safetensors")] + [
                f"/mnt/toshiba/mahoraga/synapse_backups{suffix}/winners/{name}"
                for suffix in ("", "_b", "_c")
            ],
        }
    (root / "stream_manifest.json").write_text(json.dumps({"experts": experts}))
    return root


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _build_fixture(Path(self.tmp.name))
        self.sym = StreamSymbiosis(str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_route_selects_expert_by_role(self):
        kod = self.sym.route("def test(): return python bug fix refactor")
        guv = self.sym.route("security vulnerability exploit xss injection")
        self.assertEqual(kod[0], "kod-uzman")
        self.assertEqual(guv[0], "guvenlik-uzman")
        # Saf EN ilkesi: skor sırası kesin, denge/bonus terimi yok
        scores = self.sym.role_scores("security vulnerability exploit xss injection")
        self.assertGreater(scores["guvenlik"], scores["kod"])

    def test_route_respects_quality_funnel(self):
        # eski-uzman (0.65 < 0.70) tek kod adayı olsa bile asla yüklenmez
        picked = self.sym.route("def f(): bug in python code", roles=["kod"])
        self.assertNotIn("eski-uzman", picked)
        for name in picked:
            self.assertGreaterEqual(self.sym.experts[name]["behavior_score"], 0.70)


class TestStreamExpert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _build_fixture(Path(self.tmp.name))
        self.sym = StreamSymbiosis(str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_stream_expert_reads_only_requested_blocks(self):
        full = self.sym.experts["kod-uzman"]["total_bytes"]
        blocks = list(self.sym.stream_expert("kod-uzman", [0, 2]))
        self.assertEqual(len(blocks), 2)
        self.assertGreater(self.sym.last_stream_bytes, 0)
        self.assertLess(self.sym.last_stream_bytes, full)  # lazy kanıtı
        # İstenen bloklar gerçekten doğru tensörler
        self.assertEqual([b.shape for b in blocks], [(64,), (64,)])
        np.testing.assert_allclose(blocks[0], np.full((64,), 1.0))


class TestTeacherAndDistill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _build_fixture(Path(self.tmp.name))
        self.sym = StreamSymbiosis(str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_consult_teacher_no_full_load(self):
        teacher = {"name": "dev-ogretmen", "layers": 61, "layer_bytes": 700_000_000}
        ts = self.sym.consult_teacher("bir prompt", teacher)
        budget = 8 * 1024**3
        self.assertLessEqual(ts.offload["gpu_bytes"], budget)  # 8GB VRAM bütçesi
        self.assertEqual(
            ts.offload["layers_on_gpu"] + ts.offload["layers_on_cpu"], 61)
        self.assertGreater(ts.offload["layers_on_cpu"], 0)  # tam yükleme YOK
        self.assertIsNone(ts.score)  # puanlayıcı yoksa uydurma puan YOK

    def test_distill_gap_triggers_only_on_gate_miss(self):
        passed = self.sym.distill_gap("swe-smith", gap=0.0)
        missed = self.sym.distill_gap("swe-smith", gap=0.12)
        self.assertFalse(passed.triggered)   # kapı geçildi → LoRA yok
        self.assertTrue(missed.triggered)    # boşluk kaldı → LoRA düzeltmesi
        self.assertEqual(missed.adapter, "unsloth-lora")


class TestSigmaWvAndCopies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _build_fixture(Path(self.tmp.name))
        self.sym = StreamSymbiosis(str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_sigma_wv_same_shape_only(self):
        v1 = np.ones((4,), dtype=np.float32)
        v2 = np.full((4,), 3.0, dtype=np.float32)
        merged = sigma_wv([
            {"key": "layers.0.q_proj.weight", "shape": (4,), "w": 0.5, "v": v1},
            {"key": "layers.0.q_proj.weight", "shape": (4,), "w": 1.5, "v": v2},
        ])
        np.testing.assert_allclose(
            merged["layers.0.q_proj.weight"], 0.5 * v1 + 1.5 * v2)
        # Cross-arch: aynı anahtar ama farklı şekil → doğrudan birleştirme YOK
        with self.assertRaises(CrossArchMergeError):
            sigma_wv([
                {"key": "layers.0.q_proj.weight", "shape": (8192, 8192), "w": 1.0,
                 "v": np.ones((2, 2), dtype=np.float32)},
                {"key": "layers.0.q_proj.weight", "shape": (4096, 4096), "w": 1.0,
                 "v": np.ones((2, 2), dtype=np.float32)},
            ])

    def test_expert_sources_have_4_copies(self):
        self.assertTrue(self.sym.verify_redundancy())  # 4 kopya manifesti tam
        self.sym.experts["kod-uzman"]["copies"] = self.sym.experts["kod-uzman"][
            "copies"][:3]  # bir kopya kayıp
        with self.assertRaises(RedundancyError):
            self.sym.verify_redundancy()


if __name__ == "__main__":
    unittest.main()
