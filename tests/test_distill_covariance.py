import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.distill_covariance import (
    LLM_COVARIANCE_RANGE,
    covariance_weight,
    select_for_distillation,
    validate_prior,
)


class TestDistillCovariance(unittest.TestCase):
    def test_kod_prior_araligi_planla_sabit(self):
        self.assertEqual(LLM_COVARIANCE_RANGE, (0.01, 0.3))
        self.assertEqual(validate_prior("kod", 0.01), 0.01)
        self.assertEqual(validate_prior("kod", 0.3), 0.3)

    def test_aralik_disi_kod_prior_reddedilir(self):
        with self.assertRaises(ValueError):
            validate_prior("kod", 0.005)
        with self.assertRaises(ValueError):
            validate_prior("kod", 0.31)

    def test_bilinmeyen_uzman_reddedilir(self):
        with self.assertRaises(ValueError):
            validate_prior("oyun", 0.1)

    def test_agirlik_monoton(self):
        r1 = {"n_synapses": 100, "magnitude": 1.0}
        r2 = {"n_synapses": 100, "magnitude": 2.0}
        self.assertGreater(covariance_weight(r2, 0.15), covariance_weight(r1, 0.15))

    def test_secim_butce_icinde_deterministik(self):
        recs = [
            {"key": "a", "n_synapses": 60, "magnitude": 1.0},
            {"key": "b", "n_synapses": 60, "magnitude": 2.0},
            {"key": "c", "n_synapses": 30, "magnitude": 0.5},
        ]
        out = select_for_distillation(recs, budget=90, uzman="kod")
        self.assertTrue(out["within_budget"])
        self.assertLessEqual(out["used_synapses"], 90)
        self.assertEqual(out["chosen_keys"], ["b", "c"])
        again = select_for_distillation(recs, budget=90, uzman="kod")
        self.assertEqual(again["chosen_keys"], out["chosen_keys"])

    def test_butce_pozitif_olmali(self):
        with self.assertRaises(ValueError):
            select_for_distillation([], budget=0)


class TestGercekKovaryans(unittest.TestCase):
    """Gerçek aktivasyon kovaryansı (measure_layers) geldiğinde magnitude
    vekâletinin yerini almalı (shortcut güncelleme tetikleyicisi gerçekleşti)."""

    def test_gercek_kovaryans_stabilite_terimini_belirler(self):
        # w = n * mag * (1 + prior * kov) = 10 * 2 * (1 + 0.1 * 0.5) = 21.0
        # vekâlet (mag) kullanılsaydı: 10 * 2 * (1 + 0.1 * 2) = 24.0
        r = {"n_synapses": 10, "magnitude": 2.0, "kovaryans": 0.5}
        self.assertAlmostEqual(covariance_weight(r, 0.1), 21.0)

    def test_kovaryans_yoksa_vekalet_suruyor(self):
        r = {"n_synapses": 10, "magnitude": 2.0}
        self.assertAlmostEqual(covariance_weight(r, 0.1), 24.0)

    def test_kovaryans_esit_magnitude_ayni_skoru_verir(self):
        base = {"n_synapses": 5, "magnitude": 1.5}
        with_cov = dict(base, kovaryans=1.5)
        self.assertAlmostEqual(
            covariance_weight(base, 0.2), covariance_weight(with_cov, 0.2)
        )

    def test_negatif_kovaryans_reddedilir(self):
        with self.assertRaises(ValueError):
            covariance_weight({"n_synapses": 1, "magnitude": 1.0, "kovaryans": -0.1}, 0.1)

    def test_sonsuz_kovaryans_reddedilir(self):
        for bad in (float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                covariance_weight({"n_synapses": 1, "magnitude": 1.0, "kovaryans": bad}, 0.1)

    def test_olcum_agirlik_siralamasini_degistirir(self):
        # Aynı magnitude, farklı gerçek kovaryans -> sıralama kovaryansa döner.
        recs = [
            {"key": "a", "n_synapses": 10, "magnitude": 1.0, "kovaryans": 0.1},
            {"key": "b", "n_synapses": 10, "magnitude": 1.0, "kovaryans": 0.9},
        ]
        out = select_for_distillation(recs, budget=15, uzman="kod")
        self.assertEqual(out["chosen_keys"], ["b"])


if __name__ == "__main__":
    unittest.main()
