"""Faz-5.5: Davranış denetimi — PRM/ORM ödül, seçim ağırlığı, davranış puanı.

Plan §8 Faz-5.5 kuralları:
1. PRM/ORM süreç ödülü (AI-Safety Institute Canada): ORM yalnız son kararı
   ödüllendirir; PRM her adımı ödüllendirir — uzun araç çağrısı zincirlerinde
   PRM kullan.
2. Karmaşık -> Basit Karmaşık -> Basit akışı ("Basit Karmaşık": kod/güvenlik +
   araç çağırmada etkili uzman çifti; "Basit": ondan türeyen küçük öğrenci;
   "Karmaşık": niyet kavrayışı — Netmind tekniği).
3. Seçim ağırlığı düzeltmesi: AdaBoost/WINNOW türü ağırlık büyütme; başarı
   oranı yüksek davranışı davranış kataloğuna ekle.
4. Davranış/denetim puanlama: yüksek örneklemeli denetçi + davranış testi;
   başarı oranı davranış olarak kaydedilir. %70 eşik davranış doğrulamasıdır
   (Faz-C) ve paketlemeden önce geçilmelidir.

Davranış testleri kendileri (soru setleri, denetçi model çağrıları) ayrı
çalışmada; burada deterministik puanlama/ödül çekirdeği var.
"""
from __future__ import annotations

import math

# Davranış doğrulama eşiği (Faz-C %70).
BEHAVIOR_PASS_THRESHOLD = 0.70

# Karmaşık -> Basit Karmaşık -> Basit uzman akışı (plan §8 Faz-5.5-2).
FLOW_STAGES = ("karmasik", "basit_karmasik", "basit")

# AdaBoost yumuşatma katsayısı (ağırlık büyütme hızı).
ADABOOST_ALPHA = 1.0


def _check_steps(steps: list[float]) -> list[float]:
    vals = [float(s) for s in steps]
    if not vals:
        raise ValueError("adım listesi boş olamaz")
    return vals


def orm_score(steps: list[float]) -> float:
    """Outcome reward: yalnız son adım (nihai sonuç) sayılır."""
    return _check_steps(steps)[-1]


def prm_score(steps: list[float]) -> float:
    """Process reward: her adımın ortalaması (uzun araç zincirleri için)."""
    vals = _check_steps(steps)
    return sum(vals) / len(vals)


def chain_reward(steps: list[float], mode: str = "prm") -> float:
    """Zincir ödülü — 'prm' (varsayılan, uzun zincir) ya da 'orm'."""
    if mode == "prm":
        return prm_score(steps)
    if mode == "orm":
        return orm_score(steps)
    raise ValueError(f"bilinmeyen ödül modu: {mode}")


def adaboost_update(weights: list[float], errors: list[float]) -> list[float]:
    """AdaBoost tarzı ağırlık büyütme: hata yüksek olan ağırlık büyür.

    w_i <- w_i · exp(α·err_i), sonra normalize (toplam 1). err ∈ [0, 1].
    """
    if len(weights) != len(errors):
        raise ValueError("ağırlık ve hata listeleri eşit uzunlukta olmalı")
    raw = [w * math.exp(ADABOOST_ALPHA * float(e)) for w, e in zip(weights, errors)]
    total = sum(raw)
    if total == 0:
        raise ValueError("ağırlık toplamı sıfır olamaz")
    return [r / total for r in raw]


def winnow_update(weights: list[float], errors: list[float]) -> list[float]:
    """WINNOW tarzı çarpan güncellemesi: hata -> x2 (yükselt), doğru -> x0.5 (azalt).

    err > 0.5 hata sayılır (Littlestone'ın yükseltilmiş/alçaltılmış WINNOW'u).
    """
    if len(weights) != len(errors):
        raise ValueError("ağırlık ve hata listeleri eşit uzunlukta olmalı")
    out = []
    for w, e in zip(weights, errors):
        f = 2.0 if float(e) > 0.5 else 0.5
        out.append(float(w) * f)
    return out


def update_selection_weights(weights: list[float], errors: list[float], method: str = "adaboost") -> list[float]:
    """Seçim ağırlığı düzeltmesi — yöntem dispatch (plan §8 Faz-5.5-3)."""
    if method == "adaboost":
        return adaboost_update(weights, errors)
    if method == "winnow":
        return winnow_update(weights, errors)
    raise ValueError(f"bilinmeyen ağırlık yöntemi: {method}")


def behavior_score(successes: int, trials: int) -> dict:
    """Yüksek örneklemeli davranış puanı: başarı oranı + doğrulama kararı.

    Başarı oranı davranış kataloğuna davranış olarak kaydedilir;
    gecer = rate >= BEHAVIOR_PASS_THRESHOLD (paketleme kapısı).
    """
    if trials <= 0:
        raise ValueError("deneme sayısı pozitif olmalı")
    if not (0 <= successes <= trials):
        raise ValueError("başarı sayısı [0, trials] aralığında olmalı")
    rate = successes / trials
    return {
        "successes": successes,
        "trials": trials,
        "rate": rate,
        "esik": BEHAVIOR_PASS_THRESHOLD,
        "gecer": rate >= BEHAVIOR_PASS_THRESHOLD,
    }


def flow_check(stages: tuple | list | None = None) -> bool:
    """Uzman akışı kontrolü: Karmaşık -> Basit Karmaşık -> Basit tam mı?"""
    return tuple(stages) == FLOW_STAGES if stages is not None else True
