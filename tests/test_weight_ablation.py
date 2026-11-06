"""Multi-D weight abliteration — birim testleri (stdlib unittest; pytest YASAK).

Kapsam (TDD — bu dosya implementasyondan ÖNCE yazıldı):
- yazar (residual writer) projeksiyon matematiği: R satırları çıktının
  satır-uzayından silinir (||R @ W'||_F ~ 0)
- okuyucu (residual reader) ve gömme projeksiyon matematiği
- hedef olmayan tensörler bayt-bayt aynı kalır
- shard roundtrip: test içinde kurulan 2-shard sentetik safetensors gövde
- manifest alanları (kaynak+yönlü hash'ler, yönler, normlar, sayaçlar, zaman)
- güvenli yazım: tmp + os.replace (resume-safe), GOLDEN-RED kaynak dokunulmaz
- yön tespiti: difference-of-means (son-token resid_post), katman sıralama
- CLI: scripts/ablate_weights.py bayrakları

Tüm tensörler minik (d_model=8, vocab=16); testler CPU'da saniyeler sürer.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src.mahoraga.weight_ablation import (
    DEFAULT_TARGETS,
    apply_ablation,
    classify_target,
    default_out_dir,
    detect_directions,
    load_prompts,
    orthonormalize,
    parse_layers,
    parse_targets,
    project_embedding,
    project_reader,
    project_writer,
)

D_MODEL = 8
VOCAB = 16

# ---------------------------------------------------------------------------
# sentetik safetensors yardımcıları (bağımsız ham-bayt okuyucu/yazıcı)
# ---------------------------------------------------------------------------

_ST_DTYPE = {np.dtype(np.float32): "F32", np.dtype(np.float16): "F16",
             np.dtype(np.float64): "F64"}


def _encode(arr: np.ndarray) -> tuple[str, bytes]:
    if arr.dtype == np.float32:
        return "F32", arr.astype("<f4").tobytes()
    if arr.dtype == np.float16:
        return "F16", arr.astype("<f2").tobytes()
    if arr.dtype == np.float64:
        return "F64", arr.astype("<f8").tobytes()
    raise TypeError(f"test yardımcı dtype desteklenmiyor: {arr.dtype}")


def _write_safetensors(path: Path, tensors: dict, metadata: dict | None = None):
    """{key: np.ndarray} -> safetensors dosyası (ham bayt, mmap yok)."""
    hdr = {}
    if metadata:
        hdr["__metadata__"] = {str(k): str(v) for k, v in metadata.items()}
    offset = 0
    blobs = []
    for key, arr in tensors.items():
        arr = np.asarray(arr)
        st_dtype, raw = _encode(arr)
        hdr[key] = {"dtype": st_dtype, "shape": list(arr.shape),
                    "data_offsets": [offset, offset + len(raw)]}
        blobs.append(raw)
        offset += len(raw)
    h = json.dumps(hdr).encode()
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(h)))
        f.write(h)
        for raw in blobs:
            f.write(raw)


def _read_safetensors_raw(path: Path) -> tuple[dict, bytes]:
    """Header'ı ve veri bölümünü ham bayt olarak döner (byte-identity için)."""
    with open(path, "rb") as f:
        hl = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(hl))
        data = f.read()
    return hdr, data


def _tensor_bytes(path: Path, key: str) -> bytes:
    hdr, data = _read_safetensors_raw(path)
    o0, o1 = hdr[key]["data_offsets"]
    return data[o0:o1]


def _load_tensor(path: Path, key: str) -> np.ndarray:
    hdr, data = _read_safetensors_raw(path)
    meta = hdr[key]
    o0, o1 = meta["data_offsets"]
    raw = data[o0:o1]
    if meta["dtype"] == "BF16":
        u16 = np.frombuffer(raw, dtype="<u2")
        return ((u16.astype(np.uint32) << 16).view(np.float32)
                .reshape(meta["shape"]))
    dt = {"F32": "<f4", "F16": "<f2", "F64": "<f8"}[meta["dtype"]]
    return np.frombuffer(raw, dtype=dt).reshape(meta["shape"])


def _encode_bf16(arr: np.ndarray) -> bytes:
    x = np.asarray(arr, dtype=np.float32).ravel()
    b = x.view(np.uint32)
    rounded = b + np.uint32(0x7FFF) + ((b >> np.uint32(16)) & np.uint32(1))
    return (rounded >> np.uint32(16)).astype("<u2").tobytes()


def _decode_bf16(raw: bytes, shape) -> np.ndarray:
    u16 = np.frombuffer(raw, dtype="<u2")
    return ((u16.astype(np.uint32) << 16).view(np.float32).reshape(shape))


# ---------------------------------------------------------------------------
# sahte model / tokenizer (gerçek yükleyici olmadan tespit testleri)
# ---------------------------------------------------------------------------

