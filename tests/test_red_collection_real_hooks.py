"""Faz-5.5: GERÇEK aktivasyon hook'ları testleri (TDD — önce RED).

Kapsam:
- TransformerLens 4.x hook aday adları (blocks.N.hook_resid_post / attn_out /
  mlp_out / resid_pre) — TransformerBridge alias sözleşmesi
- köprü protokolü (run_with_cache) üzerinden GERÇEK tensör yakalama
  (sahte log yok; hook'lar gerçekten ateşlenir, değerler elle hesaplanan
  ileri geçiş çıktısıyla birebir aynıdır)
- HF gizli-durum yolu (faz5_extraction.collect_activations ile aynı katman
  indeksleme: hidden_states[l+1])
- padding maskesi (geçerli tokenlar) ve katman/seçenek doğrulama
- measure_layers -> dual_measure -> collect_reds beslemesi
- TransformerLens 4.0 sözleşmesi: HookedTransformer KALDIRILDI,
  API TransformerBridge.boot_transformers (yerel paketten doğrulanır;
  model indirmez)

Testler ağdan model indirmez: yalnız mock köprü + tiny yerel torch modelleri.
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.mahoraga.red_collection import (
    HOOK_SITES,
    capture_activations,
    collect_reds,
    dual_measure,
    hook_names,
    load_bridge_model,
    measure_layers,
)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    HAS_NUMPY = False

try:
    import torch
    HAS_TORCH = True
except ImportError:  # pragma: no cover
    HAS_TORCH = False


class TestHookNames(unittest.TestCase):
    """TransformerLens hook aday adları (TransformerBridge alias sözleşmesi)."""

    def test_resid_post_adlari(self):
        self.assertEqual(
            hook_names([0, 3]),
            ["blocks.0.hook_resid_post", "blocks.3.hook_resid_post"],
        )

    def test_attn_mlp_resid_pre_siteleri(self):
        self.assertEqual(hook_names([2], "attn_out"), ["blocks.2.hook_attn_out"])
        self.assertEqual(hook_names([2], "mlp_out"), ["blocks.2.hook_mlp_out"])
        self.assertEqual(hook_names([1], "resid_pre"), ["blocks.1.hook_resid_pre"])

    def test_tum_siteler_tanimli(self):
        self.assertEqual(
            set(HOOK_SITES), {"resid_pre", "resid_post", "attn_out", "mlp_out"}
        )

    def test_bos_katman_reddedilir(self):
        with self.assertRaises(ValueError):
            hook_names([])

    def test_gecersiz_site_reddedilir(self):
        with self.assertRaises(ValueError):
            hook_names([0], "attn_scores")

    def test_negatif_katman_reddedilir(self):
        with self.assertRaises(ValueError):
            hook_names([-1])

    def test_tamsayi_olmayan_katman_reddedilir(self):
        with self.assertRaises(ValueError):
            hook_names(["a"])

    def test_tekrarlanan_katman_temizlenir(self):
        self.assertEqual(
            hook_names([2, 2, 1]),
            ["blocks.2.hook_resid_post", "blocks.1.hook_resid_post"],
        )


if HAS_TORCH and HAS_NUMPY:

    class _HookPoint(torch.nn.Module):
        """TL tarzı hook noktası: ileri geçişi değiştirmez."""

        def forward(self, x):
            return x

    class _TinyBlock(torch.nn.Module):
        def __init__(self, d_model):
            super().__init__()
            self.lin = torch.nn.Linear(d_model, d_model)
            self.hook_resid_post = _HookPoint()

        def forward(self, x):
            return self.hook_resid_post(torch.tanh(self.lin(x)))

    class TinyBridge(torch.nn.Module):
        """TransformerLens köprü protokolü (run_with_cache) — GERÇEK torch
        forward hook'ları ile gerçek tensör toplar (log değil)."""

        def __init__(self, n_layers=3, d_model=4, seed=0):
            super().__init__()
            torch.manual_seed(seed)
            self.cfg = types.SimpleNamespace(n_layers=n_layers, d_model=d_model)
            self.blocks = torch.nn.ModuleList(
                [_TinyBlock(d_model) for _ in range(n_layers)]
            )
            self.hooks_fired = []
            self.received_input = None

        def forward(self, x):
            for blk in self.blocks:
                x = blk(x)
            return x

        def run_with_cache(self, inputs, names_filter=None, **kwargs):
            self.received_input = inputs
            cache = {}
            handles = []
            for i, blk in enumerate(self.blocks):
                name = f"blocks.{i}.hook_resid_post"
                if names_filter is not None and not names_filter(name):
                    continue

                def hook(mod, inp, out, name=name):
                    cache[name] = out
                    self.hooks_fired.append(name)

                handles.append(blk.hook_resid_post.register_forward_hook(hook))
            try:
                logits = self.forward(inputs)
            finally:
                for h in handles:
                    h.remove()
            return logits, cache

    class TinyHF(torch.nn.Module):
        """HF transformers tarzı model: hidden_states tuple döndürür
        (faz5_extraction.load_model ile aynı sözleşme)."""

        def __init__(self, n_layers=3, d_model=4, seed=1):
            super().__init__()
            torch.manual_seed(seed)
            self.config = types.SimpleNamespace(num_hidden_layers=n_layers)
            self.embed = torch.nn.Embedding(10, d_model)
            self.blocks = torch.nn.ModuleList(
                [torch.nn.Linear(d_model, d_model) for _ in range(n_layers)]
            )
            self.forward_calls = 0

        def forward(self, input_ids=None, attention_mask=None,
                    output_hidden_states=False, **kwargs):
            self.forward_calls += 1
            x = self.embed(input_ids)
            hidden = [x]
            for blk in self.blocks:
                x = torch.tanh(blk(x))
                hidden.append(x)
            return types.SimpleNamespace(
                logits=x,
                hidden_states=tuple(hidden) if output_hidden_states else None,
            )

    class TestBridgeProtocolCapture(unittest.TestCase):
        """run_with_cache protokolü üzerinden GERÇEK tensör yakalama."""

        def setUp(self):
            self.bridge = TinyBridge(n_layers=3, d_model=4)
            self.x = torch.arange(2 * 3 * 4, dtype=torch.float32).reshape(2, 3, 4)

        def test_beklenen_katman_degerleri_birebir(self):
            acts = capture_activations(self.bridge, self.x, [0, 2])
            self.assertEqual(sorted(acts.keys()), [0, 2])
            # elle hesaplanan ileri geçiş: blok çıktıları hook_resid_post'tur
            h = self.x
            expected = {}
            for i, blk in enumerate(self.bridge.blocks):
                h = blk(h)
                if i in (0, 2):
                    expected[i] = h.detach().reshape(-1, 4).numpy()
            for l in (0, 2):
                self.assertEqual(acts[l].shape, (6, 4))
                self.assertEqual(acts[l].dtype, np.float32)
                np.testing.assert_allclose(acts[l], expected[l], rtol=0, atol=0)

        def test_hooklar_gercekten_ateslenir(self):
            capture_activations(self.bridge, self.x, [1])
            self.assertEqual(self.bridge.hooks_fired, ["blocks.1.hook_resid_post"])

        def test_yalniz_istenen_isimler_toplanir(self):
            acts = capture_activations(self.bridge, self.x, [1])
            self.assertEqual(list(acts.keys()), [1])

        def test_girdi_modele_aiten_gecirilir(self):
            capture_activations(self.bridge, self.x, [0])
            self.assertTrue(torch.equal(self.bridge.received_input, self.x))

        def test_token_maskesi_padding_dusurur(self):
            mask = torch.tensor([[True, True, False], [True, False, False]])
            acts = capture_activations(self.bridge, self.x, [0], token_mask=mask)
            self.assertEqual(acts[0].shape, (3, 4))
            h0 = self.bridge.blocks[0](self.x).detach().reshape(-1, 4).numpy()
            np.testing.assert_allclose(acts[0], h0[[0, 1, 3]], rtol=0, atol=0)

        def test_maskesiz_tum_tokenlar(self):
            acts = capture_activations(self.bridge, self.x, [0])
            self.assertEqual(acts[0].shape, (6, 4))

        def test_ateslenmeyen_hook_hata_verir(self):
            class NoFire(TinyBridge):
                def run_with_cache(self, inputs, names_filter=None, **kwargs):
                    return self.forward(inputs), {}  # hook hiç ateşlenmedi

            with self.assertRaises(RuntimeError) as cm:
                capture_activations(NoFire(), self.x, [0])
            self.assertIn("blocks.0.hook_resid_post", str(cm.exception))

    class TestHFHiddenStatesCapture(unittest.TestCase):
        """HF gizli-durum yolu: hidden_states[l+1] (faz5_extraction ile aynı)."""

        def setUp(self):
            self.model = TinyHF(n_layers=3, d_model=4)
            self.ids = torch.randint(0, 10, (2, 3))
            self.mask = torch.tensor([[1, 1, 0], [1, 0, 0]], dtype=torch.long)

        def test_hidden_states_indeksleme(self):
            acts = capture_activations(
                self.model, {"input_ids": self.ids}, [0, 2]
            )
            out = self.model(input_ids=self.ids, output_hidden_states=True)
            for l in (0, 2):
                expected = out.hidden_states[l + 1].detach().reshape(-1, 4).numpy()
                np.testing.assert_allclose(acts[l], expected, rtol=0, atol=0)

        def test_attention_mask_otomatik_token_maskesi(self):
            acts = capture_activations(
                self.model,
                {"input_ids": self.ids, "attention_mask": self.mask},
                [1],
            )
            self.assertEqual(acts[1].shape, (3, 4))  # 2*3=6 token, 3 geçerli

        def test_hf_yolu_attn_site_desteklemez(self):
            with self.assertRaises(ValueError):
                capture_activations(
                    self.model, {"input_ids": self.ids}, [0], site="attn_out"
                )

        def test_katman_siniri_asimi(self):
            with self.assertRaises(ValueError):
                capture_activations(self.model, {"input_ids": self.ids}, [3])

    class TestMeasureLayers(unittest.TestCase):
        def test_dual_measure_beslemesi(self):
            arr = np.array([[1.0, -3.0], [2.0, 2.0]], dtype=np.float32)
            out = measure_layers({0: arr})
            self.assertEqual(set(out.keys()), {"0"})
            beklenen = dual_measure([1.0, -3.0, 2.0, 2.0])
            self.assertAlmostEqual(out["0"]["aktivasyon"], beklenen["aktivasyon"])
            self.assertAlmostEqual(out["0"]["kovaryans"], beklenen["kovaryans"])
            self.assertEqual(out["0"]["n"], 4)

        def test_collect_reds_ile_uyumlu(self):
            arr = np.array([[0.5]], dtype=np.float32)
            measures = measure_layers({0: arr})
            reds = collect_reds("m1", {"kod": 0.8}, {"kod": measures["0"]})
            self.assertEqual(reds[0]["olcum"]["n"], 1)
            self.assertAlmostEqual(reds[0]["olcum"]["aktivasyon"], 0.5)


class TestModelDogrulama(unittest.TestCase):
    def test_model_olmayan_nesne_typeerror(self):
        with self.assertRaises(TypeError):
            capture_activations(object(), {}, [0])

    def test_bos_katman_listesi_reddedilir(self):
        with self.assertRaises(ValueError):
            capture_activations(object(), {}, [])


class TestTransformerLensV4Sozlesme(unittest.TestCase):
    """Yerel transformer_lens paketi üzerinde API doğrulaması (model indirmez)."""

    def test_hooked_transformer_kaldirildi_bridge_var(self):
        try:
            import transformer_lens
        except ImportError:
            self.skipTest("transformer_lens kurulu değil")
        self.assertTrue(hasattr(transformer_lens, "TransformerBridge"))
        with self.assertRaises(ImportError):
            from transformer_lens import HookedTransformer  # noqa: F401

    def test_load_bridge_model_boot_transformers_kullanimi(self):
        doc = load_bridge_model.__doc__ or ""
        self.assertIn("TransformerBridge", doc)
        self.assertIn("boot_transformers", doc)
        self.assertTrue(callable(load_bridge_model))


if __name__ == "__main__":
    unittest.main()
