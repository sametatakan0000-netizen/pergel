"""Multi-D weight abliteration — Arditi (arXiv:2406.11717) + Multi-D uzantısı.

Refusal (filtre) yönleri artık-ışak (residual stream) aktivasyonlarından
çıkarılır ve gerçek ağırlık tensörlerine orthogonal projeksiyon uygulanarak
YENİ bir gövde yazılır. Kaynak gövdeye ve sinaps dosyalarına asla dokunulmaz
(GOLDEN-RED kuralı).

İki aşama:

1) `detect_directions` — difference-of-means (son-token `resid_post`):
   zararlı prompt'lar (guvenlik_advbench) ve zararsız prompt'lar
   (dil_karar_banking77) için son-token artık-ışak vektörlerinin ortalamaları
   farkı, katman başına normalize edilmiş yön vektörü verir. Katmanlar
   ayrım (separation: zararlı/zararsız kosinüs benzerliği farkı) ile
   sıralanır; ilk `n_directions` AYRI yöne katkı veren katman seçilir
   (bağımlı yönler elenir — Multi-D kardinalite korunur). Yönler
   Gram-Schmidt ile orthonormalize edilip R (k x d_model) matrisinde
   istiflenir. Model red_collection.load_bridge_model ile yüklenir,
   aktivasyonlar red_collection.capture_activations ile yakalanır ve tespit
   biter bitmez bırakılır (model gövdesi ~16 GB, RAM 30 GB — gövde
   uygulama sırasında ASLA bellekte tutulmaz).

2) `apply_ablation` — shard'lar ham-bayt akışla işlenir
   (safe_open/mmap YOK — fazc_merge kuralı, FUSE/mmap ENOMEM dersi):

   - residual YAZARLAR (attention o_proj, mlp down_proj; W: d_model x in):
     W' = W - R.T @ (R @ W)          [d_model ekseni 0]
   - residual OKUYUCULAR (q/k/v/gate/up, lm_head; W: out x d_model):
     W' = W - (W @ R.T) @ R          [d_model ekseni 1]
   - gömme (embed_tokens; E: vocab x d_model, satırları artık akışa yazar):
     E' = E - (E @ R.T) @ R          [d_model ekseni 1]

   Varsayılan hedefler (mahoraga_recipe_map.json): attention_out, mlp_down,
   embedding_in, embedding_out — dördü de uygulanır, her kategori tek tek
   açılıp kapatılabilir. Hedef-dışı tensörler ham bayt olarak kopyalanır
   (bayt-bayt aynı). Her shard önce `.tmp` dosyasına yazılır, tamamlanınca
   `os.replace` ile yerine konur (resume-safe): kesintiden sonra tamamlanmış
   shard'lar `resumed` olarak atlanır, bayat `.tmp` temizlenir.

   Çıktı: yeni dizin + `ablation_manifest.json` (kaynak yol+hash'ler,
   katman katman serileştirilmiş yönler, uygulanan hedefler, tensör bazlı
   önce/sonra normlar, prompt sayıları, zaman damgaları).

Tespit verisi varsayılanı: ilk 64 zararlı + ilk 64 zararsız prompt
(difference-of-means için yeterli örnekleme; tamamı maliyetlidir).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .red_collection import (
    _model_n_layers,
    _normalize_layers,
    capture_activations,
    load_bridge_model,
)
from .stream_surgery import safetensors_complete
from .synapse_inventory import classify_key

# Reçete hedefleri (mahoraga_recipe_map.json): dördü de uygulanır.
DEFAULT_TARGETS = ("attention_out", "mlp_down", "embedding_in", "embedding_out")

# d_model ekseni: yazarlarda 0 (W: d_model x in), okuyucu/gömmede 1.
D_MODEL_AXIS = {"attention_out": 0, "mlp_down": 0,
                "embedding_in": 1, "embedding_out": 1}

MANIFEST_NAME = "ablation_manifest.json"
DEFAULT_HARMFUL_JSONL = "/home/pc/mahoraga_davranis_veri/guvenlik_advbench.jsonl"
DEFAULT_HARMLESS_JSONL = "/home/pc/mahoraga_davranis_veri/dil_karar_banking77.jsonl"
DEFAULT_PROMPT_LIMIT = 64
DEFAULT_ABLATION_BASE = "/home/pc/mahoraga_adaylar"

# Prompt metni için denenecek anahtarlar (guvenlik_advbench: "goal",
# dil_karar_banking77: "metin").
PROMPT_KEYS = ("goal", "prompt", "metin", "text", "instruction", "query")

# safetensors dtype -> numpy okuma biçimi (BF16 elle çözülür).
_FLOAT_ST = {"F64": "<f8", "F32": "<f4", "F16": "<f2", "BF16": "BF16"}
_COPY_CHUNK = 1 << 23  # ham kopya/okuma adımı (8 MiB)


# ---------------------------------------------------------------------------
# argüman yardımcıları
# ---------------------------------------------------------------------------

def parse_layers(arg) -> "str | list[int]":
    """Katman belirtisini ayrıştır: "auto" veya "4,12" / [4, 12]."""
    if isinstance(arg, str):
        s = arg.strip()
        if not s:
            raise ValueError("katman belirtisi boş olamaz")
        if s.lower() == "auto":
            return "auto"
        parts = [p.strip() for p in s.split(",")]
        out = []
        for p in parts:
            if not p:
                raise ValueError(f"geçersiz katman belirtisi: {arg!r}")
            try:
                out.append(int(p))
            except ValueError as exc:
                raise ValueError(f"geçersiz katman belirtisi: {arg!r}") from exc
        return _normalize_layers(out)
    return _normalize_layers(arg)


def parse_targets(arg) -> list[str]:
    """Hedef kategorileri doğrular; DEFAULT_TARGETS sırasıyla döner."""
    if arg is None:
        return list(DEFAULT_TARGETS)
    if isinstance(arg, str):
        items = [t.strip() for t in arg.split(",") if t.strip()]
    else:
        items = [str(t).strip() for t in arg]
    if not items:
        raise ValueError("hedef listesi boş olamaz")
    unknown = [t for t in items if t not in DEFAULT_TARGETS]
    if unknown:
        raise ValueError(
            f"bilinmeyen hedef(ler): {unknown} (geçerli: {list(DEFAULT_TARGETS)})")
    return [t for t in DEFAULT_TARGETS if t in items]


def default_out_dir(model_dir, base: str = DEFAULT_ABLATION_BASE) -> Path:
    """Varsayılan çıktı yolu: <base>/<model-adı>-abliterated/."""
    name = Path(str(model_dir)).name or "model"
    name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
    return Path(base) / f"{name}-abliterated"


def classify_target(key: str):
    """Tensör anahtarını reçete hedefine çevirir; hedef-dışıysa None.

    Anatomik sınıflandırma synapse_inventory.classify_key'den devralınır;
    yalnız dört reçete hedefi döner.
    """
    cat = classify_key(key)
    return cat if cat in DEFAULT_TARGETS else None


# ---------------------------------------------------------------------------
# doğrusal cebir (numpy; float64 ara bellek)
# ---------------------------------------------------------------------------

def _as_R(R) -> np.ndarray:
    arr = np.asarray(R, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"R 2B olmalı: {arr.shape}")
    if arr.shape[0] < 1:
        raise ValueError("R en az bir yön satırı içermeli")
    if arr.shape[1] < 1:
        raise ValueError("R boş sütunlu olamaz")
    return arr


def orthonormalize(rows, eps: float = 1e-6) -> np.ndarray:
    """Gram-Schmidt: bağımsız satırları normalize eder, bağımlıları atar.

    Dönen: (k', d_model) float64, satırlar birbirine dik birim vektörler.
    Hiç bağımsız satır yoksa (0, d_model) döner.
    """
    arr = np.asarray(rows, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"girdi 2B olmalı: {arr.shape}")
    out: list[np.ndarray] = []
    for row in arr:
        v = row.astype(np.float64).copy()
        for u in out:
            v -= (u @ v) * u
        n = float(np.linalg.norm(v))
        if n > eps:
            out.append(v / n)
    if not out:
        return np.zeros((0, arr.shape[1]), dtype=np.float64)
    return np.stack(out)


def project_writer(W, R) -> np.ndarray:
    """Residual YAZAR projeksiyonu: W (d_model, in), R (k, d_model).

    W' = W - R.T @ (R @ W) — R satırlarının uzandığı bileşenler çıktının
    satır-uzayından silinir: ||R @ W'||_F = 0.
    """
    W64 = np.asarray(W, dtype=np.float64)
    R64 = _as_R(R)
    if W64.ndim != 2:
        raise ValueError(f"W 2B olmalı: {W64.shape}")
    if W64.shape[0] != R64.shape[1]:
        raise ValueError(
            f"yazar şekli uyumsuz: W {W64.shape}, R {R64.shape} "
            f"(W'nin satır ekseni d_model olmalı)")
    return W64 - R64.T @ (R64 @ W64)


def project_reader(W, R) -> np.ndarray:
    """Residual OKUYUCU projeksiyonu: W (out, d_model), R (k, d_model).

    W' = W - (W @ R.T) @ R — R satırları okunan artık-ışaktan silinir:
    ||W' @ R.T||_F = 0. q/k/v/gate/up projeksiyonları ve lm_head için.
    """
    W64 = np.asarray(W, dtype=np.float64)
    R64 = _as_R(R)
    if W64.ndim != 2:
        raise ValueError(f"W 2B olmalı: {W64.shape}")
    if W64.shape[1] != R64.shape[1]:
        raise ValueError(
            f"okuyucu şekli uyumsuz: W {W64.shape}, R {R64.shape} "
            f"(W'nin sütun ekseni d_model olmalı)")
    return W64 - (W64 @ R64.T) @ R64


def project_embedding(E, R) -> np.ndarray:
    """Gömme (embed_tokens) projeksiyonu: E (vocab, d_model).

    Her satır o token'ın artık akışa YAZdığı vektördür; formül okuyucuyla
    aynıdır: E' = E - (E @ R.T) @ R.
    """
    E64 = np.asarray(E, dtype=np.float64)
    R64 = _as_R(R)
    if E64.ndim != 2:
        raise ValueError(f"E 2B olmalı: {E64.shape}")
    if E64.shape[1] != R64.shape[1]:
        raise ValueError(
            f"gömme şekli uyumsuz: E {E64.shape}, R {R64.shape}")
    return E64 - (E64 @ R64.T) @ R64


# ---------------------------------------------------------------------------
# prompt verisi
# ---------------------------------------------------------------------------

def load_prompts(path, key: str | None = None, limit: int | None = None) -> list[str]:
    """JSONL'den prompt metinlerini okur (sırayla, ilk `limit` adet).

    key verilmezse PROMPT_KEYS'te ilk bulunan anahtar kullanılır
    (guvenlik_advbench: "goal"; dil_karar_banking77: "metin").
    Dosya yoksa/boşsa, anahtar yoksa veya metin dizgi değilse ValueError.
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"prompt dosyası yok: {p}")
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"prompt dosyası boş: {p}")
    if key is None:
        for k in PROMPT_KEYS:
            if k in rows[0]:
                key = k
                break
        else:
            raise ValueError(
                f"prompt anahtarı bulunamadı {PROMPT_KEYS}: {p}")
    texts: list[str] = []
    for i, row in enumerate(rows):
        if key not in row:
            raise ValueError(f"satır {i}: {key!r} anahtarı yok ({p})")
        t = row[key]
        if not isinstance(t, str):
            raise ValueError(f"satır {i}: {key!r} dizgi değil ({p})")
        texts.append(t)
        if limit is not None and len(texts) >= limit:
            break
    return texts