class _FakeTokenizer:
    """metin -> sabit token kimliği; S=2, son-token vektörünü model üretir."""

    def __init__(self, table: dict):
        self.table = table

    def __call__(self, text, **kw):
        tid = self.table[text]
        return {"input_ids": [[tid, tid]], "attention_mask": [[1, 1]]}


class _FakeModel:
    """HF gizli-durum yolu: hidden_states[l+1] = katman l residual çıktısı."""

    def __init__(self, vecs: dict, n_layers: int):
        self.config = SimpleNamespace(num_hidden_layers=n_layers)
        self.vecs = vecs  # {tok_id: {layer: (D,) vektör}}

    def __call__(self, input_ids=None, attention_mask=None,
                 output_hidden_states=False, **kw):
        ids = np.asarray(input_ids)
        tid = int(ids.reshape(-1)[0])
        s = ids.shape[-1]
        hs = [np.zeros((1, s, D_MODEL), dtype=np.float32)]
        for l in range(self.config.num_hidden_layers):
            arr = np.zeros((1, s, D_MODEL), dtype=np.float32)
            arr[0, -1] = self.vecs[tid][l]
            hs.append(arr)
        return SimpleNamespace(hidden_states=tuple(hs))


class _FakeBridgeModel:
    """TransformerBridge yolu: run_with_cache + cfg. Girdi token tensörü
    olmalı — dict geçilirse gerçek köprüde torch.embedding TypeError
    fırlatır ('indices must be Tensor, not dict')."""

    def __init__(self, vecs: dict, n_layers: int):
        self.cfg = SimpleNamespace(n_layers=n_layers)
        self.vecs = vecs  # {tok_id: {layer: (D,) vektör}}
        self.received = None

    def __call__(self, *args, **kwargs):
        raise AssertionError("köprü modeli doğrudan çağrılmamalı")

    def run_with_cache(self, inputs, names_filter=None):
        self.received = inputs
        if isinstance(inputs, dict):
            raise TypeError("embedding(): argument 'indices' (position 2) "
                            "must be Tensor, not dict")
        ids = np.asarray(inputs)
        tid = int(ids.reshape(-1)[0])
        s = ids.shape[-1]
        cache = {}
        for l in range(self.cfg.n_layers):
            arr = np.zeros((1, s, D_MODEL), dtype=np.float32)
            arr[0, -1] = self.vecs[tid][l]
            cache[f"blocks.{l}.hook_resid_post"] = arr
        return None, cache


def _unit(i: int) -> np.ndarray:
    v = np.zeros(D_MODEL, dtype=np.float32)
    v[i] = 1.0
    return v


def _write_jsonl(path: Path, rows: list[dict]):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# 1. projeksiyon matematiği
# ---------------------------------------------------------------------------

class TestProjectionMath(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        # normalize edilmiş bağımsız satırlar: R (2, d_model)
        raw = rng.standard_normal((2, D_MODEL))
        self.R = orthonormalize(raw)
        self.assertEqual(self.R.shape, (2, D_MODEL))
        self.W_writer = rng.standard_normal((D_MODEL, 5))  # (d_model, in)
        self.W_reader = rng.standard_normal((5, D_MODEL))  # (out, d_model)
        self.E = rng.standard_normal((VOCAB, D_MODEL))     # (vocab, d_model)

    def test_writer_projection_removes_R_rows(self):
        W2 = project_writer(self.W_writer, self.R)
        self.assertEqual(W2.shape, self.W_writer.shape)
        # R satırları çıktının satır-uzayından silinmiş olmalı
        residual = self.R @ W2
        self.assertLess(float(np.linalg.norm(residual)), 1e-10)
        # kapalı form: W - R.T @ (R @ W)
        expected = self.W_writer - self.R.T @ (self.R @ self.W_writer)
        np.testing.assert_allclose(W2, expected, atol=1e-12)

    def test_reader_projection_removes_R_columns(self):
        W2 = project_reader(self.W_reader, self.R)
        self.assertEqual(W2.shape, self.W_reader.shape)
        residual = W2 @ self.R.T
        self.assertLess(float(np.linalg.norm(residual)), 1e-10)
        expected = self.W_reader - (self.W_reader @ self.R.T) @ self.R
        np.testing.assert_allclose(W2, expected, atol=1e-12)

    def test_embedding_projection_removes_R_columns(self):
        E2 = project_embedding(self.E, self.R)
        self.assertEqual(E2.shape, self.E.shape)
        residual = E2 @ self.R.T
        self.assertLess(float(np.linalg.norm(residual)), 1e-10)
        # R'a dik bileşenler korunur: RR^T dışı değişmez
        perp = self.E - (self.E @ self.R.T) @ self.R
        np.testing.assert_allclose(E2, perp, atol=1e-12)

    def test_projection_is_idempotent(self):
        W2 = project_writer(self.W_writer, self.R)
        W3 = project_writer(W2, self.R)
        np.testing.assert_allclose(W3, W2, atol=1e-12)

    def test_rank1_projection_matches_formula(self):
        r = self.R[:1]  # tek yön
        W2 = project_writer(self.W_writer, r)
        expected = self.W_writer - r.T @ (r @ self.W_writer)
        np.testing.assert_allclose(W2, expected, atol=1e-12)
        self.assertLess(float(np.linalg.norm(r @ W2)), 1e-10)

    def test_bad_shapes_raise(self):
        with self.assertRaises(ValueError):
            project_writer(self.W_reader, self.R)  # yanlış eksen
        with self.assertRaises(ValueError):
            project_reader(self.W_writer, self.R)  # yanlış eksen
        with self.assertRaises(ValueError):
            project_writer(self.W_writer, np.zeros((0, D_MODEL)))


class TestOrthonormalize(unittest.TestCase):
    def test_independent_rows_orthonormal(self):
        rng = np.random.default_rng(3)
        R = orthonormalize(rng.standard_normal((3, D_MODEL)))
        self.assertEqual(R.shape, (3, D_MODEL))
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-10)

    def test_dependent_rows_dropped(self):
        r0 = _unit(0)
        rows = np.stack([r0, 2.0 * r0, _unit(3)])  # 2. satır bağımlı
        R = orthonormalize(rows)
        self.assertEqual(R.shape, (2, D_MODEL))
        np.testing.assert_allclose(R @ R.T, np.eye(2), atol=1e-10)

    def test_zero_rows_dropped(self):
        R = orthonormalize(np.zeros((2, D_MODEL)))
        self.assertEqual(R.shape[0], 0)

    def test_requires_2d(self):
        with self.assertRaises(ValueError):
            orthonormalize(np.zeros(D_MODEL))


