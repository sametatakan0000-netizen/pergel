"""Kombinasyon arama motoru testleri (TDD — önce RED).

Kullanıcı tezi (05.11): sinapslar eşsiz parçalar DEĞİLDİR; farklı aileler
aynı işlevi farklı yollarla yapar. Görev: fonksiyonel kümeleme -> her
kümeden "en" iyi temsil süzme -> kombinasyonları simüle edip nihai sonuca
ulaşma (bütçe-sınırlı arama; 2^N yerine exhaustive küçük k + greedy).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.combination_search import (
    combination_score,
    functional_clusters,
    select_best,
    simulate_combinations,
)


REC = lambda key, model, aile, n=100, mag=1.0: {
    "key": key, "model": model, "aile": aile, "n_synapses": n, "magnitude": mag,
}


class TestFonksiyonelKumeleme(unittest.TestCase):
    def test_role_gore_kumelenir(self):
        recs = [
            REC("model.layers.0.self_attn.q_proj.weight", "A", "a"),
            REC("model.layers.2.self_attn.q_proj.weight", "B", "b"),
            REC("model.layers.0.mlp.gate_proj.weight", "A", "a"),
        ]
        out = functional_clusters(recs)
        self.assertEqual(sum(len(v) for v in out.values()), 3)
        q_clusters = [v for v in out.values() if len(v) == 2]
        self.assertEqual(len(q_clusters), 1)  # iki q_proj aynı kümede
        self.assertEqual(len([v for v in out.values() if len(v) == 1]), 1)


class TestEnSuzme(unittest.TestCase):
    def test_hedef_davranista_en_iyi_uyeler(self):
        clusters = {
            "attention_q": [
                REC("q1", "A", "a"),
                REC("q2", "B", "b"),
            ],
        }
        scores = {"A": {"kod": 0.6}, "B": {"kod": 0.9}}
        out = select_best(clusters, hedef_davranis="kod", model_skorlari=scores, prior=0.15)
        self.assertEqual(out["attention_q"]["en"], "q2")
        self.assertEqual(out["attention_q"]["adaylar"][0], "q2")
        self.assertIn("q1", out["attention_q"]["adaylar"])

    def test_kovaryans_agirlik_rutbesi_dusuk_modeli_yukseltir(self):
        # aynı davranış skorunda büyük/kuvvetli sinaps kazanır
        clusters = {"attention_q": [REC("q1", "A", "a", n=10, mag=0.1),
                                    REC("q2", "B", "b", n=1000, mag=5.0)]}
        scores = {"A": {"kod": 0.8}, "B": {"kod": 0.8}}
        out = select_best(clusters, "kod", scores, prior=0.15)
        self.assertEqual(out["attention_q"]["en"], "q2")


class TestSimulasyon(unittest.TestCase):
    def test_exhaustive_kadar_ara_butceye_hormet(self):
        adaylar = ["x1", "x2", "x3"]
        skorlar = {"x1": 0.5, "x2": 0.9, "x3": 0.7}
        oracle = lambda combo: sum(skorlar[k] for k in combo)
        out = simulate_combinations(adaylar, oracle, max_k=2, budget=100)
        self.assertEqual(set(out["en_iyi"]), {"x2", "x3"})
        self.assertLessEqual(out["simulasyon_sayisi"], 100)

    def test_butce_asimi_durdurur(self):
        adaylar = [f"x{i}" for i in range(50)]
        oracle = lambda combo: 1.0
        out = simulate_combinations(adaylar, oracle, max_k=3, budget=10)
        self.assertLessEqual(out["simulasyon_sayisi"], 10)

    def test_cesitlilik_bonusu_farkli_aileler(self):
        combo_a = [REC("q1", "A", "a"), REC("q2", "B", "b")]
        combo_b = [REC("q3", "A", "a"), REC("q4", "A", "a")]
        scores = {"A": {"kod": 0.8}, "B": {"kod": 0.8}}
        sa = combination_score(combo_a, scores, "kod")
        sb = combination_score(combo_b, scores, "kod")
        self.assertGreater(sa, sb)  # farklı aile = farklı yol = bonus


if __name__ == "__main__":
    unittest.main()


class TestHuniVeTamSimulasyon(unittest.TestCase):
    def test_huni_dusuk_skorlulur_elener(self):
        from src.mahoraga.combination_search import funnel_candidates
        best = {
            "attention_q": {"en": "q1", "adaylar": ["q1"], "skorlar": {"q1": 9.0},
                            "davranis_skoru": 0.9},
            "norm": {"en": "n1", "adaylar": ["n1"], "skorlar": {"n1": 1.0},
                     "davranis_skoru": 0.3},
        }
        out = funnel_candidates(best, min_skor=0.6, ust_sinir=18)
        self.assertIn("attention_q", out)
        self.assertNotIn("norm", out)

    def test_huni_ust_sinir_kalite_sirasiyla_kisar(self):
        from src.mahoraga.combination_search import funnel_candidates
        best = {f"r{i}": {"en": f"k{i}", "adaylar": [f"k{i}"], "skorlar": {f"k{i}": 1.0},
                          "davranis_skoru": 0.5 + i * 0.01}
                for i in range(10)}
        out = funnel_candidates(best, min_skor=0.4, ust_sinir=3)
        self.assertEqual(len(out), 3)
        self.assertIn("r9", out)  # en yüksek skorlu kalır

    def test_max_k_verilmezse_tum_boyutlar_simule_edilir(self):
        adaylar = ["x1", "x2", "x3"]
        cagrilar = []
        oracle = lambda combo: (cagrilar.append(tuple(combo)) or 1.0)
        out = simulate_combinations(adaylar, oracle, budget=1000)
        self.assertEqual(out["simulasyon_sayisi"], 7)  # 2^3 − 1
        self.assertTrue(out["tam_exhaustive"])
