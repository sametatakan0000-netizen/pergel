"""Davranış skor matrisi (öğretmen ölçüm turu) testleri.

Kurallar:
- Karar 2: yalnız en yüksek doğrulanmış skor; denge bonusu YOK.
- Puanlayıcı yoksa skor None (plan_only); skor uydurulmaz.
- Eşik: davranış skoru / 100 >= 0.70 ise öğrenci akışı yüklenir.
- Bağlı benchmark dışı kanıtlar (ör. LiveCodeBench) skoru etkilemez.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mahoraga.behavior_score_matrix import (
    BENCHMARK_AILELERI,
    davranis_skor_matrisi,
    model_satirlari,
)

MANIFEST = Path("/home/pc/mahoraga_montaj_manifest.json")
KANITLAR = Path("/home/pc/mahoraga_davranis_kanitlari.json")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


@pytest.fixture(scope="module")
def kanitlar() -> list[dict]:
    return json.loads(KANITLAR.read_text())["kanitlar"]


def test_bagli_benchmark_eslemesi():
    assert BENCHMARK_AILELERI["kod"]["aile"] == "swe-bench-verified"
    assert BENCHMARK_AILELERI["arac"]["aile"] == "tau"
    assert BENCHMARK_AILELERI["dil_karar"]["aile"] == "netmind-intent"
    assert BENCHMARK_AILELERI["guvenlik"]["aile"] == "stegollm-paq"


def test_kod_matrisi_dogrulanmis_skorlar(manifest, kanitlar):
    m = davranis_skor_matrisi(manifest, kanitlar)
    kod = m["davranislar"]["kod"]
    modeller = {r["model"]: r for r in kod["modeller"]}
    # DeepSeek-V4.1-Flash: 79.4 (spec-kitty) + 66.0 (armes) -> ortalama 72.7
    ds = modeller["deepseek-ai/DeepSeek-V4.1-Flash"]
    assert ds["skor_ortalama"] == pytest.approx(72.7)
    assert ds["skor_min"] == pytest.approx(66.0)
    assert ds["skor_max"] == pytest.approx(79.4)
    # Puanlayıcı olmayanlar None kalır (skor uydurulmaz)
    assert modeller["mistralai/Codestral-22B-v0.1"]["skor_ortalama"] is None
    assert modeller["Qwen/Qwen3-235B-A22B"]["skor_ortalama"] is None
    # Sınıf skoru: yalnız puanlı modeller, sinaps ağırlıklı
    assert kod["davranis_skoru"] == pytest.approx(72.7)
    assert kod["plan_only"] is False
    assert kod["yukle"] is True  # 72.7 / 100 >= 0.70
    assert kod["kapsam"] < 1.0  # puanlı sinaps / toplam sinaps


def test_arac_matrisi_esik_alti(manifest, kanitlar):
    m = davranis_skor_matrisi(manifest, kanitlar)
    arac = m["davranislar"]["arac"]
    modeller = {r["model"]: r for r in arac["modeller"]}
    assert modeller["nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-BF16"]["skor_ortalama"] == pytest.approx(17.0)
    assert arac["davranis_skoru"] == pytest.approx(17.0)
    assert arac["yukle"] is False  # 17/100 < 0.70


def test_puani_olmayan_davranislar_plan_only(manifest, kanitlar):
    m = davranis_skor_matrisi(manifest, kanitlar)
    assert m["davranislar"]["dil_karar"]["plan_only"] is True
    assert m["davranislar"]["dil_karar"]["yukle"] is False
    assert m["davranislar"]["guvenlik"]["plan_only"] is True
    assert m["davranislar"]["guvenlik"]["yukle"] is False


def test_sinaps_agirikli_davranis_skoru():
    # Sentez manifest: A=2 sinaps @90, B=1 sinaps @50 -> (2*90+1*50)/3 = 76.67
    sentez_manifest = {
        "davranislar": {
            "kod": {
                "sinapslar": [
                    {"mevki": "m1", "model": "a/m1", "aile": "x", "key": "k1", "n_synapses": 10},
                    {"mevki": "m2", "model": "a/m1", "aile": "x", "key": "k2", "n_synapses": 10},
                    {"mevki": "m3", "model": "b/m2", "aile": "y", "key": "k3", "n_synapses": 10},
                ],
            }
        }
    }
    sentez_kanit = [
        {"model": "a/m1", "davranis": "kod", "benchmark": "swe-bench-verified", "skor": 90.0},
        {"model": "b/m2", "davranis": "kod", "benchmark": "swe-bench-verified", "skor": 50.0},
    ]
    m = davranis_skor_matrisi(sentez_manifest, sentez_kanit)
    kod = m["davranislar"]["kod"]
    assert kod["davranis_skoru"] == pytest.approx(76.666666, rel=1e-4)
    assert kod["kapsam"] == pytest.approx(1.0)


def test_coklu_kanit_protokol_yayilimi_korunur():
    # Aynı model/benchmark, iki protokol: ortalama alınır, yayılım kaydedilir (denge bonusu yok)
    sentez_manifest = {
        "davranislar": {
            "kod": {"sinapslar": [{"mevki": "m1", "model": "a/m1", "aile": "x", "key": "k1", "n_synapses": 1}]}
        }
    }
    sentez_kanit = [
        {"model": "a/m1", "davranis": "kod", "benchmark": "swe-bench-verified", "skor": 66.0, "protokol": "base"},
        {"model": "a/m1", "davranis": "kod", "benchmark": "swe-bench-verified", "skor": 79.4, "protokol": "agent"},
    ]
    m = davranis_skor_matrisi(sentez_manifest, sentez_kanit)
    satir = m["davranislar"]["kod"]["modeller"][0]
    assert satir["skor_ortalama"] == pytest.approx(72.7)
    assert (satir["skor_min"], satir["skor_max"]) == (66.0, 79.4)


def test_bagdisiz_kanit_skoru_etkilemez():
    # LiveCodeBench kanıtı kod davranışının bağlı benchmark'ı değildir; skora girmez
    sentez_manifest = {
        "davranislar": {
            "kod": {"sinapslar": [{"mevki": "m1", "model": "a/m1", "aile": "x", "key": "k1", "n_synapses": 1}]}
        }
    }
    sentez_kanit = [
        {"model": "a/m1", "davranis": "kod", "benchmark": "livecodebench", "skor": 99.0},
    ]
    m = davranis_skor_matrisi(sentez_manifest, sentez_kanit)
    satir = m["davranislar"]["kod"]["modeller"][0]
    assert satir["skor_ortalama"] is None
    assert m["davranislar"]["kod"]["plan_only"] is True
    assert m["bagdisiz_kanit_sayisi"] >= 1


def test_sinapsi_olmayan_kanit_notlanir():
    # DeepSeek'in tau-bench kanıtı var ama 'arac' davranışında sinapsı yok -> skora girmez, notlanır
    sentez_manifest = {
        "davranislar": {
            "arac": {"sinapslar": [{"mevki": "m1", "model": "n/n1", "aile": "x", "key": "k1", "n_synapses": 1}]}
        }
    }
    sentez_kanit = [
        {"model": "d/d1", "davranis": "arac", "benchmark": "tau-bench-retail", "skor": 80.0},
        {"model": "n/n1", "davranis": "arac", "benchmark": "tau3-bench", "skor": 17.0},
    ]
    m = davranis_skor_matrisi(sentez_manifest, sentez_kanit)
    arac = m["davranislar"]["arac"]
    assert [r["model"] for r in arac["modeller"]] == ["n/n1"]
    assert arac["sinapsiz_kanitli_modeller"] == ["d/d1"]


def test_model_satirlari_yardimcisi(manifest, kanitlar):
    satirlar = model_satirlari(manifest, kanitlar, "kod")
    assert {r["model"] for r in satirlar} == {
        "deepseek-ai/DeepSeek-V4.1-Flash",
        "mistralai/Codestral-22B-v0.1",
        "Qwen/Qwen3-235B-A22B",
    }
