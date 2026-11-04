"""Büyük tensörler chunk'lanarak işlenmeli: OOM olmadan aynı hash/magnitude.

unittest-uyumlu (pytest yok; importorskip yerine SkipTest).
"""
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

try:
    import torch  # ağır opsiyonel bağımlılık (GPU ameliyat ortamı)
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest(f"torch yok: {exc}")


def _reference_record(tensor, key):
    """Eski satır içi algoritma (birebir) — referans davranış."""
    n = tensor.numel()
    sample = tensor.reshape(-1)[::max(1, n // 100)][:100]
    h = hashlib.sha256()
    for v in sample.to(torch.float32).tolist():
        h.update(struct.pack("f", v))
    mag = float(tensor.to(torch.float32).abs().mean())
    return {"key": key, "shape": list(tensor.shape), "n_synapses": n,
            "hash": h.hexdigest()[:16], "magnitude": mag}


class TestChunkedExtract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_st(self, tensors):
        from safetensors.torch import save_file
        path = self.tmp / "shard.safetensors"
        save_file(tensors, str(path))
        return path

    def test_chunked_matches_reference_small_tensor(self):
        from safetensors import safe_open
        from src.mahoraga.real_surgery import tensor_record_chunked
        torch.manual_seed(7)
        t = torch.randn(400, 64, dtype=torch.bfloat16)
        path = self._make_st({"layers.0.w": t})
        with safe_open(str(path), framework="pt") as f:
            rec = tensor_record_chunked(f, "layers.0.w", chunk_elems=1000)
        ref = _reference_record(t, "layers.0.w")
        self.assertEqual(rec["hash"], ref["hash"])
        self.assertEqual(rec["n_synapses"], ref["n_synapses"])
        self.assertLess(abs(rec["magnitude"] - ref["magnitude"]), 1e-4)

    def test_chunked_handles_multidim_row_chunking(self):
        from safetensors import safe_open
        from src.mahoraga.real_surgery import tensor_record_chunked
        torch.manual_seed(11)
        t = torch.randn(3, 500, 7, dtype=torch.bfloat16)
        path = self._make_st({"layers.3.w": t})
        with safe_open(str(path), framework="pt") as f:
            rec = tensor_record_chunked(f, "layers.3.w", chunk_elems=2000)
        ref = _reference_record(t, "layers.3.w")
        self.assertEqual(rec["hash"], ref["hash"])
        self.assertEqual(rec["shape"], [3, 500, 7])

    def test_chunked_1d_tensor(self):
        from safetensors import safe_open
        from src.mahoraga.real_surgery import tensor_record_chunked
        torch.manual_seed(3)
        t = torch.randn(10000, dtype=torch.float32)
        path = self._make_st({"bias": t})
        with safe_open(str(path), framework="pt") as f:
            rec = tensor_record_chunked(f, "bias", chunk_elems=999)
        ref = _reference_record(t, "bias")
        self.assertEqual(rec["hash"], ref["hash"])
        self.assertLess(abs(rec["magnitude"] - ref["magnitude"]), 1e-4)


if __name__ == "__main__":
    unittest.main()
