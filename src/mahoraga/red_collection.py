"""Faz-5: Kırmızı toplama + kurtarma matrisi.

Kırmızı = ameliyattan sonra KAYBEDİLMEMESİ gereken davranış (araç,
güvenlik, dil/karar, kod, matematik, araştırma — plan §8). Bu modül:

- çift yönlü ölçüm (aktivasyon + kovaryans)
- kırmızı kayıp (red loss) eşiği kontrolü
- Marjinal kayıp AUC doğrulaması (0.98 mühendislik hedefi; "PAQ" adı doğrulanamadı — bkz. plan §7.1; kanıt bandı LSGC %70-99)
- altın-kırmızı 4 kopya yedek kuralı
- kurtarma matrisi (kırmızı davranış -> reçete ailesi + yedek kaynakları)
- Faz-5.5 GERÇEK aktivasyon yakalama: TransformerLens 4.x köprü protokolü
  (TransformerBridge.run_with_cache) veya HF gizli-durum yolu üzerinden
  seçili katmanlarda residual-stream (opsiyonel attn/mlp) tensörleri

Model-güdümlü davranış testleri (Faz-5.5: PRM/ORM, IA gizlilik) ayrı
çalışmada; burada deterministik çekirdek + gerçek hook'lar var.
"""
from __future__ import annotations

import contextlib
import math
import operator

BEHAVIOR_TURS = ("kod", "guvenlik", "arac", "dil_karar", "matematik", "arastirma")

# Kırmızı kayıp eşiği: davranış puanındaki en büyük düşüş bunu aşarsa
# ameliyat reddedilir (geri alma / kurtarma matrisi devreye girer).
RED_LOSS_THRESHOLD = 0.10

# Marjinal kayıp AUC hedefi (mühendislik kapısı). "PAQ" adı kamuya açık
# kaynakta bulunamadı (plan §7.1); kanıt çapası: LSGC steganaliz bandı (arXiv:2406.04218).
PAQ_AUC_TARGET = 0.98

# Altın-kırmızı kural: sinaps yedekleri asla 4 kopyadan az olmaz
# (depo + Toshiba + mahoraga_synapses/ + manifest).
BACKUP_COPY_MIN = 4

# Kurtarma matrisinin standart yedek kaynakları.
BACKUP_SOURCES = ("depo", "toshiba", "mahoraga_synapses", "manifest")


def dual_measure(samples: list[float]) -> dict:
    """Çift yönlü ölçüm: aktivasyon (mean|x|) + kovaryans (varyans).

    Gerçek model aktivasyonları için bkz. capture_activations (Faz-5.5):
      TransformerLens 4.x köprü protokolü (TransformerBridge.run_with_cache)
      veya HF gizli-durum yolu ile katman tensörleri toplanır, measure_layers
      ile bu özet formatına dönüştürülür. Arayüz aynı kalır.
    """
    vals = [float(x) for x in samples]
    if not vals:
        raise ValueError("ölçüm boş olamaz")
    n = len(vals)
    aktivasyon = sum(abs(v) for v in vals) / n
    mean = sum(vals) / n
    kovaryans = sum((v - mean) ** 2 for v in vals) / n
    return {"aktivasyon": aktivasyon, "kovaryans": kovaryans, "n": n}


def collect_reds(model: str, behavior_scores: dict, measures: dict | None = None) -> list[dict]:
    """Davranış puanlarını kırmızı kayıtlarına toplar (Faz-5 toplama).

    behavior_scores: {tur: puan}. Her puanlı tür bir kırmızı adayıdır;
    ölçüm varsa kayda eklenir. Türler BEHAVIOR_TURS ile sınırlıdır.
    """
    measures = measures or {}
    reds = []
    for tur, puan in behavior_scores.items():
        if tur not in BEHAVIOR_TURS:
            raise ValueError(f"bilinmeyen davranış türü: {tur}")
        reds.append({
            "id": f"red-{model}-{tur}",
            "model": model,
            "tur": tur,
            "taban_puan": float(puan),
            "olcum": measures.get(tur),
            "oney": "kritik",
        })
    return sorted(reds, key=lambda r: r["tur"])


def red_loss(baseline: dict, current: dict) -> dict:
    """Kırmızı kayıp: davranış bazında düşüş + kabul kararı.

    Kabul: max_drop <= RED_LOSS_THRESHOLD. Eksik türler yalnız iki
    tarafta da varsa hesaplanır (kırmızı listesi sabitlenir).
    """
    dususler = {}
    for tur in sorted(set(baseline) & set(current)):
        dusus = float(baseline[tur]) - float(current[tur])
        if dusus > 0:
            dususler[tur] = dusus
    max_drop = max(dususler.values()) if dususler else 0.0
    return {
        "dususler": dususler,
        "max_drop": max_drop,
        "esik": RED_LOSS_THRESHOLD,
        "kabul": max_drop <= RED_LOSS_THRESHOLD,
    }