# ---------------------------------------------------------------------------
# 2. sınıflandırma + argüman yardımcıları
# ---------------------------------------------------------------------------

class TestClassifyAndArgs(unittest.TestCase):
    def test_classify_target_categories(self):
        self.assertEqual(classify_target("model.layers.0.self_attn.o_proj.weight"),
                         "attention_out")
        self.assertEqual(classify_target("model.layers.0.mlp.down_proj.weight"),
                         "mlp_down")
        self.assertEqual(classify_target("model.embed_tokens.weight"),
                         "embedding_in")
        self.assertEqual(classify_target("lm_head.weight"), "embedding_out")

    def test_classify_target_non_targets(self):
        for key in ("model.layers.0.self_attn.q_proj.weight",
                    "model.layers.0.mlp.gate_proj.weight",
                    "model.layers.0.input_layernorm.weight",
                    "model.rotary_emb.inv_freq"):
            self.assertIsNone(classify_target(key))

    def test_default_targets(self):
        self.assertEqual(tuple(DEFAULT_TARGETS),
                         ("attention_out", "mlp_down", "embedding_in",
                          "embedding_out"))

    def test_parse_layers(self):
        self.assertEqual(parse_layers("auto"), "auto")
        self.assertEqual(parse_layers("4,12"), [4, 12])
        self.assertEqual(parse_layers(" 4 , 12 "), [4, 12])
        with self.assertRaises(ValueError):
            parse_layers("4,elma")
        with self.assertRaises(ValueError):
            parse_layers("")

    def test_parse_targets(self):
        self.assertEqual(parse_targets("mlp_down,attention_out"),
                         ["attention_out", "mlp_down"])
        self.assertEqual(parse_targets(None), list(DEFAULT_TARGETS))
        with self.assertRaises(ValueError):
            parse_targets("attention_out,bilinmeyen")

    def test_default_out_dir(self):
        p = default_out_dir("/mnt/toshiba/eval_models/Qwen_Qwen3-8B")
        self.assertEqual(p.name, "Qwen_Qwen3-8B-abliterated")
        self.assertEqual(p.parent.name, "mahoraga_adaylar")

    def test_load_prompts_keys_and_limit(self):
        with tempfile.TemporaryDirectory() as td:
            adv = Path(td) / "adv.jsonl"
            b77 = Path(td) / "b77.jsonl"
            _write_jsonl(adv, [{"id": f"a{i}", "goal": f"G{i}"} for i in range(10)])
            _write_jsonl(b77, [{"id": f"b{i}", "metin": f"M{i}"} for i in range(5)])
            self.assertEqual(load_prompts(adv, limit=3), ["G0", "G1", "G2"])
            self.assertEqual(load_prompts(b77, limit=64),
                             ["M0", "M1", "M2", "M3", "M4"])
            self.assertEqual(load_prompts(adv, key="goal", limit=1), ["G0"])

    def test_load_prompts_bad(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.jsonl"
            _write_jsonl(p, [{"veri": "x"}])
            with self.assertRaises(ValueError):
                load_prompts(p)
            with self.assertRaises(ValueError):
                load_prompts(p, key="goal")
            with self.assertRaises(ValueError):
                load_prompts(Path(td) / "yok.jsonl")


# ---------------------------------------------------------------------------
# 3. yön tespiti (difference-of-means, son-token resid_post)
# ---------------------------------------------------------------------------

class TestDetectDirections(unittest.TestCase):
    def _build(self, td: Path, layer_vecs: dict, n_texts: int = 4):
        """layer_vecs: {layer: (v_harmful, v_harmless)}; sahte model kurar."""
        harmful = [{"id": f"h{i}", "goal": f"H{i}"} for i in range(n_texts)]
        harmless = [{"id": f"n{i}", "metin": f"N{i}"} for i in range(n_texts)]
        adv = td / "adv.jsonl"
        b77 = td / "b77.jsonl"
        _write_jsonl(adv, harmful)
        _write_jsonl(b77, harmless)
        table = {}
        vecs = {}
        n_layers = len(layer_vecs)
        for i in range(n_texts):
            table[f"H{i}"] = 100 + i
            vecs[100 + i] = {l: layer_vecs[l][0] for l in range(n_layers)}
            table[f"N{i}"] = 200 + i
            vecs[200 + i] = {l: layer_vecs[l][1] for l in range(n_layers)}
        model = _FakeModel(vecs, n_layers)
        tok = _FakeTokenizer(table)
        return adv, b77, model, tok

    def test_difference_of_means_direction(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            v_h, v_n = _unit(0) + 0.1 * _unit(3), -_unit(0) + 0.1 * _unit(3)
            adv, b77, model, tok = self._build(td, {0: (v_h, v_n)})
            res = detect_directions(str(td), str(adv), str(b77),
                                    model=model, tokenizer=tok,
                                    n_directions=1)
            expected = (v_h.astype(np.float64) - v_n) / np.linalg.norm(
                v_h.astype(np.float64) - v_n)
            d0 = np.asarray(res["layers"]["0"]["direction"])
            self.assertGreater(abs(float(d0 @ expected)), 0.999)
            self.assertAlmostEqual(res["layers"]["0"]["separation"],
                                   2.0 / np.sqrt(1.01), places=5)
            self.assertFalse(res["layers"]["0"]["degenerate"])
            self.assertEqual(res["d_model"], D_MODEL)
            self.assertEqual(res["prompt_counts"],
                             {"harmful": 4, "harmless": 4})

    def test_layer_ranking_picks_top_k(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            layer_vecs = {
                # katman 0: net ayrım (yön ~e0)
                0: (_unit(0) + 0.1 * _unit(3), -_unit(0) + 0.1 * _unit(3)),
                # katman 1: gürültülü (ayrım küçük)
                1: (_unit(0) + 10.0 * _unit(4), -_unit(0) + 10.0 * _unit(4)),
                # katman 2: orta-net, FARKLI yön (~e5)
                2: (_unit(5) + 0.5 * _unit(0), -_unit(5) + 0.5 * _unit(0)),
                # katman 3: tamamen dejenere (ayrım yok)
                3: (2.0 * _unit(7), 2.0 * _unit(7)),
            }
            adv, b77, model, tok = self._build(td, layer_vecs)
            res = detect_directions(str(td), str(adv), str(b77),
                                    model=model, tokenizer=tok,
                                    n_directions=3)
            self.assertTrue(res["layers"]["3"]["degenerate"])
            self.assertAlmostEqual(res["layers"]["3"]["separation"], 0.0,
                                   places=6)
            self.assertEqual(res["selected_layers"], [0, 2])
            R = np.asarray(res["R"])
            self.assertEqual(R.shape, (2, D_MODEL))
            np.testing.assert_allclose(R @ R.T, np.eye(2), atol=1e-8)
            # ilk satır ~e0, ikinci ~e5
            self.assertGreater(abs(float(R[0] @ _unit(0))), 0.999)
            self.assertGreater(abs(float(R[1] @ _unit(5))), 0.999)

    def test_bridge_model_receives_token_tensor_not_dict(self):
        """Köprü modeller (run_with_cache) token tensörü almalı — dict
        geçilirse gerçek gövdede torch.embedding TypeError fırlatır."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            layer_vecs = {
                0: (_unit(0) + 0.1 * _unit(3), -_unit(0) + 0.1 * _unit(3)),
            }
            adv, b77, fake, tok = self._build(td, layer_vecs)
            bridge = _FakeBridgeModel(fake.vecs, 1)
            res = detect_directions(str(td), str(adv), str(b77),
                                    model=bridge, tokenizer=tok,
                                    n_directions=1)
            self.assertIsNotNone(bridge.received)
            self.assertFalse(isinstance(bridge.received, dict))
            self.assertEqual(np.asarray(bridge.received).shape[-1], 2)  # S=2
            d0 = np.asarray(res["layers"]["0"]["direction"])
            self.assertGreater(abs(float(d0 @ _unit(0))), 0.999)

    def test_explicit_layers_only(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            layer_vecs = {
                0: (_unit(0) + 0.1 * _unit(3), -_unit(0) + 0.1 * _unit(3)),
                1: (_unit(2) + 0.1 * _unit(3), -_unit(2) + 0.1 * _unit(3)),
            }
            adv, b77, model, tok = self._build(td, layer_vecs)
            res = detect_directions(str(td), str(adv), str(b77),
                                    layers="1", model=model, tokenizer=tok,
                                    n_directions=4)
            self.assertEqual(res["candidate_layers"], [1])
            self.assertEqual(res["selected_layers"], [1])
            R = np.asarray(res["R"])
            self.assertGreater(abs(float(R[0] @ _unit(2))), 0.999)

    def test_max_prompts_limits_counts(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            layer_vecs = {0: (_unit(0), _unit(1))}
            adv, b77, model, tok = self._build(td, layer_vecs, n_texts=6)
            res = detect_directions(str(td), str(adv), str(b77),
                                    model=model, tokenizer=tok,
                                    max_prompts=2, n_directions=1)
            self.assertEqual(res["prompt_counts"],
                             {"harmful": 2, "harmless": 2})

    def test_result_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            layer_vecs = {0: (_unit(0), _unit(1))}
            adv, b77, model, tok = self._build(td, layer_vecs)
            res = detect_directions(str(td), str(adv), str(b77),
                                    model=model, tokenizer=tok,
                                    n_directions=1)
            blob = json.dumps(res)
            self.assertIn("direction", blob)
            self.assertIn("separation", blob)
            self.assertIn("hash", blob)
            self.assertEqual(len(res["layers"]["0"]["hash"]), 16)

    def test_empty_prompts_raise(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            adv = td / "adv.jsonl"
            b77 = td / "b77.jsonl"
            _write_jsonl(adv, [])
            _write_jsonl(b77, [{"metin": "x"}])
            with self.assertRaises(ValueError):
                detect_directions(str(td), str(adv), str(b77),
                                  model=_FakeModel({}, 1),
                                  tokenizer=_FakeTokenizer({}))

    def test_loaded_model_not_held(self):
        """Tespit, yükleyiciyle yüklenen modeli bırakır (RAM kuralı)."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            layer_vecs = {0: (_unit(0), _unit(1))}
            adv, b77, model, tok = self._build(td, layer_vecs)
            held = []

            def fake_loader(model_dir, device="cpu", dtype=None, **kw):
                held.append(model)
                return model

            res = detect_directions(str(td), str(adv), str(b77),
                                    loader=fake_loader, tokenizer=tok,
                                    n_directions=1)
            self.assertEqual(len(held), 1)
            self.assertEqual(res["prompt_counts"]["harmful"], 4)


# ---------------------------------------------------------------------------
# 4. sentetik gövde kurulumu (2 shard + index + config)
# ---------------------------------------------------------------------------

def _build_body(root: Path) -> dict:
    """2-shard minik gövde: yazar/okuyucu/gömme + hedef-dışı tensörler."""
    rng = np.random.default_rng(11)
    shard1 = root / "model-00001-of-00002.safetensors"
    shard2 = root / "model-00002-of-00002.safetensors"
    tensors1 = {
        "model.embed_tokens.weight": rng.standard_normal((VOCAB, D_MODEL)).astype(np.float32),
        "model.layers.0.self_attn.q_proj.weight": rng.standard_normal((D_MODEL, D_MODEL)).astype(np.float32),
        "model.layers.0.self_attn.o_proj.weight": rng.standard_normal((D_MODEL, D_MODEL)).astype(np.float32),
    }
    down = rng.standard_normal((D_MODEL, 6)).astype(np.float32)
    lm = rng.standard_normal((VOCAB, D_MODEL)).astype(np.float32)
    gate = rng.standard_normal((6, D_MODEL)).astype(np.float32)
    oproj1 = rng.standard_normal((D_MODEL, 6)).astype(np.float32)
    tensors2 = {
        "model.layers.0.mlp.down_proj.weight": down,
        "lm_head.weight": lm,
        "model.layers.0.mlp.gate_proj.weight": gate,
        "model.layers.1.self_attn.o_proj.weight": oproj1,
    }
    _write_safetensors(shard1, tensors1, metadata={"format": "pt"})
    # BF16 hedef-dışı tensör (bayt-identity + codec kapsamı)
    with open(shard2, "wb") as f:
        hdr = {}
        blobs = []
        offset = 0
        for key, arr in tensors2.items():
            st, raw = _encode(arr)
            hdr[key] = {"dtype": st, "shape": list(arr.shape),
                        "data_offsets": [offset, offset + len(raw)]}
            blobs.append(raw)
            offset += len(raw)
        bf_key = "model.layers.2.mlp.down_proj.weight"
        bf_raw = _encode_bf16(rng.standard_normal((D_MODEL, 4)))
        hdr[bf_key] = {"dtype": "BF16", "shape": [D_MODEL, 4],
                       "data_offsets": [offset, offset + len(bf_raw)]}
        blobs.append(bf_raw)
        hdr["__metadata__"] = {"format": "pt"}
        h = json.dumps(hdr).encode()
        f.write(struct.pack("<Q", len(h)))
        f.write(h)
        for raw in blobs:
            f.write(raw)
    index = {
        "metadata": {"total_size": 1},
        "weight_map": {
            "model.embed_tokens.weight": shard1.name,
            "model.layers.0.self_attn.q_proj.weight": shard1.name,
            "model.layers.0.self_attn.o_proj.weight": shard1.name,
            "model.layers.0.mlp.down_proj.weight": shard2.name,
            "model.layers.1.self_attn.o_proj.weight": shard2.name,
            "model.layers.2.mlp.down_proj.weight": shard2.name,
            "lm_head.weight": shard2.name,
            "model.layers.0.mlp.gate_proj.weight": shard2.name,
        },
    }
    (root / "model.safetensors.index.json").write_text(json.dumps(index))
    (root / "config.json").write_text(json.dumps({"model_type": "qwen3"}))
    return {"shard1": shard1, "shard2": shard2, "tensors1": tensors1,
            "tensors2": tensors2, "bf_key": "model.layers.2.mlp.down_proj.weight"}


def _make_directions() -> dict:
    R = np.zeros((2, D_MODEL))
    R[0, 0] = 1.0
    R[1, 1] = 1.0
    return {"R": R.tolist(), "n_directions": 2, "d_model": D_MODEL,
            "selected_layers": [0, 1],
            "layers": {"0": {"direction": R[0].tolist(), "separation": 1.9,
                             "hash": "a" * 16},
                       "1": {"direction": R[1].tolist(), "separation": 1.2,
                             "hash": "b" * 16}},
            "prompt_counts": {"harmful": 4, "harmless": 4},
            "method": "difference_of_means"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 5. apply_ablation: roundtrip, byte-identity, manifest, resume
# ---------------------------------------------------------------------------

class TestApplyAblation(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.in_dir = self.root / "kaynak"
        self.in_dir.mkdir()
        self.body = _build_body(self.in_dir)
        self.out_dir = self.root / "aday"
        self.directions = _make_directions()

    def tearDown(self):
        self._td.cleanup()

    def test_shard_roundtrip_projection_applied(self):
        manifest = apply_ablation(self.in_dir, self.out_dir, self.directions)
        R = np.asarray(self.directions["R"])
        out1 = self.out_dir / self.body["shard1"].name
        out2 = self.out_dir / self.body["shard2"].name
        # yazar (o_proj, down_proj): R satırları silinmiş
        for path, key in ((out1, "model.layers.0.self_attn.o_proj.weight"),
                          (out2, "model.layers.0.mlp.down_proj.weight"),
                          (out2, "model.layers.1.self_attn.o_proj.weight"),
                          (out2, self.body["bf_key"])):
            W2 = _load_tensor(path, key).astype(np.float64)
            self.assertLess(float(np.linalg.norm(R @ W2)),
                            1e-4, msg=key)
        # gömme + lm_head: R sütunları silinmiş
        for key in ("model.embed_tokens.weight", "lm_head.weight"):
            E2 = _load_tensor(out1 if key.startswith("model") else out2,
                              key).astype(np.float64)
            self.assertLess(float(np.linalg.norm(E2 @ R.T)), 1e-4, msg=key)
        # ham bayt biçimi hâlâ safetensors
        for p in (out1, out2):
            hdr, _ = _read_safetensors_raw(p)
            self.assertIn("__metadata__", hdr)

    def test_non_target_tensors_byte_identical(self):
        apply_ablation(self.in_dir, self.out_dir, self.directions)
        for name, key in ((self.body["shard1"].name,
                           "model.layers.0.self_attn.q_proj.weight"),
                          (self.body["shard2"].name,
                           "model.layers.0.mlp.gate_proj.weight")):
            src = _tensor_bytes(self.in_dir / name, key)
            dst = _tensor_bytes(self.out_dir / name, key)
            self.assertEqual(src, dst, msg=key)

    def test_targets_toggle(self):
        manifest = apply_ablation(self.in_dir, self.out_dir, self.directions,
                                  targets=["mlp_down"])
        R = np.asarray(self.directions["R"])
        out1 = self.out_dir / self.body["shard1"].name
        out2 = self.out_dir / self.body["shard2"].name
        # yalnız down_proj ablate edildi
        W2 = _load_tensor(out2, "model.layers.0.mlp.down_proj.weight")
        self.assertLess(float(np.linalg.norm(R @ W2.astype(np.float64))), 1e-4)
        for name, key in ((self.body["shard1"].name,
                           "model.layers.0.self_attn.o_proj.weight"),
                          (self.body["shard2"].name, "lm_head.weight")):
            self.assertEqual(_tensor_bytes(self.in_dir / name, key),
                             _tensor_bytes(self.out_dir / name, key), msg=key)
        self.assertEqual(manifest["targets"], ["mlp_down"])
        ablated = [t for t in manifest["tensors"] if t["action"] == "ablated"]
        self.assertEqual([t["key"] for t in ablated],
                         ["model.layers.0.mlp.down_proj.weight",
                          "model.layers.2.mlp.down_proj.weight"])

    def test_manifest_fields_present(self):
        manifest = apply_ablation(self.in_dir, self.out_dir, self.directions)
        for field in ("status", "created_utc", "completed_utc", "source_dir",
                      "output_dir", "source_files", "shards", "targets",
                      "directions", "directions_hash", "prompt_counts",
                      "tensors", "counts"):
            self.assertIn(field, manifest, msg=field)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["source_dir"], str(self.in_dir))
        self.assertEqual(manifest["targets"], list(DEFAULT_TARGETS))
        self.assertEqual(manifest["prompt_counts"],
                         {"harmful": 4, "harmless": 4})
        # kaynak dosya hash'leri
        by_name = {f["name"]: f for f in manifest["source_files"]}
        for p in self.in_dir.iterdir():
            if p.is_file():
                self.assertIn(p.name, by_name)
                self.assertEqual(by_name[p.name]["sha256"], _sha256_file(p))
        # yönler katman katman serileştirilmiş
        self.assertIn("layers", manifest["directions"])
        self.assertIn("0", manifest["directions"]["layers"])
        self.assertTrue(manifest["directions_hash"])
        # tensör bazlı önce/sonra normlar
        norms = {t["key"]: t for t in manifest["tensors"]}
        o_proj = norms["model.layers.0.self_attn.o_proj.weight"]
        self.assertEqual(o_proj["action"], "ablated")
        self.assertGreater(o_proj["norm_before"], o_proj["norm_after"])
        self.assertAlmostEqual(
            o_proj["norm_after"],
            float(np.linalg.norm(_load_tensor(
                self.out_dir / self.body["shard1"].name,
                "model.layers.0.self_attn.o_proj.weight"))),
            places=4)
        q_proj = norms["model.layers.0.self_attn.q_proj.weight"]
        self.assertEqual(q_proj["action"], "copied")
        self.assertAlmostEqual(q_proj["norm_before"], q_proj["norm_after"],
                               places=6)
        self.assertEqual(manifest["counts"]["ablated"], 6)
        self.assertEqual(manifest["counts"]["copied"], 2)
        self.assertEqual(manifest["counts"]["skipped"], 0)

    def test_resume_safe_tmp_and_rename(self):
        with mock.patch("os.replace", wraps=os.replace) as rep:
            manifest = apply_ablation(self.in_dir, self.out_dir,
                                      self.directions)
        self.assertGreaterEqual(rep.call_count, 2)
        for call in rep.call_args_list:
            self.assertTrue(str(call.args[0]).endswith(".tmp"),
                            msg=str(call.args))
            self.assertFalse(str(call.args[1]).endswith(".tmp"))
        # tmp kalıntısı yok; tüm shard'lar tamamlanmış
        self.assertEqual(list(self.out_dir.glob("*.tmp")), [])
        for name in (self.body["shard1"].name, self.body["shard2"].name):
            self.assertTrue((self.out_dir / name).exists())

    def test_resume_completes_after_interruption(self):
        # 1) ilk koşu tamamlanır; shard-1 çıktısı + in_progress durumu taklit edilir
        apply_ablation(self.in_dir, self.out_dir, self.directions)
        out_b = self.root / "aday-devam"
        out_b.mkdir()
        (out_b / self.body["shard1"].name).write_bytes(
            (self.out_dir / self.body["shard1"].name).read_bytes())
        state = json.loads(
            (self.out_dir / "ablation_manifest.json").read_text())
        state["status"] = "in_progress"
        (out_b / "ablation_manifest.json").write_text(json.dumps(state))
        # bayat tmp dosyası + shard-2 eksik
        stale = out_b / (self.body["shard2"].name + ".tmp")
        stale.write_bytes(b"bayat yarim yazim")
        # 2) devam koşusu: shard-1 resumed, shard-2 işlenir
        manifest = apply_ablation(self.in_dir, out_b, self.directions)
        self.assertEqual(list(out_b.glob("*.tmp")), [])
        self.assertFalse(stale.exists())
        by_name = {s["name"]: s for s in manifest["shards"]}
        self.assertTrue(by_name[self.body["shard1"].name]["resumed"])
        self.assertFalse(by_name[self.body["shard2"].name]["resumed"])
        self.assertEqual(manifest["status"], "complete")
        # shard-2 gerçekten ablate edilmiş
        R = np.asarray(self.directions["R"])
        W2 = _load_tensor(out_b / self.body["shard2"].name,
                          "model.layers.1.self_attn.o_proj.weight")
        self.assertLess(float(np.linalg.norm(R @ W2.astype(np.float64))), 1e-4)

    def test_completed_manifest_rejects_rerun(self):
        apply_ablation(self.in_dir, self.out_dir, self.directions)
        with self.assertRaises(ValueError):
            apply_ablation(self.in_dir, self.out_dir, self.directions)

    def test_resume_mismatch_rejected(self):
        apply_ablation(self.in_dir, self.out_dir, self.directions)
        state = json.loads(
            (self.out_dir / "ablation_manifest.json").read_text())
        state["status"] = "in_progress"
        (self.out_dir / "ablation_manifest.json").write_text(json.dumps(state))
        other = _make_directions()
        other["R"] = [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                      [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]
        with self.assertRaises(ValueError):
            apply_ablation(self.in_dir, self.out_dir, other)

    def test_golden_red_out_dir_guard(self):
        with self.assertRaises(ValueError):
            apply_ablation(self.in_dir, self.in_dir, self.directions)
        with self.assertRaises(ValueError):
            apply_ablation(self.in_dir, self.in_dir / "alt",
                           self.directions)

    def test_source_untouched(self):
        before = {p.name: _sha256_file(p) for p in self.in_dir.iterdir()
                  if p.is_file()}
        apply_ablation(self.in_dir, self.out_dir, self.directions)
        after = {p.name: _sha256_file(p) for p in self.in_dir.iterdir()
                 if p.is_file()}
        self.assertEqual(before, after)

    def test_index_and_config_copied(self):
        apply_ablation(self.in_dir, self.out_dir, self.directions)
        self.assertEqual(
            (self.out_dir / "model.safetensors.index.json").read_bytes(),
            (self.in_dir / "model.safetensors.index.json").read_bytes())
        self.assertEqual((self.out_dir / "config.json").read_bytes(),
                         (self.in_dir / "config.json").read_bytes())

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            apply_ablation(self.root / "yok", self.out_dir, self.directions)
        with self.assertRaises(ValueError):
            apply_ablation(self.in_dir, self.out_dir, self.directions,
                           targets=["attention_out", "bilinmeyen"])
        with self.assertRaises(ValueError):
            apply_ablation(self.in_dir, self.out_dir,
                           {"R": np.zeros((0, D_MODEL)).tolist()})

    def test_integration_detect_then_apply(self):
        """Tespit çıktısı doğrudan apply_ablation'a beslenebilir."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            v_h, v_n = _unit(0) + 0.1 * _unit(3), -_unit(0) + 0.1 * _unit(3)
            layer_vecs = {0: (v_h, v_n), 1: (_unit(1), -_unit(1))}
            harmful = [{"id": f"h{i}", "goal": f"H{i}"} for i in range(4)]
            harmless = [{"id": f"n{i}", "metin": f"N{i}"} for i in range(4)]
            adv = td / "adv.jsonl"
            b77 = td / "b77.jsonl"
            _write_jsonl(adv, harmful)
            _write_jsonl(b77, harmless)
            table, vecs = {}, {}
            for i in range(4):
                table[f"H{i}"] = 100 + i
                vecs[100 + i] = {l: layer_vecs[l][0] for l in (0, 1)}
                table[f"N{i}"] = 200 + i
                vecs[200 + i] = {l: layer_vecs[l][1] for l in (0, 1)}
            res = detect_directions(
                str(td), str(adv), str(b77), model=_FakeModel(vecs, 2),
                tokenizer=_FakeTokenizer(table), n_directions=2)
            out = td / "aday"
            manifest = apply_ablation(self.in_dir, out, res)
            self.assertEqual(manifest["status"], "complete")
            R = np.asarray(res["R"])
            W2 = _load_tensor(out / self.body["shard1"].name,
                              "model.layers.0.self_attn.o_proj.weight")
            self.assertLess(float(np.linalg.norm(R @ W2.astype(np.float64))),
                            1e-4)


# ---------------------------------------------------------------------------
# 6. CLI
# ---------------------------------------------------------------------------

class TestCLI(unittest.TestCase):
    def test_cli_help_flags(self):
        repo = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, "scripts/ablate_weights.py", "--help"],
            cwd=repo, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        for flag in ("--model-dir", "--out-dir", "--harmful-jsonl",
                     "--harmless-jsonl", "--layers", "--directions",
                     "--targets", "--device"):
            self.assertIn(flag, proc.stdout, msg=flag)


if __name__ == "__main__":
    unittest.main()
