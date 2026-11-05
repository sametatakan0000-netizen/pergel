"""Multi-D doğrulama matrisi — Faz-5 (plan §8: L1-norm maskesi +
Covariance-Weighted SVD + doğrulama matrisi).

Yönler: kod / güvenlik / araç / dil (plan §8 Multi-D).
Geçiş kriterleri behavior_audit (%70) ve red_collection (%10 red loss)
eşikleriyle ortak.

KISA YOL (dürüst kayıt): gerçek SVD hesaplaması gövde silineceği için
model aktivasyonu üzerinde Faz-C eğitiminde yapılır; buradaki
`covariance_weighted_svd` kovaryans-ağırlıklı bileşen SIRALAMASI proxy'sidir.
"""
from __future__ import annotations

from .behavior_audit import BEHAVIOR_PASS_THRESHOLD
from .red_collection import RED_LOSS_THRESHOLD
from .distill_covariance import covariance_weight

# Plan §8 Multi-D yönleri.
DIRECTIONS = ("kod", "guvenlik", "arac", "dil")


def l1_mask(records: list[dict], threshold: float) -> dict:
    """L1-norm maskesi: l1 = n_synapses * |magnitude| >= threshold kalanlar."""
    kept, dropped = [], []
    for rec in records:
        l1 = rec["n_synapses"] * abs(rec["magnitude"])
        (kept if l1 >= threshold else dropped).append(rec["key"])
    return {"kept_keys": kept, "kept": len(kept), "total": len(records),
            "dropped_keys": dropped}


def covariance_weighted_svd(records: list[dict], prior: float, keep_ratio: float) -> dict:
    """Kovaryans-ağırlıklı bileşen seçimi (SVD proxy — bkz. modül docstring).

    Bileşenler covariance_weight'e göre azalan sıralanır; keep_ratio
    kadarı (en az 1) tutulur.
    """
    if not 0.0 < keep_ratio <= 1.0:
        raise ValueError("keep_ratio (0,1] aralığında olmalı")
    ranked = sorted(
        records,
        key=lambda r: covariance_weight(r, prior),
        reverse=True,
    )
    keep_n = max(1, int(len(ranked) * keep_ratio))
    kept = ranked[:keep_n]
    return {"kept_keys": [r["key"] for r in kept], "kept": len(kept),
            "total": len(records)}


def validation_matrix(olcum: dict) -> dict:
    """Çok-yönlü doğrulama matrisi: yön x ölçüm -> karar.

    Geç kriteri: red_loss <= %10 VE behavior_rate >= %70.
    'tamam' yalnız 4 yönün TAMAMI geçince True (paketleme kapısı).
    """
    satirlar, gerekceler = {}, {}
    for yon in DIRECTIONS:
        m = olcum.get(yon)
        if m is None:
            continue
        reasons = []
        if m.get("red_loss", 0.0) > RED_LOSS_THRESHOLD:
            reasons.append(f"red_loss {m['red_loss']:.2f} > {RED_LOSS_THRESHOLD}")
        if m.get("behavior_rate", 0.0) < BEHAVIOR_PASS_THRESHOLD:
            reasons.append(f"behavior_rate {m['behavior_rate']:.2f} < {BEHAVIOR_PASS_THRESHOLD}")
        satirlar[yon] = {
            "aktivasyon_delta": m.get("aktivasyon_delta"),
            "kovaryans_delta": m.get("kovaryans_delta"),
            "red_loss": m.get("red_loss"),
            "behavior_rate": m.get("behavior_rate"),
            "karar": "gec" if not reasons else "red",
        }
        gerekceler[yon] = reasons
    tamam = (
        set(satirlar.keys()) == set(DIRECTIONS)
        and all(r["karar"] == "gec" for r in satirlar.values())
    )
    return {"satirlar": satirlar, "gerekceler": gerekceler, "tamam": tamam,
            "esikler": {"red_loss": RED_LOSS_THRESHOLD, "behavior_rate": BEHAVIOR_PASS_THRESHOLD}}
