"""Öğretmen davranış skor matrisi — kamuya açık doğrulanmış benchmark kanıtları.

Amaç: Faz-C öğrenci uzman davranışlarını, öğretmenlerin davranış puanlarıyla
eşleştirmek. Kurallar (Karar 2 + davranış kataloğu):
- Her davranış, kendine BAĞLI benchmark ailesinden puanlanır
  (kod -> SWE-bench Verified, arac -> tau ailesi, dil_karar -> Netmind niyet,
  guvenlik -> StegoLLM-PAQ).
- Yalnızca alıntılı (sozlu kanitli) kayıtlar skor girer; canlı ölçüm yoksa
  skor None kalır (plan_only) — puan UYDURULMAZ.
- Aynı model/benchmark için birden çok protokol kaydı varsa ortalama alınır,
  min/max protokol yayılımı korunur. Denge/bonus terimi YOK (Karar 2).
- Davranış skoru = yalnız puanlı modellerin, sinaps (tensör) ağırlıklı ortalaması.
- Kapsam (coverage) = puanlı sinaps / toplam sinaps.
- Davranış skoru / 100 >= esik (0.70) ise öğrenci akışı yüklenir; değilse
  plan_only kalır (router yalnız EN yükseği seçer).
"""
from __future__ import annotations

import json
from pathlib import Path

ESIK_VARSAYILAN = 0.70

# Davranış -> bağlı benchmark ailesi ve kabul edilen benchmark kimlikleri.
# 'tau' ailesinde varyantlar (tau-bench retail/airline, tau3, aa_tau2) protokol
# notuyla ayrı satır tutar; ortalama aile düzeyinde alınır.
BENCHMARK_AILELERI = {
    "kod": {
        "aile": "swe-bench-verified",
        "kabul": {"swe-bench-verified"},
    },
    "arac": {
        "aile": "tau",
        "kabul": {"tau-bench-retail", "tau-bench-airline", "tau3-bench", "aa_tau2"},
    },
    "dil_karar": {
        "aile": "netmind-intent",
        "kabul": {"netmind-intent"},
    },
    "guvenlik": {
        "aile": "stegollm-paq",
        "kabul": {"stegollm-paq"},
    },
}


