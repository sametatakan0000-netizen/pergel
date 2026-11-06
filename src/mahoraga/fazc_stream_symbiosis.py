#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mahoraga Faz-C — Akış Bağlama (Stream Symbiosis) pilotu.

Tasarım: docs/fazc-akisa-baglama-tasarim.md. Cross-arch doğrudan ağırlık
birleştirme kapsamı sıfır olduğundan (fazc-merge-pilot-raporu: birebir=0),
bilgi ham ağırlık olarak değil AKIŞ olarak taşınır:

- Sınıflandırıcı (router): girdi → fonksiyonel küme skoru → uzman akışı.
  Saf EN ilkesi: en yüksek skor kazanır, denge/bonus terimi yok (plan Karar 2).
- Kalite hunisi: davranış skoru < %70 kapısının altındaki uzman HİÇ yüklenmez.
- Blok akışı: os.pread ile yalnız istenen tensör blokları okunur
  (safe_open/mmap YOK — FUSE/mmap ENOMEM dersi; ham-bayt streaming).
- Öğretmen danışmanı: AirLLM tarzı katman offload planı; tam yükleme yok,
  VRAM bütçesi (varsayılan 8GB — Karar 10) aşılmaz. Puanlayıcı yoksa puan
  UYDURULMAZ (score=None, status=plan_only).
- Distilasyon: davranış boşluğu > 0 kalırsa unsloth LoRA düzeltmesi.
- Σw·v: yalnız aynı anahtar + aynı şekil (fazc_merge kuralı); cross-arch
  mevkide CrossArchMergeError.
- Altın-kırmızı: uzman akışı kaynağı 4 kopya manifestiyle doğrulanır.

Kullanım:
  sym = StreamSymbiosis("/home/pc/mahoraga_montaj/winners")
  uzmanlar = sym.route("girdi metni")
  for tensor in sym.stream_expert(uzmanlar[0], [0, 3]): ...
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

# Plan Karar 2: kesmeyi KALİTE yapar — davranış %70 kapısı.
QUALITY_GATE = 0.70
# Karar 10: RTX 5050 Laptop 8GB VRAM — portable kısıt.
DEFAULT_VRAM_BUDGET = 8 * 1024**3
# Karar 9 + plan §kaynaklar: dil köprüsü veri kaynakları.
ALLOWED_DATASETS = {"swe-smith", "c4-tr", "c4-de"}

# Fonksiyonel küme leksikonu (token eşleşmesi). Roller: synapse_inventory
# ROLE_MAP'i ile uyumlu söz varlığı; pilot için 4 küme.
ROLE_LEXICON = {
    "kod": {
        "def", "class", "import", "function", "func", "bug", "error", "fix",
        "exception", "stack", "trace", "test", "pytest", "python", "refactor",
        "api", "return", "variable", "loop", "compile", "kod", "fonksiyon",
        "hata", "sinif", "sınıf", "degistir", "değiştir",
    },
    "guvenlik": {
        "security", "vulnerability", "vuln", "exploit", "xss", "injection",
        "cve", "auth", "password", "firewall", "malware", "token", "guvenlik",
        "güvenlik", "sizma", "sızma", "acik", "açık", "sifre", "şifre", "yetki",
    },
    "arac": {
        "tool", "tools", "terminal", "command", "shell", "script", "deploy",
        "git", "install", "package", "server", "cli", "pipeline", "cron",
        "arac", "araç", "komut", "dosya", "kurulum", "sunucu",
    },
    "dil": {
        "translate", "translation", "grammar", "sentence", "paragraph",
        "summarize", "summary", "text", "essay", "proofread", "dil", "ceviri",
        "çeviri", "cumle", "cümle", "ozet", "özet", "yazim", "yazım", "paragraf",
    },
}

_DTYPE_MAP = {"F32": np.float32, "F16": np.float16}
_TOKEN_RE = re.compile(r"[a-zçğıöşü0-9_]+")


class CrossArchMergeError(ValueError):
    """Aynı anahtar farklı şekil: doğrudan Σw·v birleştirme yapılamaz."""


