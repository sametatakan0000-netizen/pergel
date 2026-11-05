"""Kovaryans-ağırlıklı distilasyon seçimi — Faz-1 aracı (Adım 2 devamı).

Amaç: öğrenci uzmanlara (Faz-C) hangi sinaps/tensör bileşenlerinin
distile edileceğini SEÇMEK. Gerçek SVD kovaryans hesabı Faz-C'de
aktivasyonlarla yapılacak; burada seçim çekirdeği + LLM kovaryans
katsayısı doğrulaması var.

Kural (plan §8): "distill_covariance.py LLM covariance 0.01-0.3
(kod uzmanları)". Bu aralık dışında katsayı reddedilir.
"""
from __future__ import annotations

# Kod uzmanları için LLM kovaryans katsayısı aralığı (plan §8).
LLM_COVARIANCE_RANGE = (0.01, 0.3)

# Uzman türüne göre katsayı aralığı. 'kod' planla sabit; diğerleri
# geniş tutulur (Faz-C davranış doğrulaması daraltacak).
PRIOR_RANGES = {
    "kod": LLM_COVARIANCE_RANGE,
    "guvenlik": LLM_COVARIANCE_RANGE,
    "araclar": (0.01, 0.5),
    "genel": (0.001, 0.5),
}


def validate_prior(uzman: str, prior: float) -> float:
    """Kovaryans katsayısını uzman türüne göre doğrular.

    ValueError: bilinmeyen uzman ya da aralık dışı katsayı.
    """
    if uzman not in PRIOR_RANGES:
        raise ValueError(f"bilinmeyen uzman türü: {uzman}")
    lo, hi = PRIOR_RANGES[uzman]
    if not (lo <= float(prior) <= hi):
        raise ValueError(f"{uzman} için kovaryans katsayısı [{lo}, {hi}] aralığında olmalı: {prior}")
    return float(prior)


def covariance_weight(record: dict, prior: float) -> float:
    """Tek tensor kaydı için kovaryans-ağırlıklı skor.

    w = n_synapses * magnitude * (1 + prior * stabilité)
    stabilité = |magnitude| büyüklüğü (ham ölçek bilinmediğinden
    normalize edilmez — nispi sıralama için yeterli).
    # shortcut: gerçek kovaryans (aktivasyon) yerine magnitude vekâleten,
    #   Faz-C aktivasyon ölçümü gelince yerini alacak.
    """
    n = float(record.get("n_synapses", 0))
    mag = abs(float(record.get("magnitude") or 0.0))
    return n * mag * (1.0 + float(prior) * mag)


def select_for_distillation(
    records: list[dict],
    budget: int,
    uzman: str = "kod",
    prior: float | None = None,
) -> dict:
    """Bütçe altında en yüksek ağırlıklı tensörleri seç (açgözlü, deterministik).

    Bütçe sinaps cinsinden. Aynı ağırlıkta kalanlar key ile kararlı
    sıralanır. Dönen sözlük seçim + denetim alanları taşır.
    """
    if prior is None:
        prior = 0.15 if uzman in ("kod", "guvenlik") else 0.1
    prior = validate_prior(uzman, prior)
    if budget <= 0:
        raise ValueError("bütçe pozitif olmalı")

    scored = sorted(
        records,
        key=lambda r: (-covariance_weight(r, prior), str(r.get("key", ""))),
    )
    chosen, used = [], 0
    for rec in scored:
        n = int(rec.get("n_synapses", 0))
        if used + n <= budget:
            chosen.append(rec)
            used += n
    return {
        "chosen_keys": [r.get("key") for r in chosen],
        "chosen_tensors": len(chosen),
        "used_synapses": used,
        "budget": budget,
        "prior": prior,
        "uzman": uzman,
        "within_budget": used <= budget,
    }