def load_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def load_kanitlar(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    # İki kanıt biçimi desteklenir: {"kanitlar": [...]} sarmalı veya çıplak liste.
    if isinstance(data, list):
        return data
    return data["kanitlar"]


def _davranis_sinaplari(manifest: dict, davranis: str) -> list[dict]:
    try:
        return manifest["davranislar"][davranis]["sinapslar"]
    except KeyError as exc:
        raise ValueError(f"manifestte davranış yok: {davranis!r}") from exc


def model_satirlari(manifest: dict, kanitlar: list[dict], davranis: str) -> list[dict]:
    """Davranışın her öğretmen modeli için tek satır: sinaps sayısı + puan durumu."""
    sinapslar = _davranis_sinaplari(manifest, davranis)
    kabul = BENCHMARK_AILELERI[davranis]["kabul"]
    kurali_eslesen = [
        k for k in kanitlar
        if k["davranis"] == davranis
        and k["benchmark"] in kabul
        and not k.get("bagli_degil")
    ]
    satirlar: dict[str, dict] = {}
    for s in sinapslar:
        satir = satirlar.setdefault(
            s["model"],
            {
                "model": s["model"],
                "aile": s["aile"],
                "sinaps_sayisi": 0,
                "toplam_sinaps_adedi": 0,
                "skor_ortalama": None,
                "skor_min": None,
                "skor_max": None,
                "kanit_sayisi": 0,
                "protokoller": [],
            },
        )
        satir["sinaps_sayisi"] += 1
        satir["toplam_sinaps_adedi"] += s.get("n_synapses") or 0
    for k in kurali_eslesen:
        satir = satirlar.get(k["model"])
        if satir is None:
            continue  # sinapssız model: matris dışında notlanır (aşağıda)
        satir["kanit_sayisi"] += 1
        satir["protokoller"].append(k.get("protokol", ""))
        skorlar = [kk["skor"] for kk in kurali_eslesen if kk["model"] == k["model"]]
        satir["skor_ortalama"] = sum(skorlar) / len(skorlar)
        satir["skor_min"] = min(skorlar)
        satir["skor_max"] = max(skorlar)
    return sorted(satirlar.values(), key=lambda r: r["model"])


def davranis_skor_matrisi(
    manifest: dict,
    kanitlar: list[dict],
    esik: float = ESIK_VARSAYILAN,
) -> dict:
    """Tüm davranışlar için deterministik skor matrisi."""
    davranislar: dict[str, dict] = {}
    bagdisiz = 0
    sinapsiz_kanitlar: list[str] = []
    for davranis in sorted(manifest["davranislar"]):
        satirlar = model_satirlari(manifest, kanitlar, davranis)
        toplam_sinaps = sum(r["sinaps_sayisi"] for r in satirlar)
        puanli = [r for r in satirlar if r["skor_ortalama"] is not None]
        puanli_sinaps = sum(r["sinaps_sayisi"] for r in puanli)
        if puanli:
            agirlikli = sum(r["skor_ortalama"] * r["sinaps_sayisi"] for r in puanli)
            davranis_skoru = agirlikli / puanli_sinaps
        else:
            davranis_skoru = None
        plan_only = davranis_skoru is None
        yukle = (not plan_only) and (davranis_skoru / 100.0) >= esik
        kabul = BENCHMARK_AILELERI[davranis]["kabul"]
        sinaps_modelleri = {r["model"] for r in satirlar}
        sinapsiz = sorted({
            k["model"] for k in kanitlar
            if k["davranis"] == davranis and k["benchmark"] in kabul
            and not k.get("bagli_degil") and k["model"] not in sinaps_modelleri
        })
        sinapsiz_kanitlar.extend(sinapsiz)
        davranislar[davranis] = {
            "bagli_benchmark": BENCHMARK_AILELERI[davranis]["aile"],
            "modeller": satirlar,
            "davranis_skoru": davranis_skoru,
            "kapsam": (puanli_sinaps / toplam_sinaps) if toplam_sinaps else 0.0,
            "plan_only": plan_only,
            "yukle": yukle,
            "sinapsiz_kanitli_modeller": sinapsiz,
        }
    for k in kanitlar:
        davranis = k.get("davranis")
        if k.get("bagli_degil") or (
            davranis in BENCHMARK_AILELERI
            and k.get("benchmark") not in BENCHMARK_AILELERI[davranis]["kabul"]
        ):
            bagdisiz += 1
    return {
        "esik": esik,
        "kural": "Karar 2: en yuksek dogrulanmis skor kazanir; denge bonusu yok; olcum yoksa skor None (plan_only)",
        "davranislar": davranislar,
        "bagdisiz_kanit_sayisi": bagdisiz,
        "sinapsiz_kanitli_modeller": sorted(set(sinapsiz_kanitlar)),
    }


def markdown_tablo(matris: dict) -> str:
    """Matrisi markdown tablo dizisi olarak üretir (rapor gömme için)."""
    satirlar = [
        "| davranış | model | sinaps | skor (ort) | min–max | kapsam | durum |",
        "|---|---|---|---|---|---|---|",
    ]
    for davranis, d in matris["davranislar"].items():
        for r in d["modeller"]:
            sk = "—" if r["skor_ortalama"] is None else f"{r['skor_ortalama']:.1f}"
            yay = "—" if r["skor_min"] is None else f"{r['skor_min']:.1f}–{r['skor_max']:.1f}"
            durum = "puansız" if r["skor_ortalama"] is None else (
                "yükle" if d["yukle"] else "eşik altı"
            )
            satirlar.append(
                f"| {davranis} | {r['model']} | {r['sinaps_sayisi']} | {sk} | {yay} | "
                f"{d['kapsam']:.2f} | {durum} |"
            )
        s = "—" if d["davranis_skoru"] is None else f"{d['davranis_skoru']:.1f}"
        satirlar.append(
            f"| **{davranis} (sınıf)** | — | — | **{s}** | — | {d['kapsam']:.2f} | "
            f"{'plan_only' if d['plan_only'] else ('yükle' if d['yukle'] else 'eşik altı')} |"
        )
    return "\n".join(satirlar)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Davranış skor matrisi üretir")
    ap.add_argument("--manifest", default="/home/pc/mahoraga_montaj_manifest.json")
    ap.add_argument("--kanitlar", default="/home/pc/mahoraga_davranis_kanitlari.json")
    ap.add_argument("--out-json", default="/home/pc/mahoraga_davranis_skor_matrisi.json")
    ap.add_argument("--out-md", default="/home/pc/mahoraga_davranis_skor_matrisi.md")
    args = ap.parse_args()
    m = davranis_skor_matrisi(load_manifest(args.manifest), load_kanitlar(args.kanitlar))
    Path(args.out_json).write_text(json.dumps(m, ensure_ascii=False, indent=2))
    Path(args.out_md).write_text(markdown_tablo(m) + "\n")
    print(f"matris yazildi: {args.out_json} / {args.out_md}")
    for d, v in m["davranislar"].items():
        s = "None" if v["davranis_skoru"] is None else f"{v['davranis_skoru']:.1f}"
        print(f"  {d}: skor={s} kapsam={v['kapsam']:.2f} "
              f"plan_only={v['plan_only']} yukle={v['yukle']}")
