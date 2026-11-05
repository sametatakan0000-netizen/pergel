"""Faz-6 Karmaşık->Basit distilasyon testleri (TDD — önce RED).

Kapsam (plan §8):
- davranış başına öğrenci planı (taze en-iyi-sınıf amiral + HQQ öğrenci)
- kovaryanslı örnek ağırlıkları
- 'ağır kayıp yok' doğrulama kapısı
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.behavior_tests import BEHAVIOR_CLASSES, build_catalog
from src.mahoraga.distillation import (
    BEHAVIOR_ADMIRALS,
    build_student_plan,
    covariance_sample_weights,
    student_gate,
)


class TestOgrenciPlani(unittest.TestCase):
    def test_dort_davranis_amiral_ve_veri(self):
        plan = build_student_plan(build_catalog())
        self.assertEqual(set(plan["ogrenciler"].keys()), set(BEHAVIOR_CLASSES))
        for cls, ogrenci in plan["ogrenciler"].items():
            self.assertEqual(ogrenci["amiral"], BEHAVIOR_ADMIRALS[cls])
            self.assertIn("veri_kaynak", ogrenci)
            self.assertIn("orneklem", ogrenci)
            self.assertEqual(ogrenci["quant"]["yontem"], "HQQ")

    def test_agir_kayip_siniri(self):
        plan = build_student_plan(build_catalog())
        for ogrenci in plan["ogrenciler"].values():
            self.assertLessEqual(ogrenci["agir_kayip_siniri"], 0.10)


class TestKovaryansliAgirliklar(unittest.TestCase):
    def test_normalizasyon(self):
        recs = [
            {"key": "a", "n_synapses": 100, "magnitude": 1.0},
            {"key": "b", "n_synapses": 300, "magnitude": 2.0},
        ]
        w = covariance_sample_weights(recs, prior=0.15)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)
        self.assertGreater(w["b"], w["a"])

    def test_bos_girdi(self):
        self.assertEqual(covariance_sample_weights([], prior=0.1), {})


class TestKapi(unittest.TestCase):
    def test_agir_kayip_yok_gecis(self):
        results = {c: {"behavior_rate": 0.85} for c in BEHAVIOR_CLASSES}
        self.assertTrue(student_gate(results))
        results["kod"] = {"behavior_rate": 0.5}
        self.assertFalse(student_gate(results))

    def test_eksik_davranis_engel(self):
        self.assertFalse(student_gate({"kod": {"behavior_rate": 1.0}}))


if __name__ == "__main__":
    unittest.main()
