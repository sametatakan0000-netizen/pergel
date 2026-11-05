#!/usr/bin/env python3
"""Kombinasyon arama motorunu GERÇEK envantere bağlar.

1. 27 modelin sinaps manifestoları (/home/pc/mahoraga_synapses/*_synapses.json)
2. Öğretmen haritası davranış skorları (birincil 0.9, listeli 0.7, kanıt
   override, taban 0.3; guvenlik kanıtsız -> düz 0.5 — dürüst boşluk)
3. Fonksiyonel kümeleme -> her kümeden "en" -> kombinasyon simülasyonu
Çıktı: /home/pc/mahoraga_kombinasyon_sonuc.json
"""
from __future__ import annotations

import glob
import json
import sys

sys.path.insert(0, "/home/pc/.hermes/sandboxes/docker/default/home/ai_browser_farm")
from src.mahoraga.combination_search import (  # noqa: E402
    combination_score, functional_clusters, select_best, simulate_combinations,
)

SYNAPSE_DIR = "/home/pc/mahoraga_synapses"
OUT = "/home/pc/mahoraga_kombinasyon_sonuc.json"
PRIOR = 0.15

# Davranış -> öğretmen haritası sınıfı (dil_karar iki sınıfın ortalaması)
DAVRANIS_ESLEME = {
    "kod": ["kod"],
    "arac": ["arac_agentic"],
    "dil_karar": ["dil_uslup", "karar_router"],
    "guvenlik": [],  # öğretmen haritasında davranış kanıtı YOK -> düz 0.5
}

# Kanıt override'ları (agentic_kanit.sonuclar — 05.11 doğrulanmış sayılar)
KANIT_SKORLARI = {
    "kod": {
        "deepseek-ai/deepseek-v4.1-flash": 0.888,   # vals.ai SWE-bench Verified
    },
}


def model_skorlarini_uret(ogretmen_haritasi: dict, modeller: list[str]) -> dict:
    """model -> {davranis: oran} — öğretmen haritası + kanıt override."""
    uzman = ogretmen_haritasi["uzman_haritasi"]
    skorlar = {m: {} for m in modeller}
    norm = {m.lower(): m for m in modeller}
    for dav, siniflar in DAVRANIS_ESLEME.items():
        for m in modeller:
            s = 0.5 if dav == "guvenlik" else 0.3  # taban / dürüst boşluk
            for sinif in siniflar:
                e = uzman.get(sinif, {})
                birincil = (e.get("birincil") or "").lower()
                liste = [x.lower() for x in e.get("ogretmenler", [])]
                if m.lower() == birincil:
                    s = max(s, 0.9)
                elif m.lower() in liste:
                    s = max(s, 0.7)
            for mm, oran in KANIT_SKORLARI.get(dav, {}).items():
                if m.lower() == mm:
                    s = max(s, oran)
            skorlar[m][dav] = round(s, 3)
    return skorlar


def main() -> int:
    tm = json.load(open("/home/pc/mahoraga_ogretmen_haritasi.json"))
    rm = json.load(open("/home/pc/mahoraga_recipe_map.json"))
    modeller_map = rm.get("modeller", rm)

    # 1. Envanter kayıtları
    records, key_to_rec = [], {}
    model_ids = set()
    for path in sorted(glob.glob(f"{SYNAPSE_DIR}/*_synapses.json")):
        d = json.load(open(path))
        model = d["model"]
        model_ids.add(model)
        aile = None
        for k, v in modeller_map.items():
            if k.lower() == model.lower() or k.lower().endswith(model.split("/")[-1].lower()):
                aile = v.get("aile") if isinstance(v, dict) else str(v).split(" (")[0]
                break
        aile = aile or model.split("/")[0]
        for t in d.get("tensors", []):
            rec = {"key": t["key"], "model": model, "aile": aile,
                   "n_synapses": t["n_synapses"], "magnitude": t.get("magnitude", 1.0)}
            records.append(rec)
            key_to_rec[(model, t["key"])] = rec
    print(f"envanter: {len(model_ids)} model, {len(records)} sinaps kaydı")

    # 2. Davranış skorları
    skorlar = model_skorlarini_uret(tm, sorted(model_ids))

    # 3. Davranış başına kümeleme -> "en" -> simülasyon
    sonuc = {"olusturma": "2026-11-05", "onbellek": f"{len(records)} sinaps kaydı",
             "model_skorlari": skorlar, "davranislar": {}}
    for dav in ("kod", "arac", "dil_karar", "guvenlik"):
        clusters = functional_clusters(records)
        best = select_best(clusters, dav, skorlar, prior=PRIOR)
        enler = {rol: v["en"] for rol, v in best.items()}
        # oracle: anahtar -> kayıt dönüşümü (aynı key farklı modellerde olabilir;
        # 'en' seçiminde model bilgisi korunur)
        anahtar_kayit = {}
        for rol, v in best.items():
            for kk, ss in v["skorlar"].items():
                pass
        # kombinasyon adayları: küme başına "en" kaydı
        en_kayitlar = []
        for rol, v in best.items():
            for r in records:
                if r["key"] == v["en"] and r["model"] in model_ids:
                    # 'en' key'i birden çok modelde geçebilir; en yüksek skorluyu al
                    adaylar = [x for x in records if x["key"] == v["en"]]
                    en_kayitlar.append(max(adaylar, key=lambda x: skorlar[x["model"]][dav]))
                    break
        combo_key_index = {f"{r['model']}::{r['key']}": r for r in en_kayitlar}
        keys = list(combo_key_index.keys())
        oracle = lambda combo: combination_score(
            [combo_key_index[k] for k in combo], skorlar, dav)
        sim = simulate_combinations(keys, oracle, max_k=4, budget=10000)
        sonuc["davranislar"][dav] = {
            "kume_sayisi": len(best),
            "en_secimler": {rol: {"en": v["en"], "skor": round(v["skorlar"][v["en"]], 4)}
                            for rol, v in best.items()},
            "simulasyon": {
                "en_iyi_kombinasyon": [k.split("::")[1] + " @ " + k.split("::")[0] for k in sim["en_iyi"]],
                "skor": round(sim["skor"], 4) if sim["skor"] is not None else None,
                "simulasyon_sayisi": sim["simulasyon_sayisi"],
                "tam_exhaustive": sim["tam_exhaustive"],
            },
            "en_yuksek_model_skorlari": sorted(
                ((m, s[dav]) for m, s in skorlar.items()), key=lambda x: -x[1])[:5],
        }
        print(f"[{dav}] kümeler={len(best)} simülasyon={sim['simulasyon_sayisi']} "
              f"en_iyi_skor={sonuc['davranislar'][dav]['simulasyon']['skor']}")

    json.dump(sonuc, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("sonuç:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
