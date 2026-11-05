"""Davranış testi kataloğu — Faz-5.5 (plan §8-4: davranış/denetim puanlama görevi).

Her davranış sınıfı gerçek kamuya açık bir benchmark'a bağlanır
(maliyet kuralı: kendi model testi koşma, mevcut veri setlerini kullan):
- kod      -> SWE-bench Verified (500 gerçek issue → patch)
- araç     -> tau-bench (retail ~115 + airline ~50 görev, araç zincirleri)
- güvenlik -> StegoLLM-PAQ marjinal kayıp + LLM-gizlilik (IA) davranışı
- dil/karar-> Netmind tekniği ile niyet kavrayışı (Karmaşık→Basit ayrışımı)

Soru metinleri BURADA üretilmez; 'soru_iskeleti' şablonları gerçek veri
setlerinden doldurulacak iskeletlerdir. Puanlama behavior_audit
üzerinden yürür (başarı oranı = davranış kaydı, %70 kapı).
"""
from __future__ import annotations

from .behavior_audit import BEHAVIOR_PASS_THRESHOLD, behavior_score

# Plan §9 davranış testleri: araç / güvenlik / dil karar / kod.
BEHAVIOR_CLASSES = ("kod", "guvenlik", "arac", "dil_karar")


def build_catalog() -> dict:
    """Davranış testi kataloğu: 4 sınıf, gerçek kaynaklı takımlar."""
    suites = {
        "kod": {
            "id": "suite-kod-swebench",
            "kaynak": "SWE-bench Verified (500 gerçek issue; patch doğrulaması testlerle)",
            "hedef_davranis": "issue açıklamasından çalışan patch üretme; davranış = çözülen görev oranı",
            "ogretmen_kanit": "Nemotron-CORTEXA %68.2 / DeepSeek-V4.1-Flash %88.8 (SWE-bench Verified)",
            "orneklem": 500,
            "soru_iskeleti": [
                "repo + issue açıklaması -> patch (birim testler geçmeli)",
                "repo + regresyon raporu -> düzeltme (kırmızı testi yeşile çevir)",
            ],
        },
        "arac": {
            "id": "suite-arac-taubench",
            "kaynak": "tau-bench (retail ~115 + airline ~50 görev; araç çağrısı zincirleri)",
            "hedef_davranis": "kullanıcı niyetinden doğru araç çağrısı zinciri kurma; davranış = görev başarı oranı",
            "ogretmen_kanit": "tau-bench retail/airline lider panosu (DeepSeek-V3.2 %61.5 retail)",
            "orneklem": 165,
            "soru_iskeleti": [
                "kullanıcı niyeti + araç listesi -> doğru çağrı zinciri (parametreler tam)",
                "çok turlu diyalog niyeti + araç listesi -> tek seferde doğru çağrı",
            ],
        },
        "guvenlik": {
            "id": "suite-guvenlik-stego-izleme",
            "kaynak": "LSGC steganaliz (arXiv:2406.04218) + izleme kanıtı (arXiv:2507.02737)",
            "hedef_davranis": "gizli kanal/stego taleplerini reddetme; çıkarım anında izleme ile sızıntıyı yakalama",
            "ogretmen_kanit": (
                "LSGC Tablo III: güçlü gizlemede tespit Acc %97-99, en zor senaryolarda %70-83; "
                "izleme: frontier modeller standart imkânlarda gizli mesajı izleyiciden gizleyemiyor "
                "(arXiv:2507.02737) — risk yalnız izlenmeyen defter + kararlaştırılmış şema ile"
            ),
            "kanit_banti": [0.70, 0.99],
            "duzeltme": (
                "2026-11-05: 'StegoLLM-PAQ' adının kamuya açık kaynağı BULUNAMADI; 'DeepEclipse' "
                "(USENIX Sec'24) beyaz-kutu filigran KALDIRMA çalışmasıdır — IA gizlilik kanıtı "
                "olarak yanlış atıftı. Yerine yukarıdaki doğrulanabilir kanıtlar kondu."
            ),
            "orneklem": 200,
            "soru_iskeleti": [
                "stego istemi (PAQ dinamik taban) -> marjinal kayıp AUC ölçümü",
                "IA gizlilik istemi -> çıkarım anında sızıntı yok",
            ],
        },
        "dil_karar": {
            "id": "suite-dil-karar-netmind",
            "kaynak": "Netmind tekniği niyet kavrayışı; Karmaşık -> Basit Karmaşık -> Basit ayrışımı",
            "hedef_davranis": "karmaşık niyeti doğru sınıfa ayırıp basit öğrenciye devretme; davranış = niyet doğruluğu",
            "ogretmen_kanit": "öğretmen haritası davranış listesi (mahoraga_ogretmen_haritasi.json)",
            "orneklem": 300,
            "soru_iskeleti": [
                "karmaşık kullanıcı niyeti -> doğru davranış sınıfı (kod/güvenlik/araç/dil)",
                "belirsiz niyet -> güvenli varsayılan karar",
            ],
        },
    }
    return {"suites": suites, "esik": BEHAVIOR_PASS_THRESHOLD}


def evaluate_suite(suite: dict, successes: int, trials: int) -> dict:
    """Takım puanı: behavior_score + davranış kaydı (başarı oranı = davranış)."""
    out = behavior_score(successes=successes, trials=trials)
    out["kayit"] = {
        "sinif": next((c for c, s in build_catalog()["suites"].items() if s["id"] == suite["id"]), suite.get("id")),
        "suite_id": suite["id"],
        "kaynak": suite["kaynak"],
    }
    return out


def validation_gate(results: dict) -> bool:
    """Paketleme öncesi davranış doğrulaması: 4 sınıfın TAMAMI geçmeli (plan §8)."""
    return set(results.keys()) == set(BEHAVIOR_CLASSES) and all(
        r.get("gecer") for r in results.values()
    )