class RedundancyError(ValueError):
    """Altın-kırmızı ihlali: yedek kopya sayısı eşiğin altında."""


@dataclass
class TeacherScore:
    """Öğretmen davranış skoru + kanıtlanabilir offload planı."""
    prompt: str
    teacher: str
    score: float | None          # puanlayıcı yoksa None — puan uydurulmaz
    status: str                  # "scored" | "plan_only"
    offload: dict                # plan_offload çıktısı


@dataclass
class LoRAResult:
    triggered: bool
    adapter: str | None
    dataset: str | None
    gap: float
    reason: str


def sigma_wv(entries: list[dict]) -> dict:
    """v_merged(key) = Σ_k w_k·v_k — yalnız aynı anahtar + aynı şekil.

    Kural fazc_merge.direct merge ile aynıdır; cross-arch mevkilerde hiçbir
    ağırlık doğrudan taşınmaz (plan §2.4). Şekil farkı = CrossArchMergeError.
    """
    merged: dict = {}
    shapes: dict = {}
    for e in entries:
        key = e["key"]
        shape = tuple(e["shape"])
        v = np.asarray(e["v"], dtype=np.float32)
        if key in shapes and shapes[key] != shape:
            raise CrossArchMergeError(
                f"{key}: şekil farkı {shapes[key]} vs {shape} — "
                f"cross-arch mevkide doğrudan birleştirme YOK")
        if key not in merged:
            merged[key] = float(e["w"]) * v
            shapes[key] = shape
        else:
            merged[key] = merged[key] + float(e["w"]) * v
    return merged