# ---------------------------------------------------------------------------
# yön tespiti (difference-of-means, son-token resid_post)
# ---------------------------------------------------------------------------

def _tokenize(tokenizer, text: str) -> dict:
    try:
        inputs = tokenizer(text, return_tensors="pt")
    except TypeError:
        inputs = tokenizer(text)
    if hasattr(inputs, "data"):  # HF BatchEncoding
        inputs = dict(inputs)
    if not isinstance(inputs, dict) or "input_ids" not in inputs:
        raise TypeError("tokenizer 'input_ids' içeren dict döndürmeli")
    return inputs


def _last_token_mask(inputs: dict) -> np.ndarray:
    """(B, S) bool maske: yalnız son geçerli token True."""
    attn = inputs.get("attention_mask")
    if attn is None:
        ids = np.asarray(
            inputs["input_ids"].detach().cpu()
            if hasattr(inputs["input_ids"], "detach") else inputs["input_ids"])
        attn = np.ones(ids.shape[-2:], dtype=np.int64)
    am = np.asarray(
        attn.detach().cpu() if hasattr(attn, "detach") else attn)
    if am.ndim == 1:
        am = am[None, :]
    b, s = am.shape
    mask = np.zeros((b, s), dtype=bool)
    valid = np.nonzero(am[0].astype(bool))[0]
    if valid.size == 0:
        raise ValueError("prompt token içermiyor (attention_mask boş)")
    mask[0, valid[-1]] = True
    return mask