def marginal_loss_auc(clean_scores: list[float], stego_scores: list[float]) -> float:
    """Marjinal kayıp doğrulaması: temiz vs gizli skor AUC'su.

    AUC = P(temiz > gizli) + 0.5·P(eşit); hedef PAQ_AUC_TARGET (0.98).
    Boş liste ValueError.
    """
    if not clean_scores or not stego_scores:
        raise ValueError("iki skor listesi de dolu olmalı")
    wins = ties = 0.0
    for a in clean_scores:
        for b in stego_scores:
            if a > b:
                wins += 1
            elif a == b:
                ties += 1
    total = len(clean_scores) * len(stego_scores)
    return (wins + 0.5 * ties) / total


def verify_altin_kirmizi(synapse_group: str, locations: dict) -> dict:
    """Altın-kırmızı 4 kopya kuralını doğrular.

    locations: {kaynak: {synapse_group: adet}} — BACKUP_SOURCES'taki her
    kaynakta grup bulunmalı. Eksikler listelenir.
    """
    present = [src for src in BACKUP_SOURCES if synapse_group in locations.get(src, {})]
    eksikler = [src for src in BACKUP_SOURCES if src not in present]
    return {
        "synapse_group": synapse_group,
        "kopie_sayisi": len(present),
        "gerekli": BACKUP_COPY_MIN,
        "ok": len(present) >= BACKUP_COPY_MIN,
        "eksikler": eksikler,
    }


def build_recovery_matrix(reds: list[dict], recipe_map: dict, backup_locations: dict) -> dict:
    """Kurtarma matrisi: her kırmızı davranış için kurtarma planı satırı.

    Her satır: reçete ailesi (recipe_map['modeller']), yedek kopya
    doğrulaması (verify_altin_kirmizi) ve somut kurtarma adımı.
    """
    modeller = recipe_map.get("modeller", {})
    satirlar = []
    for red in reds:
        model = red["model"]
        recete = modeller.get(model)
        yedek = verify_altin_kirmizi(model, backup_locations)
        adim = (
            f"{red['tur']} kırmızısı: {model} gövdesi yedeklerinden geri "
            f"yüklenecek; reçete ({recete or 'TANIMSIZ'}) ile kapılar "
            f"yeniden uygulanır"
        )
        satirlar.append({
            "id": red["id"],
            "tur": red["tur"],
            "model": model,
            "recete_ailesi": recete,
            "recete_ok": recete is not None,
            "yedek_ok": yedek["ok"],
            "yedek_detay": yedek,
            "kurtarma_adimi": adim,
        })
    return {
        "satirlar": satirlar,
        "toplam_kirmizi": len(satirlar),
        "hazir": all(s["recete_ok"] and s["yedek_ok"] for s in satirlar),
    }


# ---------------------------------------------------------------------------
# Faz-5.5: GERÇEK aktivasyon yakalama (TransformerLens 4.x köprüsü)
# ---------------------------------------------------------------------------
# TransformerLens 4.0'da HookedTransformer KALDIRILDI (import hatası
# migrating_to_v4.md'yi işaret eder); API TransformerBridge'tir ve hook
# aday adları klasik TL sözleşmesini korur: blocks.{katman}.hook_resid_post /
# hook_resid_pre / hook_attn_out / hook_mlp_out (bridge_core.hook_aliases).

# Yakalanabilir hook siteleri -> TransformerLens hook adı eki.
HOOK_SITES = {
    "resid_pre": "hook_resid_pre",
    "resid_post": "hook_resid_post",
    "attn_out": "hook_attn_out",
    "mlp_out": "hook_mlp_out",
}

# HF gizli-durum indekslemesi: hidden_states[0] = gömme katmanı;
# katman l'in residual çıktısı hidden_states[l + 1] (faz5_extraction ile aynı).
HF_HIDDEN_OFFSET = 1


def _normalize_layers(layers) -> list[int]:
    """Katman kimliklerini doğrular: tam sayı (bool değil), negatif olamaz,
    tekrarlar ilk geçtiği sırada temizlenir. Boş liste ValueError."""
    if layers is None:
        raise ValueError("katman listesi boş olamaz")
    try:
        raw = list(layers)
    except TypeError as exc:
        raise ValueError("katman listesi iterable olmalı") from exc
    if not raw:
        raise ValueError("katman listesi boş olamaz")
    out: list[int] = []
    for l in raw:
        if isinstance(l, bool):
            raise ValueError("katman kimliği tam sayı olmalı")
        try:
            li = operator.index(l)
        except TypeError as exc:
            raise ValueError("katman kimliği tam sayı olmalı") from exc
        if li < 0:
            raise ValueError(f"negatif katman kimliği: {li}")
        if li not in out:
            out.append(li)
    return out


