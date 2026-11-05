"""Filtre Yüzeyi Envanteri — Faz 2 (Filtre Dedektörü), Adım 1.

Amaç: anatomik envanterdeki her model için FİLTRE YÜZEYİ tensörlerini
işaretleyip HF `index.json` shard eşlemesiyle bir "alışveriş listesi"
üretmek: hangi shard, kaç tensör, kaç sinaps — gövde indirmeden.

Kural (Arditi + kamuya açık abliteration reçeteleri):
filtre yüzeyi = artık akışa veya kelime uzayına YAZAN kapılar.
Yönlendirme/gate kapıları (attention q/k/v, MoE router, PLE key_proj,
engram k_weight), normlar ve görsel kuleler yazı YAZMAZ; yüzeyde
değildir. Bellek modüllerinde yalnız yük (payload) yolu yüzeydedir
(PLE value_proj/conv1d, engram v_*), kapı yolu değil.

Girdi: /home/pc/mahoraga_synapses/*_synapses.json (envanter) +
HuggingFace model.safetensors.index.json (weight_map: tensör → shard).
Çıktı: filtre yüzeyi raporu + indirme planı (tam gövde GEREKMEZ).
"""
from __future__ import annotations

# Yüzeydeki kategoriler: artık-ışak ve kelime yazarları
# (anatomik sınıflandırıcının gerçek kategori adlarıyla).
WRITER_CATEGORIES = {
    "attention_out",   # attention/hyper çıkış projeksiyonları (artık yazar)
    "mlp_down",        # MLP değeri artık akışa yazar (ROME)
    "moe_expert_down",  # MoE uzman değeri artık akışa yazar
    "embedding_in",    # kelime → artık (satır-uzayı düzenleme hedefi)
    "embedding_out",   # lm_head: artık → kelime (çıkış yönü hedefi)
    "mtp_head",        # çoklu-token tahmin başlığı (lm_head aynası)
}

UNKNOWN_SHARD = "index_bilinmiyor"


def is_filter_surface(key: str, category: str | None = None) -> bool:
    """Tensör filtre yüzeyinde mi?

    Kategori verilmezse anatomik sınıflandırıcıdan türetilir.
    """
    if category is None:
        from src.mahoraga.synapse_inventory import classify_key
        category = classify_key(key)
    if category == "vision_tower":
        return False  # metin yolunun dışı
    if category in WRITER_CATEGORIES:
        return True
    if category == "lookup_memory":
        # PLE: yalnız yük yolu (value_proj, conv1d); kapı yolu değil
        return ("value_proj" in key or "conv1d" in key) and "key_proj" not in key
    if category == "engram_memory":
        # Engram: yalnız V (yük) yolu; K (kapı) yolu değil
        return ".v_weight" in key or ".v_bias" in key
    if category == "ssm_mixer":
        return "out_proj" in key  # SSM'de yalnız çıkış projeksiyonu yazar
    return False


def surface_for_model(record: dict) -> dict:
    """Bir modelin sinaps kaydından filtre yüzeyi raporu üretir.

    Kayıttaki n_synapses toplamı ile yeniden hesaplanan toplam eşit
    olmalıdır (sum_check) — envanter bütünlüğü korunur.
    """
    tensors = record.get("tensors", [])
    total = sum(t.get("n_synapses", 0) for t in tensors)
    surface = [
        {"key": t["key"], "category": None, "n_synapses": t.get("n_synapses", 0),
         "hash": t.get("hash"), "magnitude": t.get("magnitude")}
        for t in tensors if is_filter_surface(t["key"])
    ]
    from src.mahoraga.synapse_inventory import classify_key
    for entry in surface:
        entry["category"] = classify_key(entry["key"])
    surface_syn = sum(e["n_synapses"] for e in surface)
    declared = record.get("synapse_count", total)
    return {
        "model": record.get("model"),
        "tensors": surface,
        "surface_tensor_count": len(surface),
        "surface_synapses": surface_syn,
        "total_tensor_count": len(tensors),
        "total_synapses": total,
        "sum_check": (surface_syn <= total) and (declared == total),
    }


def _normalize_key(key: str) -> str:
    """HF index anahtarı ↔ envanter anahtarı normalizasyonu.

    "model." öneki ve ".weight"/".bias" soneki kayıtlar arasında
    tutarsız gelebilir; çekirdek ad üzerinden eşleştirilir.
    """
    k = key
    while k.startswith("model."):
        k = k[len("model."):]
    for suffix in (".weight", ".bias"):
        if k.endswith(suffix):
            k = k[: -len(suffix)]
    return k


def attach_shard(surface: dict, weight_map: dict) -> dict:
    """HF index.json weight_map'ini yüzey tensörlerine iliştirir.

    Eşleşme normalleştirilmiş anahtarlar üzerinden yapılır.
    """
    normalized = {_normalize_key(k): v for k, v in weight_map.items()}
    for entry in surface.get("tensors", []):
        entry["shard"] = normalized.get(_normalize_key(entry["key"]), UNKNOWN_SHARD)
    return surface


def download_plan(surface: dict) -> dict:
    """Yüzey tensörlerinin shard'larına göre indirme planı.

    Shard = ~5 GB'lık dilim; yüzey genelde tüm modelin küçük bir
    alt kümesini tutan birkaç dilime düşer.
    """
    shards: dict = {}
    for entry in surface.get("tensors", []):
        shard = entry.get("shard", UNKNOWN_SHARD)
        info = shards.setdefault(shard, {"tensors": 0, "synapses": 0})
        info["tensors"] += 1
        info["synapses"] += entry.get("n_synapses", 0)
    return {
        "model": surface.get("model"),
        "shards": shards,
        "total_download_shards": len(shards),
    }


def build_report(entries: list) -> dict:
    """(repo, record, weight_map) üçlülerinden toplu rapor üretir."""
    models = {}
    tot_surface = tot_total = 0
    for repo, record, weight_map in entries:
        rep = attach_shard(surface_for_model(record), weight_map)
        rep["repo"] = repo
        rep["download_plan"] = download_plan(rep)
        models[record.get("model") or repo] = rep
        tot_surface += rep["surface_synapses"]
        tot_total += rep["total_synapses"]
    return {
        "models": models,
        "totals": {
            "models": len(models),
            "total_synapses": tot_total,
            "surface_synapses": tot_surface,
            "surface_share_pct": (tot_surface * 100.0 / tot_total) if tot_total else 0.0,
        },
        "sum_check": all(m["sum_check"] for m in models.values()),
    }