def _inference_ctx():
    """Torch inference_mode: tespit geçişi gradyan grafiği tutmaz —
    8B gövdede OOM'un ana kaynağı buydu (grafik + aktivasyon tutulması).
    Torch yoksa boşlam."""
    try:
        import torch
        return torch.inference_mode()
    except ImportError:
        import contextlib
        return contextlib.nullcontext()


def _model_inputs(model, inputs: dict):
    """capture_activations için girdi biçimi: köprü modeller (run_with_cache)
    token tensörü bekler — dict geçilirse torch.embedding TypeError fırlatır
    ('indices must be Tensor, not dict'); HF gizli-durum yolu ise dict bekler.
    Torch yoksa ham liste döner (köprü sahteleri liste kabul eder)."""
    if not hasattr(model, "run_with_cache"):
        return inputs
    ids = inputs["input_ids"]
    if not hasattr(ids, "detach"):
        try:
            import torch
            ids = torch.as_tensor(ids, dtype=torch.long)
        except ImportError:
            return ids
    if getattr(ids, "ndim", 0) == 1:
        ids = ids[None, :]
    return ids


def _row_cos_mean(M: np.ndarray, r: np.ndarray) -> float:
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return float(np.mean((M / norms) @ r))


def detect_directions(model_dir, harmful_jsonl, harmless_jsonl,
                      layers="auto", n_directions: int = 4,
                      device: str = "cpu", max_prompts: int = DEFAULT_PROMPT_LIMIT,
                      loader=None, tokenizer=None, model=None) -> dict:
    """Difference-of-means refusal yönlerini tespit eder.

    Her prompt için son-token `resid_post` vektörleri (red_collection
    .capture_activations — TransformerBridge köprüsü veya HF gizli-durum
    yolu) toplanır; katman l için yön = normalize(mean(zararlı) -
    mean(zararsız)); ayrım = zararlı-zararsız ortalama kosinüs farkı.
    Katmanlar ayrıma göre azalan sıralanır; ilk `n_directions` AYRI yöne
    katkı veren katman seçilir (bağımlı yönler elenir). Yönler
    orthonormalize edilerek R (k x d_model) istiflenir.

    layers: "auto" (tüm katmanlar) veya "4,12" / [4, 12].
    max_prompts: her dosyadan okunacak prompt sayısı (varsayılan 64:
    difference-of-means için ilk 64'ün örnekleme yeterliliği).

    Model yükleyici `loader(model_dir, device=...)` ile yüklenir
    (varsayılan red_collection.load_bridge_model) ve tespit biter bitmez
    bırakılır; `model`/`tokenizer` enjekte edilirse hiç yüklenmez (testler).

    Dönen dict tümüyle JSON-serileştirilebilir: katman başına normalize
    yön vektörleri + ayrım istatistikleri + hash, seçilen katmanlar,
    orthonormalize R, prompt sayıları.
    """
    if not isinstance(n_directions, int) or n_directions < 1:
        raise ValueError("n_directions >= 1 olmalı")
    if not isinstance(max_prompts, int) or max_prompts < 1:
        raise ValueError("max_prompts >= 1 olmalı")

    prompts_h = load_prompts(harmful_jsonl, limit=max_prompts)
    prompts_n = load_prompts(harmless_jsonl, limit=max_prompts)
    if not prompts_h or not prompts_n:
        raise ValueError("zararlı ve zararsız prompt listeleri dolu olmalı")

    loaded_here = False
    if model is None:
        loader = loader or load_bridge_model
        model = loader(model_dir, device=device)
        loaded_here = True
    try:
        if tokenizer is None:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(
                model_dir, local_files_only=True)

        if hasattr(model, "eval"):
            model.eval()
        n_layers = _model_n_layers(model)
        if isinstance(layers, str) and layers.strip().lower() == "auto":
            if not n_layers:
                raise ValueError(
                    "auto katman seçimi model katman sayısını gerektirir")
            candidates = list(range(n_layers))
        else:
            candidates = _normalize_layers(parse_layers(layers)
                                           if isinstance(layers, str) else layers)

        acts_h: dict = {l: [] for l in candidates}
        acts_n: dict = {l: [] for l in candidates}
        for text in prompts_h:
            inputs = _tokenize(tokenizer, text)
            mask = _last_token_mask(inputs)
            with _inference_ctx():
                got = capture_activations(model, _model_inputs(model, inputs),
                                          candidates,
                                          site="resid_post", token_mask=mask)
            for l in candidates:
                acts_h[l].append(np.asarray(got[l], dtype=np.float32)[0])
        for text in prompts_n:
            inputs = _tokenize(tokenizer, text)
            mask = _last_token_mask(inputs)
            with _inference_ctx():
                got = capture_activations(model, _model_inputs(model, inputs),
                                          candidates,
                                          site="resid_post", token_mask=mask)
            for l in candidates:
                acts_n[l].append(np.asarray(got[l], dtype=np.float32)[0])
    finally:
        if loaded_here:
            del model

    layer_stats: dict = {}
    d_model = int(np.asarray(acts_h[candidates[0]][0]).shape[0])
    for l in candidates:
        H = np.stack(acts_h[l]).astype(np.float64)
        N = np.stack(acts_n[l]).astype(np.float64)
        diff = H.mean(axis=0) - N.mean(axis=0)
        norm = float(np.linalg.norm(diff))
        if norm < 1e-12:
            layer_stats[str(l)] = {
                "direction": [0.0] * d_model, "norm": norm,
                "separation": 0.0, "degenerate": True, "hash": "0" * 16,
                "n_harmful": int(H.shape[0]), "n_harmless": int(N.shape[0]),
            }
            continue
        r = diff / norm
        sep = _row_cos_mean(H, r) - _row_cos_mean(N, r)
        layer_stats[str(l)] = {
            "direction": [float(x) for x in r], "norm": norm,
            "separation": float(sep), "degenerate": False,
            "hash": hashlib.sha256(
                np.asarray(r, dtype="<f4").tobytes()).hexdigest()[:16],
            "n_harmful": int(H.shape[0]), "n_harmless": int(N.shape[0]),
        }

    # katmanları ayrıma göre sırala; ilk n_directions AYRI yönü seç
    ranked = sorted(
        (l for l in candidates if not layer_stats[str(l)]["degenerate"]),
        key=lambda l: layer_stats[str(l)]["separation"], reverse=True)
    selected: list[int] = []
    chosen_rows: list[np.ndarray] = []
    for l in ranked:
        r = np.asarray(layer_stats[str(l)]["direction"], dtype=np.float64)
        trial = orthonormalize(chosen_rows + [r])
        if trial.shape[0] == len(chosen_rows) + 1:
            selected.append(l)
            chosen_rows.append(r)
            if len(selected) >= n_directions:
                break
    if not selected:
        raise ValueError(
            "geçerli yön bulunamadı (tüm katmanlar dejenere)")
    R = orthonormalize(chosen_rows)
    for l in candidates:
        layer_stats[str(l)]["selected"] = l in selected

    return {
        "method": "difference_of_means",
        "site": "resid_post",
        "model_dir": str(model_dir),
        "d_model": d_model,
        "n_layers": int(n_layers) if n_layers else None,
        "candidate_layers": list(candidates),
        "layers": layer_stats,
        "selected_layers": list(selected),
        "R": [[float(x) for x in row] for row in R],
        "n_directions": int(R.shape[0]),
        "orthonormalized": True,
        "prompt_counts": {"harmful": len(prompts_h), "harmless": len(prompts_n)},
        "prompt_files": {"harmful": str(harmful_jsonl),
                         "harmless": str(harmless_jsonl)},
        "max_prompts": int(max_prompts),
    }


