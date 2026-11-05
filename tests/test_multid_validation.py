"""Multi-D doğrulama matrisi testleri (TDD — önce RED).

Kapsam (plan §8 Faz-5, Multi-D):
- L1-norm maskesi
- Covariance-Weighted SVD bileşen seçimi
- çok-yönlü doğrulama matrisi (kod/güvenlik/araç/dil yönleri x ölçüm/karar)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.multid_validation import (
    DIRECTIONS,
    covariance_weighted_svd,
    l1_mask,
    validation_matrix,
)


class TestL1Mask(unittest.TestCase):
    def test_esik_alti_eleme(self):
        recs = [
            {"key": "a", "n_synapses": 100, "magnitude": 2.0},
            {"key": "b", "n_synapses": 100, "magnitude": 0.01},
        ]
        out = l1_mask(recs, threshold=100.0)
        self.assertEqual(out["kept_keys"], ["a"])
        self.assertEqual(out["kept"], 1)
        self.assertEqual(out["total"], 2)

    def test_l1_tanimi(self):
        # l1 = n_synapses * |magnitude|
        recs = [{"key": "x", "n_synapses": 10, "magnitude": 3.0}]
        out = l1_mask(recs, threshold=30.0)
        self.assertEqual(out["kept_keys"], ["x"])


class TestCovarianceWeightedSvd(unittest.TestCase):
    def test_keep_ratio_secimi(self):
        recs = [
            {"key": "a", "n_synapses": 10, "magnitude": 1.0},
            {"key": "b", "n_synapses": 10, "magnitude": 2.0},
            {"key": "c", "n_synapses": 10, "magnitude": 3.0},
            {"key": "d", "n_synapses": 10, "magnitude": 4.0},
        ]
        out = covariance_weighted_svd(recs, prior=0.15, keep_ratio=0.5)
        self.assertEqual(out["kept_keys"], ["d", "c"])  # en yüksek ağırlık
        self.assertEqual(out["kept"], 2)

    def test_gecersiz_keep_ratio(self):
        with self.assertRaises(ValueError):
            covariance_weighted_svd([], prior=0.1, keep_ratio=1.5)


class TestDogrulamaMatrisi(unittest.TestCase):
    def test_dort_yon_ve_karar(self):
        olcum = {
            "kod": {"aktivasyon_delta": 0.05, "kovaryans_delta": 0.02, "red_loss": 0.03, "behavior_rate": 0.85},
            "guvenlik": {"aktivasyon_delta": 0.05, "kovaryans_delta": 0.02, "red_loss": 0.02, "behavior_rate": 0.90},
            "arac": {"aktivasyon_delta": 0.05, "kovaryans_delta": 0.02, "red_loss": 0.04, "behavior_rate": 0.75},
            "dil": {"aktivasyon_delta": 0.05, "kovaryans_delta": 0.02, "red_loss": 0.25, "behavior_rate": 0.60},
        }
        out = validation_matrix(olcum)
        self.assertEqual(set(out["satirlar"].keys()), set(DIRECTIONS))
        self.assertEqual(out["satirlar"]["kod"]["karar"], "gec")
        self.assertEqual(out["satirlar"]["dil"]["karar"], "red")
        self.assertTrue(out["gerekceler"]["dil"])
        self.assertFalse(out["tamam"])

    def test_eksik_yon_tamam_engeli(self):
        out = validation_matrix({"kod": {"red_loss": 0.0, "behavior_rate": 1.0}})
        self.assertFalse(out["tamam"])


if __name__ == "__main__":
    unittest.main()
