"""Faz-5: Kırmızı toplama + kurtarma matrisi.

Kırmızı = ameliyattan sonra KAYBEDİLMEMESİ gereken davranış (araç,
güvenlik, dil/karar, kod, matematik, araştırma — plan §8). Bu modül:

- çift yönlü ölçüm (aktivasyon + kovaryans)
- kırmızı kayıp (red loss) eşiği kontrolü
- Marjinal kayıp AUC doğrulaması (0.98 mühendislik hedefi; "PAQ" adı doğrulanamadı — bkz. plan §7.1; kanıt bandı LSGC %70-99)
- altın-kırmızı 4 kopya yedek kuralı
- kurtarma matrisi (kırmızı davranış -> reçete ailesi + yedek kaynakları)

Model-güdümlü davranış testleri (Faz-5.5: PRM/ORM, IA gizlilik) ayrı
çalışmada; burada yalnız deterministik çekirdek var.
"""
from __future__ import annotations

import math

BEHAVIOR_TURS = ("kod", "guvenlik", "arac", "dil_karar", "matematik", "arastirma")

# Kırmızı kayıp eşiği: davranış puanındaki en büyük düşüş bunu aşarsa
# ameliyat reddedilir (geri alma / kurtarma matrisi devreye girer).
RED_LOSS_THRESHOLD = 0.10

# Marjinal kayıp AUC hedefi (mühendislik kapısı). "PAQ" adı kamuya açık
# kaynakta bulunamadı (plan §7.1); kanıt çapası: LSGC steganaliz bandı (arXiv:2406.04218).
PAQ_AUC_TARGET = 0.98

# Altın-kırmızı kural: sinaps yedekleri asla 4 kopyadan az olmaz
# (depo + Toshiba + mahoraga_synapses/ + manifest).
BACKUP_COPY_MIN = 4

# Kurtarma matrisinin standart yedek kaynakları.
BACKUP_SOURCES = ("depo", "toshiba", "mahoraga_synapses", "manifest")


def dual_measure(samples: list[float]) -> dict:
    """Çift yönlü ölçüm: aktivasyon (mean|x|) + kovaryans (varyans).

    # shortcut: gerçek aktivasyon hook'ları (TransformerLens/bridge) Faz-5.5'de
      bağlanacak; burada sayısal özet çekirdeği çalışır, arayüz aynı kalır.
    """
    vals = [float(x) for x in samples]
    if not vals:
        raise ValueError("ölçüm boş olamaz")
    n = len(vals)
    aktivasyon = sum(abs(v) for v in vals) / n
    mean = sum(vals) / n
    kovaryans = sum((v - mean) ** 2 for v in vals) / n
    return {"aktivasyon": aktivasyon, "kovaryans": kovaryans, "n": n}


def collect_reds(model: str, behavior_scores: dict, measures: dict | None = None) -> list[dict]:
    """Davranış puanlarını kırmızı kayıtlarına toplar (Faz-5 toplama).

    behavior_scores: {tur: puan}. Her puanlı tür bir kırmızı adayıdır;
    ölçüm varsa kayda eklenir. Türler BEHAVIOR_TURS ile sınırlıdır.
    """
    measures = measures or {}
    reds = []
    for tur, puan in behavior_scores.items():
        if tur not in BEHAVIOR_TURS:
            raise ValueError(f"bilinmeyen davranış türü: {tur}")
        reds.append({
            "id": f"red-{model}-{tur}",
            "model": model,
            "tur": tur,
            "taban_puan": float(puan),
            "olcum": measures.get(tur),
            "oney": "kritik",
        })
    return sorted(reds, key=lambda r: r["tur"])


def red_loss(baseline: dict, current: dict) -> dict:
    """Kırmızı kayıp: davranış bazında düşüş + kabul kararı.

    Kabul: max_drop <= RED_LOSS_THRESHOLD. Eksik türler yalnız iki
    tarafta da varsa hesaplanır (kırmızı listesi sabitlenir).
    """
    dususler = {}
    for tur in sorted(set(baseline) & set(current)):
        dusus = float(baseline[tur]) - float(current[tur])
        if dusus > 0:
            dususler[tur] = dusus
    max_drop = max(dususler.values()) if dususler else 0.0
    return {
        "dususler": dususler,
        "max_drop": max_drop,
        "esik": RED_LOSS_THRESHOLD,
        "kabul": max_drop <= RED_LOSS_THRESHOLD,
    }


def marginal_loss_auc(clean_scores: list[float], stego_scores: list[float]) -> float:
    """Marjinal kayıp doğrulaması: temiz vs gizli skor AUC'su.

    AUC = P(temiz > gizli) + 0.5·P(eşit); hedef PAQ_AUC_TARGET (0.98).
    Boş liste ValueError.
    """
    if not clean_scores or not stego_scores:
        raise ValueError("iki skor listesi de dolu olmalı")
    wins = ties = 0.0
    for a in clean_scores:
        for b in stego_scores:
            if a > b:
                wins += 1
            elif a == b:
                ties += 1
    total = len(clean_scores) * len(stego_scores)
    return (wins + 0.5 * ties) / total


def verify_altin_kirmizi(synapse_group: str, locations: dict) -> dict:
    """Altın-kırmızı 4 kopya kuralını doğrular.

    locations: {kaynak: {synapse_group: adet}} — BACKUP_SOURCES'taki her
    kaynakta grup bulunmalı. Eksikler listelenir.
    """
    present = [src for src in BACKUP_SOURCES if synapse_group in locations.get(src, {})]
    eksikler = [src for src in BACKUP_SOURCES if src not in present]
    return {
        "synapse_group": synapse_group,
        "kopie_sayisi": len(present),
        "gerekli": BACKUP_COPY_MIN,
        "ok": len(present) >= BACKUP_COPY_MIN,
        "eksikler": eksikler,
    }


def build_recovery_matrix(reds: list[dict], recipe_map: dict, backup_locations: dict) -> dict:
    """Kurtarma matrisi: her kırmızı davranış için kurtarma planı satırı.

    Her satır: reçete ailesi (recipe_map['modeller']), yedek kopya
    doğrulaması (verify_altin_kirmizi) ve somut kurtarma adımı.
    """
    modeller = recipe_map.get("modeller", {})
    satirlar = []
    for red in reds:
        model = red["model"]
        recete = modeller.get(model)
        yedek = verify_altin_kirmizi(model, backup_locations)
        adim = (
            f"{red['tur']} kırmızısı: {model} gövdesi yedeklerinden geri "
            f"yüklenecek; reçete ({recete or 'TANIMSIZ'}) ile kapılar "
            f"yeniden uygulanır"
        )
        satirlar.append({
            "id": red["id"],
            "tur": red["tur"],
            "model": model,
            "recete_ailesi": recete,
            "recete_ok": recete is not None,
            "yedek_ok": yedek["ok"],
            "yedek_detay": yedek,
            "kurtarma_adimi": adim,
        })
    return {
        "satirlar": satirlar,
        "toplam_kirmizi": len(satirlar),
        "hazir": all(s["recete_ok"] and s["yedek_ok"] for s in satirlar),
    }
