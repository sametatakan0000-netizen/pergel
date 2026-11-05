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
            "davranis_skoru": model_skorlari[ranked[0]["model"]][hedef_davranis],
        }
    return out


def kadro_view(records: dict, combo_keys: list[str]) -> dict:
    """Oyuncu görünümü: modeller = oyuncular, roller = mevkiler.

    Kadro (kombinasyon) tek tek sinapslardan çok "hangi oyuncu hangi mevkide"
    sorusuna göre okunur (oyuncu metaforu, 2026-11-05).
    """
    kadro: dict = {}
    for k in combo_keys:
        r = records.get(k)
        if not r:
            continue
        kayit = kadro.setdefault(r["model"], {"mevkiler": [], "siniflar": set()})
        kayit["mevkiler"].append(r.get("rol", "?"))
        kayit["siniflar"].add(r.get("sinif", "?"))
    out = {}
    for oyuncu, kayit in kadro.items():
        out[oyuncu] = {
            "mevkiler": sorted(set(kayit["mevkiler"])),
            "oynadigi_mevki": len(kayit["mevkiler"]),
            "siniflar": sorted(kayit["siniflar"]),
        }
    return {"oyuncu_sayisi": len(out), "kadro": out}


def combination_score(combo: list[dict], model_skorlari: dict,
                      hedef_davranis: str) -> float:
    """Saf 'EN' skoru: mevkilerin davranış katkıları TOPLAMI.

    Oyuncu ilkesi (2026-11-05): modeller değişkendir (istedikleri biçime
    girebilirler), farklı ailelerin gittiği yolları başka aileler de
    yürüyebilir — yollar aileye kilitli DEĞİLDİR. Bu yüzden aile çeşitlilik
    bonusu ya da takım uyumu YOKTUR: her mevkide işi EN iyi yapan kazanır,
    kazanmayan yola gerek yoktur. Tam yapılandırma = her mevkinin "en"i;
    her mevki toplama katkı verir (kaplama).
    """
    return sum(model_skorlari[r["model"]][hedef_davranis] for r in combo)


def funnel_candidates(best: dict[str, dict], min_skor: float = 0.6,
                      ust_sinir: int = 18) -> dict[str, dict]:
    """'En' hunisi: kesmeyi KALİTE yapar, sayım değil (model/sinaps mantığı).

    Davranış skoru eşiğinin altındaki kümeler elenir. Havuz ust_sinir'i
    aşarsa en düşük skorlular gider (yine kalite sırasıyla); ust_sinir
    yalnız son sigortadır, normalde huni yeter.
    """
    gecen = {rol: v for rol, v in best.items() if v.get("davranis_skoru", 0.0) >= min_skor}
    if len(gecen) > ust_sinir:
        sirali = sorted(gecen.items(),
                        key=lambda kv: (kv[1]["davranis_skoru"],
                                        kv[1]["skorlar"].get(kv[1]["en"], 0.0)),
                        reverse=True)
        gecen = dict(sirali[:ust_sinir])
    return gecen


def simulate_combinations(adaylar: list, oracle, max_k: int | None = None,
                          budget: int = 500_000) -> dict:
    """Kombinasyon simülasyonu: 1..max_k alt-kümeler (varsayılan TÜM boyutlar).

    oracle(combo_keys) -> float. Kesme huniyle yapılır (funnel_candidates),
    bütçe YALNIZCA güvenlik supabıdır (havuz kazara büyürse); aşılırsa
    'tam_exhaustive' False döner.
    """
    if max_k is None:
        max_k = len(adaylar)  # tüm olası kombinasyonlar: 2^N − 1
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
