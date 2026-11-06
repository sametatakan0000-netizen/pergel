#!/usr/bin/env python3
"""Multi-D weight abliteration CLI (Arditi arXiv:2406.11717 + Multi-D).

Yerel HF safetensors gövdesinden refusal yönlerini tespit eder
(difference-of-means, son-token resid_post) ve residual yazar/okuyucu/
gömme tensörlerine orthogonal projeksiyon uygular. Kaynak gövdeye ve
sinaps dosyalarına ASLA dokunulmaz (GOLDEN-RED): sonuç YENİ bir dizine
yazılır + ablation_manifest.json.

Örnek:
  python3 scripts/ablate_weights.py \\
      --model-dir /mnt/toshiba/eval_models/Qwen_Qwen3-8B \\
      --layers auto --directions 4 \\
      --targets attention_out,mlp_down,embedding_in,embedding_out \\
      --device cpu

Varsayılanlar: --harmful-jsonl /home/pc/mahoraga_davranis_veri/guvenlik_advbench.jsonl,
--harmless-jsonl /home/pc/mahoraga_davranis_veri/dil_karar_banking77.jsonl
(her birinden ilk 64 prompt), --out-dir
/home/pc/mahoraga_adaylar/<model-adı>-abliterated/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# repo kökü sys.path'e: `python3 scripts/ablate_weights.py` için
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mahoraga.weight_ablation import (  # noqa: E402
    DEFAULT_HARMFUL_JSONL,
    DEFAULT_HARMLESS_JSONL,
    DEFAULT_PROMPT_LIMIT,
    DEFAULT_TARGETS,
    apply_ablation,
    default_out_dir,
    detect_directions,
    parse_layers,
    parse_targets,
)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ablate_weights.py",
        description=(
            "Multi-D weight abliteration: refusal yönlerini tespit eder ve "
            "gerçek ağırlık tensörlerine orthogonal projeksiyon uygular. "
            "Kaynak gövde/sinaps asla değiştirilmez (GOLDEN-RED); sonuç "
            "YENİ bir dizine yazılır + ablation_manifest.json."))
    p.add_argument("--model-dir", required=True,
                   help="yerel HF safetensors gövdesi (salt okunur)")
    p.add_argument("--out-dir", default=None,
                   help="çıktı dizini (varsayılan: "
                        "/home/pc/mahoraga_adaylar/<model>-abliterated/)")
    p.add_argument("--harmful-jsonl", default=DEFAULT_HARMFUL_JSONL,
                   help="zararlı prompt JSONL (varsayılan: guvenlik_advbench)")
    p.add_argument("--harmless-jsonl", default=DEFAULT_HARMLESS_JSONL,
                   help="zararsız prompt JSONL (varsayılan: dil_karar_banking77)")
    p.add_argument("--layers", default="auto",
                   help="'auto' veya '4,12' (varsayılan: auto = tüm katmanlar)")
    p.add_argument("--directions", type=int, default=4,
                   help="maksimum AYRI yön sayısı (varsayılan: 4)")
    p.add_argument("--targets", default=None,
                   help="hedef kategoriler CSV (varsayılan: dördü — "
                        + ",".join(DEFAULT_TARGETS) + ")")
    p.add_argument("--device", default="cpu",
                   help="tespit için aygıt (varsayılan: cpu)")
    p.add_argument("--max-prompts", type=int, default=DEFAULT_PROMPT_LIMIT,
                   help="her dosyadan prompt sayısı (varsayılan: 64)")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    out_dir = args.out_dir or default_out_dir(args.model_dir)
    layers = parse_layers(args.layers)
    targets = parse_targets(args.targets)

    directions = detect_directions(
        args.model_dir, args.harmful_jsonl, args.harmless_jsonl,
        layers=layers, n_directions=args.directions,
        device=args.device, max_prompts=args.max_prompts)
    manifest = apply_ablation(args.model_dir, out_dir, directions,
                              targets=targets)
    print(json.dumps({
        "output_dir": manifest["output_dir"],
        "status": manifest["status"],
        "targets": manifest["targets"],
        "selected_layers": directions["selected_layers"],
        "n_directions": directions["n_directions"],
        "prompt_counts": manifest["prompt_counts"],
        "counts": manifest["counts"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