# ---------------------------------------------------------------------------
# ağırlık uygulama (ham-bayt shard akışı)
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_COPY_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _extract_R(directions) -> tuple[np.ndarray, dict]:
    """Yön girdisinden R matrisini ve (varsa) tespit dict'ini ayırır."""
    info: dict = {}
    if isinstance(directions, dict):
        info = directions
        raw = directions.get("R")
        if raw is None:
            raise ValueError("directions dict'inde 'R' yok")
    else:
        raw = directions
    R = _as_R(raw)
    return R, info


def _decode_chunk(raw: bytes, st_dtype: str) -> np.ndarray:
    if st_dtype == "BF16":
        u16 = np.frombuffer(raw, dtype="<u2")
        return (u16.astype(np.uint32) << 16).view(np.float32)
    return np.frombuffer(raw, dtype=_FLOAT_ST[st_dtype])


def _encode_chunk(arr: np.ndarray, st_dtype: str) -> bytes:
    if st_dtype == "BF16":
        x = np.asarray(arr, dtype=np.float32).ravel()
        b = x.view(np.uint32)
        rounded = b + np.uint32(0x7FFF) + ((b >> np.uint32(16)) & np.uint32(1))
        return (rounded >> np.uint32(16)).astype("<u2").tobytes()
    return np.asarray(arr).astype(_FLOAT_ST[st_dtype]).tobytes()


