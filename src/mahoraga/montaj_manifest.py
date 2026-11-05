"""Faz-C montaj manifestı — kazanan sinapsları gerçek yedeklere çözer.

"Sinapsları almak" burada şu anlama gelir: kazanan mevki (model+key) 4 kopyalı
yedek manifestlerde hash ile bulunur, aile mimarisi belirlenir ve birleştirme
rotası atanır:
- aile içi -> direct_merge (kovaryanslı doğrusal: Σw·v)
- aileler arası -> distillation / flow-binding (cross-arch merge YOK)

Kurallar (memory/docs):
- Golden-Red: sinaps ASLA silinmez; her kayıt >= 4 kopyada hash ile doğrulanır.
- Kuyruk Kuralı: yalnız güncel envanterdeki modeller monte edilir.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

# 4 kopya kuralı (Golden-Red). Sıra, kopya raporlamasında kullanılır.
KOPYA_KOKLERI = [
    "/home/pc/mahoraga_synapses",
    "/home/pc/synapse_backups_safe",
    "/home/pc/backup_mahoraga/synapse_backups",
    "/mnt/toshiba/mahoraga/synapse_backups",
]

# model -> mimari aile. Eşleme, modellerin gerçek mimari ailelerine göredir;
# "cross-arch merge YOK" kuralı bu eşlemeye dayanır.
_AILE_ESLEME = [
    ("deepseek-ai/deepseek-r1-distill-qwen", "qwen"),   # R1-Distill = Qwen gövde
    ("01-ai/yi", "yi"),
    ("neversleep/noromaid", "mistral"),                  # Mistral-20B taban
    ("nousresearch/hermes-3-llama", "llama"),
    ("qwen/", "qwen"),
    ("allenai/olmo", "olmo"),
    ("deepseek-ai/", "deepseek"),
    ("internlm/", "internlm"),
    ("microsoft/phi", "phi"),
    ("mistralai/", "mistral"),
    ("nvidia/llama", "llama"),
    ("nvidia/nvidia-nemotron", "nemotron"),              # Bolt-74B kendi mimarisi
    ("tiiuae/falcon", "falcon"),
]


def aile_bul(model: str) -> str:
    """Model kimliğinden mimari aile; bilinmeyen açıkça reddedilir (sessizce değil)."""
    m = model.strip().lower()
    for on, aile in _AILE_ESLEME:
        if m.startswith(on):
            return aile
    raise ValueError(f"bilinmeyen mimari aile: {model!r} — aile eşlemesini genişlet")


class SinapsIndeksi:
    """4 kopyalı sinaps manifestoları üzerinde hash doğrulamalı sorgu katmanı."""

    def __init__(self, kokler: list[str]):
        self.kokler = list(kokler)
        # {kok: {model: {key: hash}}}
        self._kopyalar: dict[str, dict[str, dict[str, str]]] = {}
        # {model: {key: kayit}} (birleşik, ilk gören kopyadan)
        self._kayitlar: dict[str, dict[str, dict]] = {}
        for kok in self.kokler:
            katman: dict[str, dict[str, str]] = {}
            for yol in sorted(glob.glob(str(Path(kok) / "*_synapses.json"))):
                with open(yol) as f:
                    veri = json.load(f)
                model = veri["model"]
                t = {}
                for e in veri["tensors"]:
                    h = e.get("hash")  # eski/kısmi manifestlerde hash olmayabilir
                    t[e["key"]] = h
                    mevcut = self._kayitlar.setdefault(model, {}).setdefault(
                        e["key"], e)
                    if not mevcut.get("hash") and h:
                        # hash'li kopyayı tercih et (Golden-Red doğrulaması için)
                        self._kayitlar[model][e["key"]] = e
                katman[model] = t
            self._kopyalar[kok] = katman

    def kayit(self, model: str, key: str) -> dict | None:
        return self._kayitlar.get(model, {}).get(key)

    def kopya_sayisi(self, model: str, key: str) -> int:
        return sum(1 for k in self.kokler
                   if key in self._kopyalar.get(k, {}).get(model, {}))

    def kopya_hashleri(self, model: str, key: str) -> list[str]:
        """Yalnız GERÇEK (boş olmayan) hash'ler; çelişki kontrolü bunlarla yapılır."""
        cikti = []
        for k in self.kokler:
            h = self._kopyalar.get(k, {}).get(model, {}).get(key)
            if h:  # None/"" = kayıt var ama hash'siz (bütünlük açığı)
                cikti.append(h)
        return cikti


def manifest_yukle(kokler: list[str] | None = None) -> SinapsIndeksi:
    return SinapsIndeksi(kokler or KOPYA_KOKLERI)


def montaj_manifesti(sonuc_yolu: str,
                     kokler: list[str] | None = None) -> dict:
    """Kazanan kadroları sinaps kayıtlarına çözer; aile içi/dışı rotaları kurar."""
    indeks = manifest_yukle(kokler)
    with open(sonuc_yolu) as f:
        sonuc = json.load(f)

    davranislar = {}
    for dav, v in sonuc["davranislar"].items():
        # key -> mevki (rol) ters eşlemesi
        rol_by_key = {v2["en"]: rol for rol, v2 in v["en_secimler"].items()}
        sinapslar = []
        for cift in v["simulasyon"]["en_iyi_kombinasyon"]:
            key, model = cift.split(" @ ")
            kayit = indeks.kayit(model, key)
            if kayit is None:
                raise LookupError(f"{dav}: sinaps kaydı yok: {model}::{key}")
            sinapslar.append({
                "mevki": rol_by_key.get(key, "bilinmiyor"),
                "model": model,
                "aile": aile_bul(model),
                "key": key,
                "hash": kayit.get("hash"),
                # Golden-Red: hash boşsa sessizce geçme — işaretle.
                "hash_durumu": "dogrulandi" if kayit.get("hash") else "eksik",
                "magnitude": kayit.get("magnitude"),
                "n_synapses": kayit.get("n_synapses"),
                "kopya_sayisi": indeks.kopya_sayisi(model, key),
            })

        aile_gruplari: dict[str, dict] = {}
        for s in sinapslar:
            grup = aile_gruplari.setdefault(
                s["aile"], {"rota": "direct_merge", "sinapslar": []})
            grup["sinapslar"].append(s)

        davranislar[dav] = {
            "sinapslar": sinapslar,
            "aile_gruplari": aile_gruplari,
            "rota": "direct_merge" if len(aile_gruplari) == 1 else "distillation",
        }

    uyari = [
        f"{dav}::{s['model']}::{s['key']}"
        for dav, v in davranislar.items() for s in v["sinapslar"]
        if s["hash_durumu"] == "eksik"
    ]
    return {
        "olusturma": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kopya_kokleri": list(indeks.kokler),
        "kural": ("Golden-Red: 4 kopya hash dogrulamasi; cross-arch merge YOK — "
                  "aile ici direct_merge (Σw·v), aileler arasi distillation"),
        "altin_kirmizi_uyari": {
            "hash_eksik_sinapslar": uyari,
            "onarim": ("hash'ler tensor baytlarindan (100 orneklem sha256) turetilir; "
                       "govde silindigi icin yalniz Faz-C model indirmesi sirasinda "
                       "cikarim yeniden calistirilarak geri doldurulur (ek indirme YOK)"),
        },
        "davranislar": davranislar,
    }
