"""Faz-6: Karmaşık→Basit — SİNAPS BİRLEŞTİRME (MERGE-FIRST).

Stil kuralı (kullanıcı tezi + plan §8): çıkarılan sinapslar DOĞRUDAN
birleştirilir. Gradyan-eğitim/backprop bizim tarzımız DEĞİLDİR — sinapslar
boşuna çıkarılmadı (gövde silindi, sinapslar yedekli).

Kovaryanslı ağırlıklar = doğrusal birleştirme katsayıları (Σ w_i·v_i).

Strateji seçimi (kendi kuralımız: cross-arch merge YOK):
- direct_merge : donor ile hedef aynı mimari -> sinapsları doğrudan merge
- stitch       : cross-arch -> model_stitching akış bağlama (amiral+uzman
                 simbiyoz; ağırlık değil akış birleştirilir)
- distill      : yalnız davranış boşluğu kalırsa SON ÇARE (kapılar yine geçerli)

Ölçüm zorunlu: her yoldan sonra davranış kapıları (red loss %10, davranış %70).
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

# Faz-5'de doldurulan gerçek davranış doğrulama verisi (kapı ölçümü için).
DATA_FILES = {
    "kod": "/home/pc/mahoraga_davranis_veri/kod_swebench_verified.jsonl",
    "guvenlik": "/home/pc/mahoraga_davranis_veri/guvenlik_advbench.jsonl",
    "arac": "/home/pc/mahoraga_davranis_veri/arac_taubench.jsonl",
    "dil_karar": "/home/pc/mahoraga_davranis_veri/dil_karar_banking77.jsonl",
}

# Birleştirme sonrası kuantizasyon (plan §8; kod detayı tekrar araştırılacak).
HQQ_SPEC = {
    "yontem": "HQQ",
    "nbits": 4,
    "group_size": 64,
    "not": "kod detayı tekrar araştırılacak (plan §8); birleştirmeden sonra uygulanır",
}

# Varsayılan mimari eşlemesi: envanter gerçeği (donor, hedef) — çoğu cross-arch.
# Aynı mimari çiftlerde 'direct_merge' seçilir.
VARSAYILAN_MIMARI = {
    "kod": ("nemotron-cortexa", "hedef-govde"),
    "guvenlik": ("orbitar", "hedef-govde"),
    "arac": ("gpt-oss", "hedef-govde"),
    "dil_karar": ("nemotron-3", "hedef-govde"),
}


def strateji_sec(donor_mimari: str, hedef_mimari: str) -> str:
    """Aynı mimari -> direct_merge; cross-arch -> stitch (akış bağlama)."""
    return "direct_merge" if donor_mimari == hedef_mimari else "stitch"


def merge_plan(catalog: dict | None = None, mimari: dict | None = None) -> dict:
    """Davranış başına birleştirme planı (gradyan eğitimi YOK).

    mimari: {behavior: (donor_mimari, hedef_mimari)} — verilmezse envanter
    varsayılanı. Strateji mimari uyumundan türetilir; 'distill' yalnız
    son çare olarak plana elle eklenir (bkz. modül docstring).
    """
    catalog = catalog or build_catalog()
    mimari = mimari or VARSAYILAN_MIMARI
    planlar = {}
    for cls in BEHAVIOR_CLASSES:
        donor, hedef = mimari[cls]
        suite = catalog["suites"][cls]
        planlar[cls] = {
            "amiral": BEHAVIOR_ADMIRALS[cls],
            "strateji": strateji_sec(donor, hedef),
            "mimari": {"donor": donor, "hedef": hedef},
            "veri_kaynak": DATA_FILES[cls],   # kapı ölçümü (doğrulama matrisi)
            "benchmark": suite["kaynak"],
            "orneklem": suite["orneklem"],
            "quant": dict(HQQ_SPEC),
            "agir_kayip_siniri": RED_LOSS_THRESHOLD,
        }
    return {
        "birlestirmeler": planlar,
        "hedef": "her davranışın bir modeli (tam davranış dağılımı, ağır kayıp yok)",
        "gecme_esigi": BEHAVIOR_PASS_THRESHOLD,
        "stil": "merge-first; gradyan eğitimi yok; cross-arch'de stitch/distill",
    }


def merge_coefficients(synapse_sets: list[dict], prior: float) -> dict:
    """Kovaryanslı DOĞRUSAL birleştirme katsayıları (Σ w_i·v_i, 1.0'a normalize).

    Her sinaps seti: {'key', 'n_synapses', 'magnitude'} (envanter manifestosu).
    """
    if not synapse_sets:
        return {}
    weights = {s["key"]: covariance_weight(s, prior) for s in synapse_sets}
    toplam = sum(weights.values())
    return {k: w / toplam for k, w in weights.items()}


def post_merge_gate(results: dict) -> bool:
    """Birleştirme sonrası davranış kapısı: 4 davranışın TAMAMI >= %70.

    'Ağır kayıp yok' (plan §8): merge yolundan bağımsız, davranış ölçümü
    zorunlu; geçemeyen birleştirme kabul edilmez.
    """
    return set(results.keys()) == set(BEHAVIOR_CLASSES) and all(
        r.get("behavior_rate", 0.0) >= BEHAVIOR_PASS_THRESHOLD
        for r in results.values()
    )