def _itemsize(st_dtype: str) -> int:
    return {"F64": 8, "F32": 4, "F16": 2, "BF16": 2}[st_dtype]


def _process_shard(src: Path, tmp: Path, R: np.ndarray, targets: list[str],
                   chunk_elems: int) -> tuple[list[dict], str, str]:
    """Bir shard'ı ham-bayt akışla işler, tmp dosyasına yazar.

    Header ham bayt olarak korunur; hedef-dışı tensörler bayt-bayt aynı
    kopyalanır (kayıt için normları da hesaplanır). Hedef tensörler
    chunk'lar halinde projekte edilir (BF16/F16/F32/F64; float64 ara
    hesap). Dönen: (tensör kayıtları, kaynak sha256, çıktı sha256).
    """
    R64 = np.asarray(R, dtype=np.float64)
    d_model = R64.shape[1]
    k = R64.shape[0]
    h_src = hashlib.sha256()
    h_out = hashlib.sha256()
    records: list[dict] = []

    with open(src, "rb") as f, open(tmp, "wb") as out:
        def _copy(n: int) -> None:
            remaining = n
            while remaining > 0:
                chunk = f.read(min(remaining, _COPY_CHUNK))
                if not chunk:
                    raise ValueError(f"beklenmeyen dosya sonu: {src}")
                h_src.update(chunk)
                h_out.update(chunk)
                out.write(chunk)
                remaining -= len(chunk)

        hl_raw = f.read(8)
        if len(hl_raw) != 8:
            raise ValueError(f"geçersiz safetensors başlığı: {src}")
        h_src.update(hl_raw)
        h_out.update(hl_raw)
        out.write(hl_raw)
        hl = struct.unpack("<Q", hl_raw)[0]
        header_bytes = f.read(hl)
        if len(header_bytes) != hl:
            raise ValueError(f"eksik safetensors header: {src}")
        h_src.update(header_bytes)
        h_out.update(header_bytes)
        out.write(header_bytes)
        hdr = json.loads(header_bytes)
        entries = sorted(
            ((key, meta) for key, meta in hdr.items()
             if isinstance(meta, dict) and "data_offsets" in meta),
            key=lambda kv: kv[1]["data_offsets"][0])

        cursor = 0
        for key, meta in entries:
            o0, o1 = meta["data_offsets"]
            if o0 < cursor:
                raise ValueError(f"çakışan data_offsets: {key}")
            if o0 > cursor:
                _copy(o0 - cursor)  # padding (normalde yok)
            nbytes = o1 - o0
            st_dtype = meta["dtype"]
            shape = list(meta["shape"])
            category = classify_target(key)
            record = {"key": key, "shard": src.name, "category": category,
                      "dtype": st_dtype, "shape": shape}

            if category is not None and category in targets:
                axis = D_MODEL_AXIS[category]
                if (len(shape) != 2 or shape[axis] != d_model
                        or st_dtype not in _FLOAT_ST):
                    record.update(
                        action="skipped",
                        reason=(f"hedef kategori {category} ama biçim "
                                f"uyumsuz (shape={shape}, dtype={st_dtype})"),
                        norm_before=None, norm_after=None)
                    _copy(nbytes)
                else:
                    norm_b, norm_a = _ablate_tensor(
                        f, out, nbytes, shape, st_dtype, R64, axis,
                        chunk_elems, h_src, h_out)
                    record.update(action="ablated", reason=None,
                                  norm_before=norm_b, norm_after=norm_a)
            else:
                norm = _copy_with_norm(f, out, nbytes, st_dtype,
                                       chunk_elems, h_src, h_out)
                record.update(action="copied", reason=None,
                              norm_before=norm, norm_after=norm)
            records.append(record)
            cursor = o1

        # kuyruk artığı (normalde yok) — ham kopyala
        rest = f.read()
        if rest:
            h_src.update(rest)
            h_out.update(rest)
            out.write(rest)

    return records, h_src.hexdigest(), h_out.hexdigest()