def hook_names(layers, site: str = "resid_post") -> list[str]:
    """TransformerLens hook aday adları: blocks.{katman}.{suffix}.

    site: HOOK_SITES anahtarlarından biri (resid_pre/resid_post/attn_out/
    mlp_out). Bilinmeyen site veya boş katman listesi ValueError.
    """
    if site not in HOOK_SITES:
        raise ValueError(
            f"bilinmeyen hook sitesi: {site!r} (geçerli: {sorted(HOOK_SITES)})"
        )
    suffix = HOOK_SITES[site]
    return [f"blocks.{l}.{suffix}" for l in _normalize_layers(layers)]


def _model_n_layers(model) -> int | None:
    """Modelin katman sayısını keşfeder (bilinemiyorsa None)."""
    for attr, key in (("cfg", "n_layers"), ("config", "num_hidden_layers")):
        holder = getattr(model, attr, None)
        n = getattr(holder, key, None)
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            return n
    blocks = getattr(model, "blocks", None)
    if blocks is not None:
        try:
            n = len(blocks)
        except TypeError:
            n = 0
        if n > 0:
            return n
    return None


def _to_matrix(t, token_mask=None):
    """Aktivasyon tensörünü (n_gecerli_token, d_model) float32 matrise indirger.

    torch.Tensor veya numpy.ndarray kabul eder; 3B (B, S, D) ve 2B (S, D)
    girdiler maskesiz tüm tokenlarla, maskeli yalnız geçerli satırlarla
    döner (faz5_extraction.collect_activations çıktısıyla aynı format).
    """
    import numpy as np

    if hasattr(t, "detach"):  # torch.Tensor
        arr = t.detach().cpu().float().numpy()
    else:
        arr = np.asarray(t, dtype=np.float32)
    mask = None
    if token_mask is not None:
        m = token_mask
        if hasattr(m, "detach"):
            m = m.detach().cpu()
        mask = np.asarray(m, dtype=bool)
    if arr.ndim == 3:
        b, s, d = arr.shape
        flat = arr.reshape(b * s, d)
        if mask is not None:
            if mask.shape != (b, s):
                raise ValueError(
                    f"token_mask şekli {mask.shape}, beklenen {(b, s)}"
                )
            flat = flat[mask.reshape(-1)]
        return np.ascontiguousarray(flat, dtype=np.float32)
    if arr.ndim == 2:
        if mask is not None:
            if mask.shape != arr.shape[:1]:
                raise ValueError(
                    f"token_mask şekli {mask.shape}, beklenen {arr.shape[:1]}"
                )
            arr = arr[mask]
        return np.ascontiguousarray(arr, dtype=np.float32)
    raise ValueError(f"beklenmeyen aktivasyon boyutu: {arr.shape}")


def _capture_bridge(model, inputs, names, layer_ids, token_mask):
    """TransformerLens köprü protokolü: run_with_cache + names_filter ile
    yalnız istenen hook'lar gerçekten ateşlenir ve tensörleri toplanır."""
    wanted = set(names)
    result = model.run_with_cache(inputs, names_filter=lambda n: n in wanted)
    try:
        _logits, cache = result
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "run_with_cache (logits, cache) ikilisi döndürmeli"
        ) from exc
    acts = {}
    for l, name in zip(layer_ids, names):
        try:
            t = cache[name]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(
                f"hook hiç ateşlenmedi: {name} "
                f"(model bu hook noktasını sunmuyor olabilir)"
            ) from exc
        acts[l] = _to_matrix(t, token_mask)
    return acts


def _capture_hidden_states(model, inputs, layer_ids, token_mask):
    """HF transformers yolu: forward(..., output_hidden_states=True) ile
    hidden_states[l + 1] (gömme = 0) residual akışı — faz5_extraction ile
    aynı katman indekslemesi."""
    if isinstance(inputs, dict):
        kwargs = dict(inputs)
    else:
        raise TypeError(
            "HF gizli-durum yolu dict girdisi bekler (ör. {'input_ids': ...})"
        )
    kwargs.setdefault("output_hidden_states", True)
    try:
        import torch

        ctx = torch.no_grad()
    except ImportError:
        ctx = contextlib.nullcontext()
    with ctx:
        result = model(**kwargs)
    hs = getattr(result, "hidden_states", None)
    if hs is None:
        raise TypeError(
            "model gizli-durum (hidden_states) döndürmedi; TransformerLens "
            "köprüsü için run_with_cache protokolü gerekir"
        )
    mask = token_mask if token_mask is not None else kwargs.get("attention_mask")
    acts = {}
    for l in layer_ids:
        idx = l + HF_HIDDEN_OFFSET
        if idx >= len(hs):
            raise ValueError(
                f"hidden_states katman {l} için yetersiz ({len(hs)} kayıt)"
            )
        acts[l] = _to_matrix(hs[idx], mask)
    return acts


