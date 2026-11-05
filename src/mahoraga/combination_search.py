"""Kombinasyon arama motoru — sinaps süzme + kombinasyon simülasyonu.

Kullanıcı tezi (05.11.2026): sinapslar eşsiz parçalar DEĞİLDİR; farklı
aileler aynı işlevi farklı yollarla yapar (fonksiyonel kümeler). Geniş ve
esnek tutup "en" iyi temsilleri süzerek ve kombinasyonları simüle ederek
nihai konfigürasyona ulaşırız.

2^N uyarısı (dürüst kayıt): tüm kombinasyonların simülasyonu uzay
patlaması nedeniyle imkansız; burada bütçe-sınırlı arama var:
exhaustive küçük k'ya kadar + bütçe kesmesi (shortcut: greedy/beam v2).
Oracle = davranış kapıları ucuz skorlaması (tam model koşusu gerekmez).
"""
from __future__ import annotations

import itertools

from .distill_covariance import covariance_weight
from .synapse_inventory import classify_key

# "Farklı yol" bonusu: aynı sonuca giden farklı aile yolları ödüllendirilir.
CESITLILIK_BONUSU = 0.05


def functional_clusters(records: list[dict]) -> dict[str, list[dict]]:
    """Sinapsları işlevsel rollerine göre kümele (aynı iş = aynı küme)."""
    out: dict[str, list[dict]] = {}
    for rec in records:
        out.setdefault(classify_key(rec["key"]), []).append(rec)
    return out


def select_best(clusters: dict[str, list[dict]], hedef_davranis: str,
                model_skorlari: dict, prior: float = 0.15,
                max_aday: int = 5) -> dict[str, dict]:
    """Her kümeden "en" iyi temsili süz.

    Üyelik skoru = modelin hedef davranış skoru × kovaryans ağırlığı.
    'adaylar' sıralı: kombinasyon simülasyonu bunlar üzerinden yürür.
    """
    out: dict[str, dict] = {}
    for rol, members in clusters.items():
        def skor(rec: dict) -> float:
            return model_skorlari[rec["model"]][hedef_davranis] * covariance_weight(rec, prior)
        ranked = sorted(members, key=skor, reverse=True)
        out[rol] = {
            "en": ranked[0]["key"],
            "adaylar": [r["key"] for r in ranked[:max_aday]],
            "skorlar": {r["key"]: skor(r) for r in ranked[:max_aday]},
        }
    return out


def combination_score(combo: list[dict], model_skorlari: dict,
                      hedef_davranis: str) -> float:
    """Kombinasyon skoru: ortalam davranış skoru + çeşitlilik bonusu.

    Çeşitlilik bonusu = 0.05 × (farklı aile sayısı − 1): aynı sonuca giden
    farklı yollar bir arada olunca konfigürasyon daha dayanıklı olur.
    """
    if not combo:
        return 0.0
    temel = sum(model_skorlari[r["model"]][hedef_davranis] for r in combo) / len(combo)
    aileler = {r.get("aile", r["model"]) for r in combo}
    return temel + CESITLILIK_BONUSU * (len(aileler) - 1)


def simulate_combinations(adaylar: list, oracle, max_k: int = 3,
                          budget: int = 1000) -> dict:
    """Kombinasyon simülasyonu: 1..max_k alt-kümeler, bütçe kesmeli.

    oracle(combo_keys) -> float. Bütçe aşılırsa arama durur ve
    'tam_exhaustive' False olur (kalan uzay greedy/beam'e devredilir).
    """
    sim = 0
    best: list | None = None
    best_score = float("-inf")
    tam = True
    for k in range(1, max_k + 1):
        for combo in itertools.combinations(adaylar, k):
            if sim >= budget:
                tam = False
                break
            s = oracle(list(combo))
            sim += 1
            if s > best_score:
                best_score, best = s, list(combo)
        if sim >= budget:
            tam = False
            break
    return {
        "en_iyi": best or [],
        "skor": best_score if best is not None else None,
        "simulasyon_sayisi": sim,
        "tam_exhaustive": tam,
    }
