import json, struct, os
from pathlib import Path

from src.mahoraga.stream_surgery import safetensors_complete


def _write_fake_st(path: Path, tensors_bytes: int, truncate=False):
    """Basit sahte safetensors: 8 bayt header uzunlugu + header + veri."""
    hdr = {"t": {"dtype": "F32", "shape": [tensors_bytes // 4], "data_offsets": [0, tensors_bytes]}}
    h = json.dumps(hdr).encode()
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(h)))
        f.write(h)
        f.write(b"\x00" * tensors_bytes)
    if truncate:
        with open(path, "r+b") as f:
            f.truncate(os.path.getsize(path) - 10)


def test_complete_file_is_detected(tmp_path):
    p = tmp_path / "model-00001-of-00001.safetensors"
    _write_fake_st(p, tensors_bytes=64)
    assert safetensors_complete(p) is True


def test_truncated_file_is_not_complete(tmp_path):
    p = tmp_path / "model-00001-of-00001.safetensors"
    _write_fake_st(p, tensors_bytes=64, truncate=True)
    assert safetensors_complete(p) is False


def test_missing_file_is_not_complete(tmp_path):
    assert safetensors_complete(tmp_path / "yok.safetensors") is False