class StreamSymbiosis:
    """Amiral (çalışma zamanı) + uzman akışları (SSD kütüphanesi) bağlayıcısı.

    winners_root/stream_manifest.json şeması (fazc_shard_collect yedek
    manifestiyle uyumlu): experts{ad: {role, behavior_score, file, tensors:
    [{key, offset, nbytes, shape, dtype}], copies: [4 yol]}}.
    """

    def __init__(self, winners_root: str, device: str = "cuda",
                 vram_budget_bytes: int = DEFAULT_VRAM_BUDGET,
                 scorer: Callable | None = None):
        self.root = Path(winners_root)
        self.device = device
        self.vram_budget_bytes = int(vram_budget_bytes)
        self.scorer = scorer
        self.bytes_read = 0          # kümülatif SSD okuması (lazy kanıtı)
        self.last_stream_bytes = 0   # son stream_expert çağrısı
        manifest = self.root / "stream_manifest.json"
        if not manifest.is_file():
            raise FileNotFoundError(f"stream_manifest.json yok: {self.root}")
        self.experts = json.loads(manifest.read_text())["experts"]
        for name, ex in self.experts.items():
            path = self.root / ex["file"]
            if not path.is_file():
                raise FileNotFoundError(f"uzman akışı dosyası yok: {path}")
            ex["path"] = str(path)
            ex["total_bytes"] = path.stat().st_size

    # ---------- sınıflandırıcı (router) ----------

    def role_scores(self, text: str) -> dict:
        """Girdi → fonksiyonel küme skoru (token eşleşmesi, denge terimi yok)."""
        tokens = set(_TOKEN_RE.findall(text.lower()))
        return {role: len(tokens & words) for role, words in ROLE_LEXICON.items()}

    def route(self, text: str, roles: list[str] | None = None) -> list[str]:
        """Girdi → uzman akışı adları (kalite hunisi uygulanmış, skor sırası).

        Saf EN ilkesi: yalnız skor > 0 olan uzmanlar; sıralama saf skor
        azalanında — bonus/denge terimi yok. Davranış eşiği altındaki uzman
        hiç yüklenmez (returned bile edilmez).
        """
        scores = self.role_scores(text)
        ranked = []
        for name, ex in self.experts.items():
            if roles is not None and ex["role"] not in roles:
                continue
            if float(ex["behavior_score"]) < QUALITY_GATE:
                continue  # kalite hunisi: eşik altı hiç yüklenmez
            s = scores.get(ex["role"], 0)
            if s > 0:
                ranked.append((s, name))
        ranked.sort(key=lambda t: (-t[0], t[1]))
        return [name for _, name in ranked]

    # ---------- blok akışı (Colibri tarzı lazy offload) ----------

    def stream_expert(self, name: str, blocks: list[int]) -> Iterator[np.ndarray]:
        """Yalnız istenen tensör bloklarını SSD'den okur (os.pread, mmap YOK).

        blocks: uzman manifestindeki tensör indisleri. Her çağrıda gerçekten
        okunan bayt `last_stream_bytes`'ta tutulur — tam tensörden düşük
        kalması lazy akışın kanıtıdır.
        """
        ex = self.experts[name]
        self.last_stream_bytes = 0
        with open(ex["path"], "rb", buffering=0) as f:
            for idx in blocks:
                ent = ex["tensors"][idx]
                dt = _DTYPE_MAP.get(ent["dtype"])
                if dt is None:
                    raise NotImplementedError(
                        f"{ent['dtype']} desteklenmiyor (pilot: F32/F16)")
                buf = os.pread(f.fileno(), int(ent["nbytes"]), int(ent["offset"]))
                if len(buf) != int(ent["nbytes"]):
                    raise IOError(
                        f"{name}[{idx}]: kısa okuma "
                        f"{len(buf)}/{ent['nbytes']} — kaynak hasarlı olabilir")
                self.bytes_read += len(buf)
                self.last_stream_bytes += len(buf)
                yield np.frombuffer(buf, dtype=dt).reshape(ent["shape"])

    # ---------- öğretmen danışmanı (AirLLM katman offload) ----------

    def plan_offload(self, teacher: dict) -> dict:
        """VRAM bütçeli katman offload planı — tam yükleme YOK (Karar 10)."""
        n = int(teacher["layers"])
        layer_bytes = int(teacher["layer_bytes"])
        gpu_layers = min(n, self.vram_budget_bytes // layer_bytes)
        return {
            "teacher": teacher["name"],
            "layers_on_gpu": int(gpu_layers),
            "layers_on_cpu": int(n - gpu_layers),
            "gpu_bytes": int(gpu_layers * layer_bytes),
            "total_bytes": int(n * layer_bytes),
            "vram_budget_bytes": self.vram_budget_bytes,
            "device": self.device,
        }

    def consult_teacher(self, prompt: str, teacher: dict) -> TeacherScore:
        """Davranış skoru + offload planı. Puanlayıcı yoksa puan uydurulmaz."""
        plan = self.plan_offload(teacher)
        score = None
        if self.scorer is not None:
            score = float(self.scorer(prompt, teacher, plan))
        return TeacherScore(
            prompt=prompt,
            teacher=teacher["name"],
            score=score,
            status="scored" if score is not None else "plan_only",
            offload=plan,
        )

    # ---------- distilasyon (kalan davranış boşluğuna) ----------

    def distill_gap(self, dataset: str, gap: float) -> LoRAResult:
        """Davranış boşluğu > 0 ise unsloth LoRA düzeltmesi tetiklenir."""
        ds = dataset.lower()
        if ds not in ALLOWED_DATASETS:
            raise ValueError(
                f"bilinmeyen veri kaynağı: {dataset} "
                f"(izinli: {sorted(ALLOWED_DATASETS)})")
        if gap <= 0:
            return LoRAResult(False, None, ds, float(gap), "behavior_gate_passed")
        return LoRAResult(True, "unsloth-lora", ds, float(gap),
                          "behavior_gap_remains")

    # ---------- altın-kırmızı doğrulama ----------

    def verify_redundancy(self, min_copies: int = 4) -> bool:
        """Her uzman akışı kaynağı min_copy kopya manifestiyle işaretli olmalı."""
        missing = {
            name: len(ex.get("copies", []))
            for name, ex in self.experts.items()
            if len(ex.get("copies", [])) < min_copies
        }
        if missing:
            raise RedundancyError(
                f"altın-kırmızı ihlali (<{min_copies} kopya): {missing}")
        return True