def _copy_with_norm(f, out, nbytes: int, st_dtype: str, chunk_elems: int,
                    h_src, h_out):
    """Ham bayt kopyalar (bayt-bayt aynı); float tensörse norm döner."""
    norm2 = 0.0
    is_float = st_dtype in _FLOAT_ST
    width = _itemsize(st_dtype) if is_float else _COPY_CHUNK
    step = max(1, chunk_elems) * width if is_float else _COPY_CHUNK
    remaining = nbytes
    while remaining > 0:
        n = min(remaining, step)
        raw = f.read(n)
        if len(raw) != n:
            raise ValueError("beklenmeyen dosya sonu")
        h_src.update(raw)
        h_out.update(raw)
        out.write(raw)
        if is_float:
            arr = _decode_chunk(raw, st_dtype).astype(np.float64)
            norm2 += float(np.sum(arr * arr))
        remaining -= n
    return float(np.sqrt(norm2)) if is_float else None


def _ablate_tensor(f, out, nbytes: int, shape: list, st_dtype: str,
                   R64: np.ndarray, axis: int, chunk_elems: int,
                   h_src, h_out) -> tuple[float, float]:
    """Tensörü chunk'layarak projekte eder; önce/sonra norm döner.

    axis 1 (okuyucu/gömme): satırlar bağımsız — tek geçiş, satır chunk'ları.
    axis 0 (yazar): satırlar iç içe — iki geçiş (RW biriktir + yeniden yaz).
    """
    d_model = R64.shape[1]
    k = R64.shape[0]
    width = _itemsize(st_dtype)
    norm_b2 = 0.0
    norm_a2 = 0.0

    if axis == 1:
        n_rows, n_cols = shape[0], shape[1]
        row_bytes = n_cols * width
        rows_per_chunk = max(1, chunk_elems // max(1, n_cols))
        remaining = nbytes
        for r0 in range(0, n_rows, rows_per_chunk):
            r1 = min(r0 + rows_per_chunk, n_rows)
            n = (r1 - r0) * row_bytes
            raw = f.read(n)
            if len(raw) != n:
                raise ValueError("beklenmeyen dosya sonu")
            h_src.update(raw)
            arr = _decode_chunk(raw, st_dtype).reshape(r1 - r0, n_cols)
            arr64 = arr.astype(np.float64)
            out64 = arr64 - (arr64 @ R64.T) @ R64
            enc = _encode_chunk(out64, st_dtype)
            h_out.update(enc)
            out.write(enc)
            norm_b2 += float(np.sum(arr64 * arr64))
            norm_a2 += float(np.sum(out64 * out64))
            remaining -= n
        if remaining != 0:
            raise ValueError("tensör boyutu header ile uyumsuz")
        return float(np.sqrt(norm_b2)), float(np.sqrt(norm_a2))

    # axis == 0: yazar (d_model x in)
    n_rows, n_cols = shape[0], shape[1]
    row_bytes = n_cols * width
    rows_per_chunk = max(1, chunk_elems // max(1, n_cols))
    base = f.tell()
    RW = np.zeros((k, n_cols), dtype=np.float64)
    # geçiş 1: RW = R @ W birikimi
    for r0 in range(0, n_rows, rows_per_chunk):
        r1 = min(r0 + rows_per_chunk, n_rows)
        raw = f.read((r1 - r0) * row_bytes)
        arr64 = _decode_chunk(raw, st_dtype).reshape(r1 - r0, n_cols).astype(np.float64)
        RW += R64[:, r0:r1] @ arr64
    # geçiş 2: W' = W - R.T @ RW (hash'ler burada güncellenir)
    f.seek(base)
    for r0 in range(0, n_rows, rows_per_chunk):
        r1 = min(r0 + rows_per_chunk, n_rows)
        n = (r1 - r0) * row_bytes
        raw = f.read(n)
        if len(raw) != n:
            raise ValueError("beklenmeyen dosya sonu")
        h_src.update(raw)
        arr64 = _decode_chunk(raw, st_dtype).reshape(r1 - r0, n_cols).astype(np.float64)
        out64 = arr64 - R64[:, r0:r1].T @ RW
        enc = _encode_chunk(out64, st_dtype)
        h_out.update(enc)
        out.write(enc)
        norm_b2 += float(np.sum(arr64 * arr64))
        norm_a2 += float(np.sum(out64 * out64))
    return float(np.sqrt(norm_b2)), float(np.sqrt(norm_a2))


def apply_ablation(in_dir, out_dir, directions, targets=None,
                   chunk_elems: int = 16_000_000) -> dict:
    """Multi-D abliteration uygular: YENİ gövde + ablation_manifest.json.

    in_dir: kaynak safetensors gövdesi (shard'lar + index.json + config).
    directions: detect_directions çıktısı (veya {"R": [...]} / ham R).
    targets: uygulanacak kategoriler (varsayılan DEFAULT_TARGETS — dördü);
    her kategori tek tek açılıp kapatılabilir.

    Kurallar:
    - GOLDEN-RED: kaynak gövde/sinaps asla değiştirilmez; out_dir kaynak
      gövdenin İÇİNDE olamaz ve farklı olmalıdır.
    - resume-safe: her shard .tmp'e yazılır, os.replace ile yerine konur;
      kesintide tamamlanmış shard'lar resumed olarak atlanır, bayat .tmp
      temizlenir. Yönler/hedefler değişmişse resume REDDEDİLİR.
    - hedef-dışı tensörler bayt-bayt aynı kalır.

    Dönen manifest: kaynak yol+sha256'lar, katman katman serileştirilmiş
    yönler, uygulanan hedefler, tensör bazlı önce/sonra normlar, prompt
    sayıları, zaman damgaları, shard hash'leri, sayaçlar.
    """
    in_path = Path(in_dir)
    out_path = Path(out_dir)
    if not in_path.is_dir():
        raise ValueError(f"kaynak gövde yok: {in_path}")
    targets = parse_targets(targets)
    R64, info = _extract_R(directions)
    d_model = int(R64.shape[1])
    shards = sorted(p for p in in_path.glob("*.safetensors") if p.is_file())
    if not shards:
        raise ValueError(f"safetensors shard yok: {in_path}")
    for sp in shards:
        if not safetensors_complete(sp):
            raise ValueError(f"eksik/bozuk shard: {sp}")

    in_res = in_path.resolve()
    out_res = out_path.resolve()
    if out_res == in_res or in_res in out_res.parents:
        raise ValueError(
            "GOLDEN-RED: çıktı kaynak gövdenin içinde olamaz")

    directions_hash = hashlib.sha256(
        json.dumps(info or {"R": R64.tolist()}, sort_keys=True).encode()
    ).hexdigest()

    manifest = {
        "format": "mahoraga.ablation_manifest/1",
        "status": "in_progress",
        "created_utc": _utc_now(),
        "source_dir": str(in_path),
        "output_dir": str(out_path),
        "targets": targets,
        "directions": info if info else {"R": R64.tolist()},
        "directions_hash": directions_hash,
        "prompt_counts": info.get("prompt_counts"),
        "d_model": d_model,
        "chunk_elems": int(chunk_elems),
        "source_files": [], "shards": [], "tensors": [],
        "copied_files": [], "counts": {},
    }

    resume = False
    manifest_path = out_path / MANIFEST_NAME
    if manifest_path.exists():
        prev = json.loads(manifest_path.read_text())
        if prev.get("status") == "complete":
            raise ValueError(
                "çıktıda tamamlanmış abliteration var; yeni out_dir kullanın")
        if (prev.get("directions_hash") != directions_hash
                or list(prev.get("targets") or []) != targets):
            raise ValueError(
                "resume uyumsuz: yönler veya hedefler değişmiş")
        resume = True

    out_path.mkdir(parents=True, exist_ok=True)

    # kaynak envanteri (hash'ler manifest için)
    manifest["source_files"] = [
        {"name": p.name, "size": p.stat().st_size, "sha256": _sha256_file(p)}
        for p in sorted(in_path.iterdir()) if p.is_file()
    ]

    # safetensors olmayan dosyaları bayt-bayt kopyala (index, config, ...)
    for p in sorted(in_path.iterdir()):
        if (not p.is_file() or p.name.endswith(".safetensors")
                or p.name == MANIFEST_NAME):
            continue
        dst = out_path / p.name
        if not (dst.exists() and dst.stat().st_size == p.stat().st_size):
            tmp = dst.with_name(dst.name + ".tmp")
            shutil.copyfile(p, tmp)
            os.replace(tmp, dst)
        manifest["copied_files"].append(p.name)

    counts = {"ablated": 0, "copied": 0, "skipped": 0}
    for sp in shards:
        dst = out_path / sp.name
        if resume and dst.exists() and safetensors_complete(dst):
            manifest["shards"].append({
                "name": sp.name, "resumed": True,
                "sha256_source": _sha256_file(sp),
                "sha256_out": _sha256_file(dst)})
            continue
        if not safetensors_complete(sp):
            raise ValueError(f"eksik/bozuk shard: {sp}")
        tmp = dst.with_name(dst.name + ".tmp")
        if tmp.exists():
            tmp.unlink()  # bayat yarım yazım
        records, sha_src, sha_out = _process_shard(
            sp, tmp, R64, targets, chunk_elems)
        os.replace(tmp, dst)
        for rec in records:
            counts[rec["action"]] += 1
        manifest["tensors"].extend(records)
        manifest["shards"].append({
            "name": sp.name, "resumed": False,
            "sha256_source": sha_src, "sha256_out": sha_out})

    manifest["counts"] = counts
    manifest["status"] = "complete"
    manifest["completed_utc"] = _utc_now()
    _write_json_atomic(manifest_path, manifest)
    return manifest