def capture_activations(model, inputs, layers, site: str = "resid_post",
                        token_mask=None) -> dict:
    """GERÇEK aktivasyon yakalama: seçili katmanlarda residual/attn/mlp
    tensörleri (log değil — gerçek ileri geçiş hook'ları).

    Arka uçlar (otomatik seçilir):
    1. TransformerLens köprü protokolü — `run_with_cache` sunan modeller
       (TransformerBridge 4.x / eski HookedTransformer). `inputs` modele
       olduğu gibi geçirilir (str, list[str] veya token tensörü).
    2. HF gizli-durum yolu — `forward(**kwargs, output_hidden_states=True)`
       ile `hidden_states` dönen modeller (faz5_extraction.load_model).
       Katman l residual çıktısı hidden_states[l + 1]; site yalnız
       "resid_post" olabilir. attention_mask (varsa) token maskesi sayılır.

    Dönen: {katman: float32 (n_gecerli_token, d_model) ndarray} —
    faz5_extraction.collect_activations formatı; extract_directions ve
    measure_layers ile doğrudan beslenebilir.

    token_mask: (B, S) veya (S,) bool maskesi — False tokenlar atılır.
    Bilinmeyen site, boş/geçersiz katman listesi, sınır dışı katman
    ValueError; uyumsuz model TypeError; hiç ateşlenmeyen hook RuntimeError.
    """
    names = hook_names(layers, site)  # site + katman doğrulaması
    layer_ids = _normalize_layers(layers)
    if not callable(model):
        raise TypeError("model çağrılabilir olmalı (nn.Module / köprü)")
    n_layers = _model_n_layers(model)
    if n_layers is not None:
        asiri = [l for l in layer_ids if l >= n_layers]
        if asiri:
            raise ValueError(
                f"katman sınır dışı: {asiri} (n_layers={n_layers})"
            )
    if hasattr(model, "run_with_cache"):
        return _capture_bridge(model, inputs, names, layer_ids, token_mask)
    if site != "resid_post":
        raise ValueError(
            f"HF gizli-durum yolu yalnız site='resid_post' destekler "
            f"(istenilen: {site!r})"
        )
    return _capture_hidden_states(model, inputs, layer_ids, token_mask)


def _flatten_values(arr) -> list[float]:
    if hasattr(arr, "detach"):
        arr = arr.detach().cpu().float()
    if hasattr(arr, "reshape") and hasattr(arr, "tolist"):
        return [float(x) for x in arr.reshape(-1).tolist()]
    flat: list[float] = []

    def _rec(x):
        if isinstance(x, (list, tuple)):
            for y in x:
                _rec(y)
        else:
            flat.append(float(x))

    _rec(arr)
    return flat


def measure_layers(activations: dict) -> dict:
    """Katman başına çift yönlü ölçüm özeti (dual_measure).

    activations: capture_activations çıktısı ({katman: matris}).
    Dönen: {str(katman): {"aktivasyon", "kovaryans", "n"}} — JSON'a
    yazılabilir; collect_reds(measures=...) için doğrudan kullanılır.
    """
    return {
        str(layer): dual_measure(_flatten_values(arr))
        for layer, arr in activations.items()
    }


def load_bridge_model(model_name: str, device: str = "cpu", dtype=None,
                      compatibility: bool = False, load_weights: bool = True):
    """GERÇEK model yükleme yolu (ağ erişimi + disk gerekir — birim testler
    bunu ÇALIŞTIRMAZ).

    TransformerLens 4.0'da HookedTransformer KALDIRILDI; API
    TransformerBridge.boot_transformers(model_name, ...) ile kurulur
    (kaynak: transformer_lens/model_bridge/transformer_bridge.py; bkz.
    docs/source/content/migrating_to_v4.md). HookedTransformer ile aynı
    sayılar için sonuçta enable_compatibility_mode() çağrılmalıdır
    (LayerNorm katlama + ağırlık merkezleme) — compatibility=True bunu yapar.

    load_weights=False: checkpoint yerine rastgele başlatılmış gerçek
    mimari kurar (ağdan ağırlık indirmez; yine de config/tokenizer için
    hub erişimi gerekebilir). Dönen köprü capture_activations ile
    uyumludur (run_with_cache protokolü).
    """
    try:
        from transformer_lens import TransformerBridge
    except ImportError as exc:
        raise RuntimeError("transformer_lens 4.x kurulu değil") from exc
    kwargs: dict = {"load_weights": load_weights}
    if device is not None:
        kwargs["device"] = device
    if dtype is not None:
        kwargs["dtype"] = dtype
    bridge = TransformerBridge.boot_transformers(model_name, **kwargs)
    if compatibility:
        bridge.enable_compatibility_mode()
    return bridge
