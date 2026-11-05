"""Faz-6 sinaps birleştirme (merge-first) testleri.

Stil kuralı: gradyan eğitimi YOK; sinapslar kovaryanslı ağırlıklarla
doğrusal birleştirilir. Cross-arch -> stitch (akış bağlama).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.behavior_tests import BEHAVIOR_CLASSES, build_catalog
from src.mahoraga.distillation import (
    BEHAVIOR_ADMIRALS,
    merge_coefficients,
    merge_plan,
    post_merge_gate,
    strateji_sec,
)


class TestBirlestirmePlani(unittest.TestCase):
    def test_dort_davranis_amiral_ve_strateji(self):
        plan = merge_plan(build_catalog())
        self.assertEqual(set(plan["birlestirmeler"].keys()), set(BEHAVIOR_CLASSES))
        for cls, p in plan["birlestirmeler"].items():
            self.assertEqual(p["amiral"], BEHAVIOR_ADMIRALS[cls])
            self.assertIn(p["strateji"], ("direct_merge", "stitch"))
            self.assertIn("veri_kaynak", p)
            self.assertEqual(p["quant"]["yontem"], "HQQ")

    def test_ayni_mimari_direct_merge(self):
        mimari = {"kod": ("gpt-oss", "gpt-oss"), "guvenlik": ("a", "b"),
                  "arac": ("a", "b"), "dil_karar": ("a", "b")}
        plan = merge_plan(build_catalog(), mimari=mimari)
        self.assertEqual(plan["birlestirmeler"]["kod"]["strateji"], "direct_merge")
        self.assertEqual(plan["birlestirmeler"]["arac"]["strateji"], "stitch")

    def test_strateji_sec(self):
        self.assertEqual(strateji_sec("x", "x"), "direct_merge")
        self.assertEqual(strateji_sec("x", "y"), "stitch")

    def test_gradyan_egitim_dil_kullanilmaz(self):
        plan = merge_plan(build_catalog())
        kapi = str(plan).lower()
        self.assertNotIn("backprop", kapi)
        self.assertNotIn("optimizer", kapi)


class TestKovaryansliBirlestirmeKatsayilari(unittest.TestCase):
    def test_normalizasyon(self):
        sets = [
            {"key": "a", "n_synapses": 100, "magnitude": 1.0},
            {"key": "b", "n_synapses": 300, "magnitude": 2.0},
        ]
        w = merge_coefficients(sets, prior=0.15)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)
        self.assertGreater(w["b"], w["a"])

    def test_bos_girdi(self):
        self.assertEqual(merge_coefficients([], prior=0.1), {})


class TestKapi(unittest.TestCase):
    def test_agir_kayip_yok_gecis(self):
        results = {c: {"behavior_rate": 0.85} for c in BEHAVIOR_CLASSES}
        self.assertTrue(post_merge_gate(results))
        results["kod"] = {"behavior_rate": 0.5}
        self.assertFalse(post_merge_gate(results))

    def test_eksik_davranis_engel(self):
        self.assertFalse(post_merge_gate({"kod": {"behavior_rate": 1.0}}))


if __name__ == "__main__":
    unittest.main()
