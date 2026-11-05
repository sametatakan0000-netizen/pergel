"""Faz-C montaj manifestı testleri (RED-first).

Kural tabanı:
- Golden-Red: her kazanan sinaps 4 kopyada hash ile doğrulanmalı.
- Cross-arch merge YOK: aile içi -> direct_merge (Σw·v), aileler arası -> distillation.
- Mevki/model/key/hash çözümü gerçek manifest ve sonuç dosyalarından gelir.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, "/home/pc/.hermes/sandboxes/docker/default/home/ai_browser_farm")

from src.mahoraga.montaj_manifest import (  # noqa: E402
    KOPYA_KOKLERI,
    aile_bul,
    manifest_yukle,
    montaj_manifesti,
)

SONUC = "/home/pc/mahoraga_kombinasyon_sonuc.json"


class TestAileEsleme(unittest.TestCase):
    def test_bilinen_aileler(self):
        self.assertEqual(aile_bul("NousResearch/Hermes-3-Llama-3.1-70B"), "llama")
        self.assertEqual(aile_bul("nvidia/Llama-3.3-Nemotron-Super-49B-v1"), "llama")
        self.assertEqual(aile_bul("mistralai/Codestral-22B-v0.1"), "mistral")
        self.assertEqual(aile_bul("NeverSleep/Noromaid-20B-v0.1.1"), "mistral")
        self.assertEqual(aile_bul("Qwen/Qwen3-235B-A22B"), "qwen")
        self.assertEqual(aile_bul("deepseek-ai/DeepSeek-V4.1-Flash"), "deepseek")
        self.assertEqual(aile_bul("microsoft/Phi-4"), "phi")
        self.assertEqual(aile_bul("01-ai/Yi-1.5-34B-Chat"), "yi")

    def test_bolt_llama_degildir(self):
        # Nemotron-3.5 Bolt kendi mimarisidir; llama ile birleştirilemez.
        self.assertEqual(
            aile_bul("nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-BF16"), "nemotron")
        self.assertNotEqual(
            aile_bul("nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-BF16"),
            aile_bul("NousResearch/Hermes-3-Llama-3.1-70B"))

    def test_bilinmeyen_acik_verilir(self):
        with self.assertRaises(ValueError):
            aile_bul("bilinmeyen/model-1B")


class TestKaynakCozumuVeAltinKirmizi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.indeks = manifest_yukle(KOPYA_KOKLERI)
        with open(SONUC) as f:
            cls.sonuc = json.load(f)

    def test_tum_me_vkiler_hashle_cozuluyor(self):
        bulunan = 0
        for dav, v in self.sonuc["davranislar"].items():
            for cift in v["simulasyon"]["en_iyi_kombinasyon"]:
                key, model = cift.split(" @ ")
                kayit = self.indeks.kayit(model, key)
                self.assertIsNotNone(kayit, f"{dav}: {model}::{key} çözülemedi")
                bulunan += 1
        self.assertGreater(bulunan, 0)

    def test_altin_kirmizi_dort_kopya(self):
        # Golden-Red: sinaps ASLA silinmez; en az 4 kopya aynı kaydı taşımalı.
        eksik = []
        for dav, v in self.sonuc["davranislar"].items():
            for cift in v["simulasyon"]["en_iyi_kombinasyon"]:
                key, model = cift.split(" @ ")
                kopya = self.indeks.kopya_sayisi(model, key)
                if kopya < 4:
                    eksik.append((dav, model, key, kopya))
        self.assertEqual(eksik, [], f"4 kopya altı sinaps var: {eksik[:5]}")

    def test_kopyalar_hash_birbirini_tutuyor(self):
        # Farklı kopyalardaki GERÇEK hash'ler çelişemez (bütünlük).
        for dav, v in self.sonuc["davranislar"].items():
            for cift in v["simulasyon"]["en_iyi_kombinasyon"]:
                key, model = cift.split(" @ ")
                hashler = self.indeks.kopya_hashleri(model, key)
                if not hashler:
                    continue  # hash boşluğu: sessizlik testiyle ayrıca yakalanır
                self.assertEqual(len(set(hashler)), 1,
                                 f"{model}::{key} kopyaları çelişkili: {hashler}")


class TestRotaKurali(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = montaj_manifesti(SONUC, KOPYA_KOKLERI)

    def test_uretilen_manifest_dolu(self):
        self.assertEqual(set(self.manifest["davranislar"]),
                         {"kod", "arac", "dil_karar", "guvenlik"})
        for dav, v in self.manifest["davranislar"].items():
            self.assertGreater(len(v["sinapslar"]), 0, dav)

    def test_aile_gruplari_icinde_direct_merge(self):
        # Aile içi her grup direct_merge; gruplar SAFTIR (aile saf olmalı).
        for dav, v in self.manifest["davranislar"].items():
            for aile, grup in v["aile_gruplari"].items():
                self.assertEqual(grup["rota"], "direct_merge", dav)
                for s in grup["sinapslar"]:
                    self.assertEqual(s["aile"], aile,
                                     f"{dav}: {aile} grubuna yabancı sinaps {s['model']}")

    def test_cross_arch_asla_direct_merge_degil(self):
        # Birden çok aile varsa birleştirme rotası distillation olmalı.
        for dav, v in self.manifest["davranislar"].items():
            aileler = list(v["aile_gruplari"])
            if len(aileler) > 1:
                self.assertEqual(v["rota"], "distillation",
                                 f"{dav}: cross-arch birleştirme direct_merge olamaz")
            else:
                self.assertEqual(v["rota"], "direct_merge")

    def test_hash_boslugu_sessiz_degil(self):
        # Golden-Red: hash'siz sinaps manifestte AÇIKÇA işaretlenir, kaybolmaz.
        uyari = self.manifest["altin_kirmizi_uyari"]["hash_eksik_sinapslar"]
        beklenen = sorted(
            f"{dav}::{s['model']}::{s['key']}"
            for dav, v in self.manifest["davranislar"].items()
            for s in v["sinapslar"] if s["hash_durumu"] == "eksik")
        self.assertEqual(sorted(uyari), beklenen)
        for dav, v in self.manifest["davranislar"].items():
            for s in v["sinapslar"]:
                self.assertIn(s["hash_durumu"], ("dogrulandi", "eksik"))
                if s["hash_durumu"] == "eksik":
                    self.assertEqual(s["kopya_sayisi"], 4,
                                     "hash'siz kayıt da 4 kopyada bulunmalı")


if __name__ == "__main__":
    unittest.main()
