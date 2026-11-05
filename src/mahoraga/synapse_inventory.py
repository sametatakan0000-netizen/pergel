#!/usr/bin/env python3
"""Mahoraga Faz 1 - Sinaps Envanter Profiler (çevrimdışı anatomı).

Sinaps envanterlerini (tensor_record JSON) anatomik sınıflara ayırır:
"ne nedir" haritası. Birleştirme DEĞİL, sınıflandırma/filtreleme.
Model gövdesi GEREKTİRMEZ — sadece envanter kayıtları okunur.

SOTA dayanağı (2026-11 web doğrulaması):
- MLP alt-katmanları bilgi deposudur, anahtar-değer bellek (~2/3 param)
  (Geva et al. 2021; Meng et al. / ROME 2022).
- Attention bilgiyi yönlendirir, taşımaz; depolama yapmaz.
- Filtre (refusal) tensör değil artık-akış YÖNÜDÜR (Arditi et al. 2024);
  tüm artık-ışak yazan matrislerden (o_proj, down_proj, w2, lm_head) geçer.
  Bu yüzden "residual_writer" kategorisi filtre/yön adayıdır.

Ayrımlaştırma: synapse_profiler.py aktivasyon-seviyesi analizdir
(TransformerLens/SAELens, gövde + GPU); bu modül envanter-seviyesi
anatomidir (gövdesiz, stdlib).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

# Kategori -> birincil rol. "knowledge" = bilgi deposu (MLP/expert),
# "routing" = yönlendirme, "scale" = ölçek, "vocab_io" = sözlük girişi/çıkışı,
# "unknown" = eşleşmeyen.
ROLE_MAP = {
    "embedding_in": "vocab_io",
    "embedding_out": "vocab_io",
    "attention_q": "routing",
    "attention_k": "routing",
    "attention_v": "routing",
    "attention_out": "routing",
    "attention_qkv": "routing",
    "attention_other": "routing",
    "mlp_gate": "knowledge",
    "mlp_up": "knowledge",
    "mlp_down": "knowledge",
    "mlp_other": "knowledge",
    "moe_expert_gate": "knowledge",
    "moe_expert_up": "knowledge",
    "moe_expert_down": "knowledge",
    "moe_expert_other": "knowledge",
    "moe_router": "routing",
    "norm": "scale",
    "mlp_gate_up": "knowledge",
    "moe_expert_gate_up": "knowledge",
    "mtp_head": "vocab_io",
    "hyper_mixer": "routing",
    "vision_tower": "vision",
    "ssm_mixer": "routing",
    "engram_memory": "knowledge",
    "lookup_memory": "knowledge",
    "unknown": "unknown",
}

# İKİNCİL boyut: artık-ışak yazarları. Arditi 2024'te filtre (refusal) yönü,
# artık-ışağa yazan TÜM matrislerden (attn out, MLP out, gömme) orthogonalize
# edilir — lm_head artık-ışağı okur, yazmaz, bu yüzden listede YOK.
# Bu kümeye giren her sinaps "filtre/yön adayı" sayılır.
RESIDUAL_WRITER_CATS = {
    "embedding_in",
    "attention_out",
    "attention_qkv",
    "mlp_down",
    "moe_expert_down",
    "hyper_mixer",
}


def _proj(key: str) -> str:
    """'model.layers.0.mlp.gate_proj.weight' -> 'gate_proj'."""
    parts = key.split(".")
    return parts[-2] if parts[-1] in ("weight", "bias") else parts[-1]


def classify_key(key: str) -> str:
    """Tensör anahtarını anatomik kategoriye çevirir.

    Kural sırası önemli: norm, attn'ten ÖNCE (post_attention_layernorm);
    expert, dense MLP'ten ÖNCE (experts.N.gate_proj).
    # shortcut: yaygın 6 mimari ailesi (Llama/Mistral/DeepSeek/Qwen/Mixtral/GPT2);
    yeni mimari gelirse 'unknown' listesine düşer -> kural ekle, sonra SAE fazı.
    """
    k = key.lower()
    p = _proj(key).lower()

    # görsel kule en başta: visual/merger anahtarları mlp/attn de taşır
    if "visual" in k or "vision" in k or "radio_model" in k:
        return "vision_tower"
    # PLE n-gram arama tablosu — 'ple_embedding' embed kontrolünden ÖNCE
    # yakalanmalı (Engram akrabası koşullu bellek modülü)
    if ".ple." in k or k.startswith("ple."):
        return "lookup_memory"
    # DeepSeek bellek modülü — 'engram.embed.*' adları embed kontrolünden ÖNCE
    # yakalanmalı (yoksa 98B'lik bellek tablosu embedding_in/vocab_io'ya düşer)
    if "engram" in k:
        return "engram_memory"
    if "embed" in k or k.endswith("wte.weight") or "word_embed" in k:
        return "embedding_in"
    if "lm_head" in k or p in ("output", "score"):
        return "embedding_out"
    if "mtp" in k:  # çoklu-token tahmin başlığı (Qwen3-Next/3.5)
        return "mtp_head"
    if "hyper_connection" in k or "hyper_mixer" in k:
        return "hyper_mixer"
    if p == "shared_expert_gate":
        return "moe_router"

    is_expert = ".experts." in k or "shared_expert" in k
    if is_expert:
        if p in ("w1", "gate_proj", "gate"):
            return "moe_expert_gate"
        if p in ("w3", "up_proj", "up"):
            return "moe_expert_up"
        if p in ("w2", "down_proj", "down"):
            return "moe_expert_down"
        if p == "gate_up_proj":  # birleşik SwiGLU (Qwen3.8 uzmanları)
            return "moe_expert_gate_up"
        return "moe_expert_other"

    # çıplak 'gate' = yönlendirici (Mixtral block_sparse_moe.gate,
    # DeepSeek mlp.gate); SwiGLU kapısı 'gate_proj' adıyla ayrıldı
    if p in ("gate", "router") and ("moe" in k or "mlp" in k):
        return "moe_router"

    if "norm" in k:
        return "norm"

    if "attn" in k or "attention" in k:
        if p in ("q_proj", "query", "wq", "q"):
            return "attention_q"
        if p in ("k_proj", "key", "wk", "k"):
            return "attention_k"
        if p in ("v_proj", "value", "wv", "v"):
            return "attention_v"
        if p in ("o_proj", "out_proj", "dense", "wo", "c_proj"):
            return "attention_out"
        if p in ("query_key_value", "c_attn", "wqkv", "qkv_proj", "in_proj_qkv"):
            return "attention_qkv"
        return "attention_other"

    if "mixer" in k:  # Mamba/SSM bloğu (Nemotron-Bolt)
        return "ssm_mixer"

    if "mlp" in k or "ffn" in k or "feed_forward" in k:
        if p in ("gate_proj", "w1", "gate"):
            return "mlp_gate"
        if p in ("up_proj", "w3", "up"):
            return "mlp_up"
        if p in ("down_proj", "w2", "down"):
            return "mlp_down"
        if p == "gate_up_proj":  # birleşik SwiGLU (Phi-4)
            return "mlp_gate_up"
        return "mlp_other"

    return "unknown"


def summarize(records: list[dict]) -> dict:
    """Tensor kayıtlarını kategori/rol bazında toplar, anomalleri işaretler."""
    categories: dict = defaultdict(lambda: {"tensors": 0, "synapses": 0})
    roles: dict = defaultdict(lambda: {"tensors": 0, "synapses": 0})
    residual_writers = {"tensors": 0, "synapses": 0}
    by_hash: dict = defaultdict(list)
    zero_magnitude = []
    unknown_keys = []
    metadata_only = 0
    synapse_sum = 0

    for rec in records:
        cat = classify_key(rec["key"])
        role = ROLE_MAP[cat]
        n = int(rec["n_synapses"])
        synapse_sum += n
        categories[cat]["tensors"] += 1
        categories[cat]["synapses"] += n
        roles[role]["tensors"] += 1
        roles[role]["synapses"] += n
        if cat in RESIDUAL_WRITER_CATS:
            residual_writers["tensors"] += 1
            residual_writers["synapses"] += n
        if "hash" in rec:
            by_hash[rec["hash"]].append(rec["key"])
        else:
            metadata_only += 1  # yalnızca şekil/envanter kaydı (hash+magnitude yok)
        if rec.get("magnitude") is not None and not rec["magnitude"]:
            zero_magnitude.append(rec["key"])
        if cat == "unknown":
            unknown_keys.append(rec["key"])

    dup_hash_pairs = [
        sorted(keys) for keys in by_hash.values() if len(keys) > 1
    ]
    return {
        "categories": dict(categories),
        "roles": dict(roles),
        "residual_writers": residual_writers,
        "synapse_sum": synapse_sum,
        "sum_check": True,  # üst seviye doğrulama profile_inventory'de yapılır
        "dup_hash_pairs": sorted(dup_hash_pairs),
        "zero_magnitude": zero_magnitude,
        "metadata_only": metadata_only,
        "unknown_keys": unknown_keys,
    }


def profile_inventory(path: str | Path) -> dict:
    """Bir *_synapses.json dosyasını profiller."""
    data = json.loads(Path(path).read_text())
    s = summarize(data["tensors"])
    s["model"] = data.get("model", Path(path).stem)
    s["file_synapses"] = int(data.get("total_synapses", 0))
    s["sum_check"] = (s["synapse_sum"] == s["file_synapses"])
    return s


def profile_all(directory: str | Path) -> dict:
    """Dizindeki tüm *_synapses.json dosyalarını profiller, küresel toplam verir."""
    models = {}
    global_roles: dict = defaultdict(lambda: {"tensors": 0, "synapses": 0})
    global_cats: dict = defaultdict(lambda: {"tensors": 0, "synapses": 0})
    grand_total = 0
    for p in sorted(Path(directory).glob("*_synapses.json")):
        s = profile_inventory(p)
        models[s["model"]] = s
        grand_total += s["synapse_sum"]
        for role, agg in s["roles"].items():
            global_roles[role]["tensors"] += agg["tensors"]
            global_roles[role]["synapses"] += agg["synapses"]
        for cat, agg in s["categories"].items():
            global_cats[cat]["tensors"] += agg["tensors"]
            global_cats[cat]["synapses"] += agg["synapses"]
    return {
        "n_models": len(models),
        "grand_total_synapses": grand_total,
        "global_roles": dict(global_roles),
        "global_categories": dict(global_cats),
        "models": models,
    }


if __name__ == "__main__":
    import sys
    out = profile_all(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(json.dumps(out, indent=2, ensure_ascii=False))
