"""Davranış testi kataloğu testleri (TDD — önce RED).

Katalog 4 davranış sınıfını gerçek kamuya açık kaynaklara bağlar:
kod -> SWE-bench Verified, araç -> tau-bench (retail/airline),
güvenlik -> StegoLLM-PAQ + IA gizlilik, dil/karar -> Netmind niyet.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.behavior_tests import (
    BEHAVIOR_CLASSES,
    build_catalog,
    evaluate_suite,
    validation_gate,
)


class TestKatalog(unittest.TestCase):
    def test_dort_sinif(self):
        self.assertEqual(BEHAVIOR_CLASSES, ("kod", "guvenlik", "arac", "dil_karar"))

    def test_katalog_yapisi_ve_kaynaklar(self):
        cat = build_catalog()
        self.assertEqual(set(cat["suites"].keys()), set(BEHAVIOR_CLASSES))
        kod = cat["suites"]["kod"]
        self.assertIn("SWE-bench", kod["kaynak"])
        self.assertIn("tau-bench", cat["suites"]["arac"]["kaynak"])
        self.assertIn("PAQ", cat["suites"]["guvenlik"]["kaynak"])
        for suite in cat["suites"].values():
            self.assertGreater(suite["orneklem"], 0)
            self.assertIn("hedef_davranis", suite)
            self.assertIn("ogretmen_kanit", suite)

    def test_soru_seti_uretimi_soru_iskeleti(self):
        cat = build_catalog()
        sorular = cat["suites"]["arac"]["soru_iskeleti"]
        self.assertTrue(all("niyet" in s or "arac" in s for s in sorular))


class TestDegerlendirme(unittest.TestCase):
    def test_takim_puani_ve_kayit(self):
        cat = build_catalog()
        out = evaluate_suite(cat["suites"]["kod"], successes=8, trials=10)
        self.assertAlmostEqual(out["rate"], 0.8)
        self.assertTrue(out["gecer"])
        self.assertEqual(out["kayit"]["sinif"], "kod")

    def test_dogrulama_kapisi(self):
        cat = build_catalog()
        results = {cls: evaluate_suite(cat["suites"][cls], successes=9, trials=10) for cls in BEHAVIOR_CLASSES}
        self.assertTrue(validation_gate(results))
        results["kod"] = evaluate_suite(cat["suites"]["kod"], successes=5, trials=10)
        self.assertFalse(validation_gate(results))

    def test_kapida_eksik_sinif_gecersiz(self):
        self.assertFalse(validation_gate({"kod": {"gecer": True}}))


if __name__ == "__main__":
    unittest.main()
