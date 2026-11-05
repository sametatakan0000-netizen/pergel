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

    def test_saf_en_aile_bagimsiz(self):
        # Yollar aileye kilitli DEĞİLDİR (oyuncu ilkesi 2026-11-05):
        # aynı davranış skoru = aynı değer — aile/uyum bonusu YOK.
        # 3 farklı aile vs 1 aile, hepsi 0.8: saf-ende eşit olmalılar.
        combo_a = [REC("q1", "A", "a"), REC("q2", "A", "a"), REC("q3", "A", "a")]
        combo_b = [REC("q4", "A", "a"), REC("q5", "B", "b"), REC("q6", "C", "c")]
        scores = {"A": {"kod": 0.8}, "B": {"kod": 0.8}, "C": {"kod": 0.8}}
        self.assertEqual(combination_score(combo_a, scores, "kod"),
                         combination_score(combo_b, scores, "kod"))

    def test_mevki_katkisi_toplamlidir(self):
        # Tam yapılandırma = her mevkinin "en"i; her mevki toplama katkı verir.
        from src.mahoraga.combination_search import combination_score
        combo = [REC("q1", "A", "a"), REC("q2", "B", "b")]
        scores = {"A": {"kod": 0.3}, "B": {"kod": 0.4}}
        self.assertAlmostEqual(combination_score(combo, scores, "kod"), 0.7)


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


class TestSafEn(unittest.TestCase):
    """Oyuncu ilkesi (2026-11-05): modeller değişkendir, her aile her yolu
    yürüyebilir — yollar aileye kilitli değildir. Seçim SAF 'EN': aynı işi en
    iyi yapan kazanır, kazanmayan yola gerek yoktur. Çeşitlilik/uyum bonusu
    YOKTUR."""

    def test_davranis_skoru_kazanir_bonus_yok(self):
        from src.mahoraga.combination_search import combination_score
        iyi = [REC("q1", "A", "a")]
        zayif = [REC("q2", "B", "b"), REC("q3", "C", "c")]
        scores = {"A": {"kod": 0.9}, "B": {"kod": 0.3}, "C": {"kod": 0.3}}
        self.assertGreater(combination_score(iyi, scores, "kod"),
                           combination_score(zayif, scores, "kod"))

    def test_simulasyon_kazanani_tum_mevkilerin_eni(self):
        # Her mevki katkıdır (kaplama): tam yapılandırma = her mevkinin "en"i
        adaylar = ["x1", "x2", "x3"]
        skorlar = {"x1": 0.9, "x2": 0.7, "x3": 0.5}
        oracle = lambda combo: sum(skorlar[k] for k in combo)
        out = simulate_combinations(adaylar, oracle)
        self.assertEqual(set(out["en_iyi"]), {"x1", "x2", "x3"})

    def test_kadro_gorunumu_modellere_gore_gruplar(self):
        from src.mahoraga.combination_search import kadro_view
        recs = {
            "q1": {"key": "q1", "model": "Codestral-22B", "rol": "attention_q", "sinif": "attention"},
            "h1": {"key": "h1", "model": "Codestral-22B", "rol": "lm_head", "sinif": "embedding"},
            "e1": {"key": "e1", "model": "DeepSeek-V4.1-Flash", "rol": "embedding_in", "sinif": "embedding"},
        }
        k = kadro_view(recs, ["q1", "h1", "e1"])
        self.assertEqual(k["oyuncu_sayisi"], 2)
        self.assertEqual(k["kadro"]["Codestral-22B"]["mevkiler"], ["attention_q", "lm_head"])
        self.assertEqual(k["kadro"]["DeepSeek-V4.1-Flash"]["oynadigi_mevki"], 1)
