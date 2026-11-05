"""Faz-5.5: davranış denetimi testleri (TDD — önce RED).

Kapsam (plan §8 Faz-5.5):
- PRM/ORM süreç ödülü: ORM yalnız sonucu, PRM her adımı ödüllendirir;
  uzun araç çağrısı zincirlerinde PRM tercih edilir.
- Seçim ağırlığı düzeltmesi: AdaBoost / WINNOW türü ağırlık büyütme.
- Davranış puanlama: yüksek örneklemeli denetim + %70 davranış doğrulama eşiği.
- Karmaşık -> Basit Karmaşık -> Basit uzman akışı kontrolü.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.behavior_audit import (
    BEHAVIOR_PASS_THRESHOLD,
    FLOW_STAGES,
    adaboost_update,
    chain_reward,
    flow_check,
    orm_score,
    prm_score,
    update_selection_weights,
    winnow_update,
)


class TestPrmOrm(unittest.TestCase):
    def test_orm_yalniz_sonuc(self):
        steps = [0.0, 0.0, 1.0]
        self.assertEqual(orm_score(steps), 1.0)

    def test_prm_her_adim(self):
        steps = [1.0, 0.0, 1.0]
        self.assertAlmostEqual(prm_score(steps), 2.0 / 3.0)

    def test_zincir_odulu_mod_secimi(self):
        steps = [0.0, 1.0]
        self.assertEqual(chain_reward(steps, mode="orm"), 1.0)
        self.assertAlmostEqual(chain_reward(steps, mode="prm"), 0.5)

    def test_bos_zincir_reddedilir(self):
        with self.assertRaises(ValueError):
            chain_reward([], mode="prm")

    def test_bilinmeyen_mod_reddedilir(self):
        with self.assertRaises(ValueError):
            chain_reward([1.0], mode="xyz")


class TestAgirlikGuncelleme(unittest.TestCase):
    def test_adaboost_hata_buyutur(self):
        w = adaboost_update([1.0, 1.0], [1.0, 0.0])
        self.assertGreater(w[0], w[1])
        self.assertAlmostEqual(sum(w), 1.0)

    def test_adaboost_tek_dogru_sabit(self):
        w = adaboost_update([0.5, 0.5], [0.0, 0.0])
        self.assertAlmostEqual(w[0], 0.5)
        self.assertAlmostEqual(w[1], 0.5)

    def test_winnow_yukseltme_azaltma(self):
        w = winnow_update([1.0, 1.0], [1.0, 0.0])
        self.assertAlmostEqual(w[0], 2.0)  # hata -> x2
        self.assertAlmostEqual(w[1], 0.5)  # dogru -> x0.5

    def test_dispatch(self):
        self.assertEqual(
            update_selection_weights([1.0], [1.0], method="winnow"), winnow_update([1.0], [1.0])
        )
        with self.assertRaises(ValueError):
            update_selection_weights([1.0], [1.0], method="yok")


class TestDavranisPuanlama(unittest.TestCase):
    def test_basari_orani_ve_esik(self):
        from src.mahoraga.behavior_audit import behavior_score
        out = behavior_score(successes=7, trials=10)
        self.assertAlmostEqual(out["rate"], 0.7)
        self.assertTrue(out["gecer"])
        self.assertEqual(BEHAVIOR_PASS_THRESHOLD, 0.70)

    def test_esik_alti_gecersiz(self):
        from src.mahoraga.behavior_audit import behavior_score
        out = behavior_score(successes=6, trials=10)
        self.assertFalse(out["gecer"])

    def test_sifir_deneme_reddedilir(self):
        from src.mahoraga.behavior_audit import behavior_score
        with self.assertRaises(ValueError):
            behavior_score(successes=0, trials=0)


class TestUzmanAkisi(unittest.TestCase):
    def test_akis_sirasi(self):
        self.assertEqual(FLOW_STAGES, ("karmasik", "basit_karmasik", "basit"))
        self.assertTrue(flow_check())

    def test_akis_tamamlanmamis(self):
        self.assertFalse(flow_check(("karmasik",)))


if __name__ == "__main__":
    unittest.main()
