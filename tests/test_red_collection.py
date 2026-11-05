"""Faz-5: kırmızı toplama + kurtarma matrisi testleri (TDD — önce RED).

Kapsam (plan §8 Faz-5):
- çift yönlü ölçüm (aktivasyon + kovaryans)
- kırmızı kayıp (red loss) eşiği
- StegoLLM-PAQ marjinal kayıp AUC doğrulaması (0.98 hedef)
- altın-kırmızı 4 kopya kuralı
- kurtarma matrisi (kırmızı davranış -> reçete ailesi + yedek kaynakları)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.red_collection import (
    BACKUP_COPY_MIN,
    PAQ_AUC_TARGET,
    RED_LOSS_THRESHOLD,
    build_recovery_matrix,
    collect_reds,
    dual_measure,
    marginal_loss_auc,
    red_loss,
    verify_altin_kirmizi,
)


class TestDualMeasure(unittest.TestCase):
    def test_aktivasyon_kovaryans(self):
        m = dual_measure([1.0, -3.0, 2.0])
        self.assertEqual(m["n"], 3)
        self.assertAlmostEqual(m["aktivasyon"], 2.0)  # mean|x|
        self.assertAlmostEqual(m["kovaryans"], 4.6666666667, places=4)  # varyans = 14/3

    def test_bos_olcum_reddedilir(self):
        with self.assertRaises(ValueError):
            dual_measure([])


class TestRedLoss(unittest.TestCase):
    def test_dusus_hesabi_ve_karar(self):
        taban = {"kod": 0.80, "guvenlik": 0.90}
        simdi = {"kod": 0.75, "guvenlik": 0.88}
        out = red_loss(taban, simdi)
        self.assertAlmostEqual(out["dususler"]["kod"], 0.05)
        self.assertAlmostEqual(out["max_drop"], 0.05)
        self.assertTrue(out["kabul"])

    def test_esik_asimi_kabul_edilmez(self):
        out = red_loss({"kod": 0.90}, {"kod": 0.70})
        self.assertFalse(out["kabul"])
        self.assertGreater(out["max_drop"], RED_LOSS_THRESHOLD)

    def test_kayip_yoksa_mukemmel(self):
        out = red_loss({"kod": 0.5}, {"kod": 0.6})
        self.assertEqual(out["max_drop"], 0.0)


class TestPakAuc(unittest.TestCase):
    def test_mukemmel_ayrisim(self):
        self.assertAlmostEqual(marginal_loss_auc([0.9, 0.8], [0.2, 0.1]), 1.0)

    def test_ters_ayrisim(self):
        self.assertAlmostEqual(marginal_loss_auc([0.1, 0.2], [0.8, 0.9]), 0.0)

    def test_tie_dogrulamasi(self):
        self.assertAlmostEqual(marginal_loss_auc([0.5, 0.5], [0.5, 0.5]), 0.5)

    def test_hedef_araligi(self):
        self.assertEqual(PAQ_AUC_TARGET, 0.98)


class TestAltinKirmizi(unittest.TestCase):
    def test_dort_kopya_kurali(self):
        out = verify_altin_kirmizi(
            "deepseek_v41_engram",
            {
                "depo": {"deepseek_v41_engram": 10},
                "toshiba": {"deepseek_v41_engram": 10},
                "mahoraga_synapses": {"deepseek_v41_engram": 10},
                "manifest": {"deepseek_v41_engram": 10},
            },
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["kopie_sayisi"], BACKUP_COPY_MIN)

    def test_eksik_kopya_tespit(self):
        out = verify_altin_kirmizi(
            "x",
            {"depo": {"x": 5}, "toshiba": {"x": 5}},
        )
        self.assertFalse(out["ok"])
        self.assertIn("mahoraga_synapses", out["eksikler"])


class TestRecoveryMatrix(unittest.TestCase):
    REDS = [
        {"id": "red-1", "model": "Qwen/Qwen3-32B", "tur": "kod", "taban_puan": 0.8, "oney": "kritik"},
        {"id": "red-2", "model": "Qwen/Qwen3-32B", "tur": "guvenlik", "taban_puan": 0.9, "oney": "kritik"},
    ]
    RECIPE = {"modeller": {"Qwen/Qwen3-32B": "Qwen3 dense"}}
    BACKUPS = {
        "depo": {"Qwen/Qwen3-32B": 3},
        "toshiba": {"Qwen/Qwen3-32B": 3},
        "mahoraga_synapses": {"Qwen/Qwen3-32B": 3},
        "manifest": {"Qwen/Qwen3-32B": 3},
    }

    def test_matris_satirlari(self):
        out = build_recovery_matrix(self.REDS, self.RECIPE, self.BACKUPS)
        satirlar = {s["id"]: s for s in out["satirlar"]}
        self.assertEqual(len(satirlar), 2)
        self.assertEqual(satirlar["red-1"]["recete_ailesi"], "Qwen3 dense")
        self.assertTrue(satirlar["red-1"]["yedek_ok"])
        self.assertIn("kurtarma_adimi", satirlar["red-1"])

    def test_recetesiz_model_isaretlenir(self):
        out = build_recovery_matrix(
            [{"id": "r", "model": "yok/model", "tur": "kod", "taban_puan": 0.5, "oney": "kritik"}],
            self.RECIPE,
            self.BACKUPS,
        )
        self.assertFalse(out["satirlar"][0]["recete_ok"])


class TestCollectReds(unittest.TestCase):
    def test_toplama(self):
        reds = collect_reds(
            "m1",
            {"kod": 0.8, "guvenlik": 0.9, "arac": 0.7},
            {"kod": {"aktivasyon": 1.0, "kovaryans": 2.0}},
        )
        self.assertEqual(len(reds), 3)
        self.assertEqual({r["tur"] for r in reds}, {"kod", "guvenlik", "arac"})
        self.assertEqual(reds[0]["model"], "m1")


if __name__ == "__main__":
    unittest.main()
