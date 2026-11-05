from mahoraga.synapse_inventory import classify_key, summarize


def test_classify_moe_gate_up_grouped():
    assert classify_key("model.layers.1.experts.3.mlp.gate_up_proj") == "moe_expert_gate_up"
    assert classify_key("model.layers.1.experts.3.mlp.gate_proj") == "moe_expert_gate"
    assert classify_key("model.layers.1.experts.3.mlp.up_proj") == "moe_expert_up"
    assert classify_key("model.layers.1.experts.3.mlp.down_proj") == "moe_expert_down"


def test_summarize_totals_equal():
    recs = [
        {"key": "model.layers.0.experts.0.mlp.gate_proj", "n_synapses": 1024, "file": "a.safetensors"},
        {"key": "model.layers.0.mlp.down_proj", "n_synapses": 2048, "file": "a.safetensors"},
    ]
    out = summarize(recs)
    total = 1024 + 2048
    assert out["synapse_sum"] == total
    assert out["sum_check"] is True
    assert sum(c["synapses"] for c in out["categories"].values()) == total
    assert out["categories"]["moe_expert_gate"]["synapses"] == 1024
    assert out["categories"]["mlp_down"]["synapses"] == 2048


def test_summarize_role_partition():
    recs = [
        {"key": "embed_tokens.weight", "n_synapses": 40},
        {"key": "score.weight", "n_synapses": 8},
    ]
    out = summarize(recs)
    assert out["synapse_sum"] == 48
    assert out["sum_check"] is True
    assert sum(r["synapses"] for r in out["roles"].values()) == 48
