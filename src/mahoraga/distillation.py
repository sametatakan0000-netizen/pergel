"""Faz-6: Karmaşık→Basit distilasyon planı (plan §8).

Her üstün davranış için taze en-iyi-sınıf amiral kaynak seçilir; her
davranışın bir öğrencisi eğitilir (tam davranış dağılımı, AĞIR KAYIP YOK).
Öğrenciler HQQ ile kuantize edilir (kod detayı tekrar araştırılacak — plan).
Örnek ağırlıkları distill_covariance kovaryans ağırlığıyla verilir.

Gerçek eğitim Faz-C motorunda (RTX 5050, davranış dağılımı öğretmeni)
yapılır; bu modül PLAN + ağırlık + kapı katmanıdır (GPU'suz doğrulanabilir).
"""
from __future__ import annotations

from .behavior_audit import BEHAVIOR_PASS_THRESHOLD
from .behavior_tests import BEHAVIOR_CLASSES, build_catalog
from .distill_covariance import covariance_weight
from .red_collection import RED_LOSS_THRESHOLD

# Öğretmen haritası Faz-C kanıtı: davranış başına üstün model aile.
BEHAVIOR_ADMIRALS = {
    "kod": "Nemotron-CORTEXA.121b",
    "guvenlik": "ORBITER-2.34b",
    "arac": "GPT-OSS-120B.117b",
    "dil_karar": "Nemotron-3-Super.249b",
}

# Faz-5'de doldurulan gerçek veri setleri (kural: uydurma yok).
DATA_FILES = {
    "kod": "/home/pc/mahoraga_davranis_veri/kod_swebench_verified.jsonl",
    "guvenlik": "/home/pc/mahoraga_davranis_veri/guvenlik_advbench.jsonl",
    "arac": "/home/pc/mahoraga_davranis_veri/arac_taubench.jsonl",
    "dil_karar": "/home/pc/mahoraga_davranis_veri/dil_karar_banking77.jsonl",
}

# HQQ kuantizasyon şeması (plan §8; kod detayı tekrar araştırılacak).
HQQ_SPEC = {
    "yontem": "HQQ",
    "nbits": 4,
    "group_size": 64,
    "not": "kod detayı tekrar araştırılacak (plan §8); Faz-6.5'te uygulanır",
}


def build_student_plan(catalog: dict | None = None) -> dict:
    """Davranış başına öğrenci planı: amiral kaynak + veri + HQQ + kayıp sınırı."""
    catalog = catalog or build_catalog()
    ogrenciler = {}
    for cls in BEHAVIOR_CLASSES:
        suite = catalog["suites"][cls]
        ogrenciler[cls] = {
            "amiral": BEHAVIOR_ADMIRALS[cls],
            "veri_kaynak": DATA_FILES[cls],
            "benchmark": suite["kaynak"],
            "orneklem": suite["orneklem"],
            "quant": dict(HQQ_SPEC),
            "agir_kayip_siniri": RED_LOSS_THRESHOLD,  # ağır kayıp yok: <= %10
        }
    return {
        "ogrenciler": ogrenciler,
        "hedef": "her davranışın bir modeli (tam davranış dağılımı, ağır kayıp yok)",
        "gecme_esigi": BEHAVIOR_PASS_THRESHOLD,
    }


def covariance_sample_weights(records: list[dict], prior: float) -> dict:
    """Kovaryanslı örnek ağırlıkları (1.0'a normalize)."""
    if not records:
        return {}
    weights = {r["key"]: covariance_weight(r, prior) for r in records}
    toplam = sum(weights.values())
    return {k: w / toplam for k, w in weights.items()}


def student_gate(results: dict) -> bool:
    """'Ağır kayıp yok' kapısı: 4 davranışın TAMAMI >= %70 davranış oranı."""
    return set(results.keys()) == set(BEHAVIOR_CLASSES) and all(
        r.get("behavior_rate", 0.0) >= BEHAVIOR_PASS_THRESHOLD
        for r in results.values()
    )
