#!/usr/bin/env python3
"""Yerel davranış ölçüm çalıştırıcı — indirilmiş safetensors gövdeyle davranış skoru üretir.

Kullanım:
  python3 scripts/behavior_eval_run.py \
      --model-dir /mnt/toshiba/eval_models/Qwen_Qwen3-8B --repo Qwen/Qwen3-8B \
      --davranis dil_karar --max-gpu-gb 4

Güvenlik: tek günlük doğruluk için tasarlandı —
- checkpoint: her tahmin anında jsonl'e append; --checkpoint verilirse yarım kalmış
  tur oradan devam eder (motor o ornekler için çağrılmaz).
- sonuç: /home/pc/mahoraga_lokal_sonuclar/<run_id>.json
- kanıt satırı: /home/pc/mahoraga_lokal_kanitlari.json listesine append
  (behavior_score_matrix kanıt şeması: model/davranis/benchmark/skor/kaynak/protokol).

Motor: transformers (greedy, do_sample=False — deterministik). Qwen3 için thinking
kapalı denenir; chat template yoksa düz metin prompt kullanılır.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.mahoraga.behavior_local_eval import (  # noqa: E402
    kanit_row,
    load_suite,
    run_eval,
)

SONUCLAR_DIR = Path("/home/pc/mahoraga_lokal_sonuclar")
KANITLAR_YOLU = Path("/home/pc/mahoraga_lokal_kanitlari.json")
TAHMINLER_DIR = Path("/home/pc/mahoraga_davranis_tahminleri")


class HFEngine:
    def __init__(self, model_dir: str, max_new_tokens: int, quant: str | None,
                 gpu_gb: int, cpu_gb: int):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        kw = dict(
            local_files_only=True,
            device_map="auto",
            max_memory={0: f"{gpu_gb}GiB", "cpu": f"{cpu_gb}GiB"},
        )
        if quant == "4bit":
            from transformers import BitsAndBytesConfig

            kw["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
                # GPU'ya sığmayan modüller CPU'ya fp32 olarak taşınabilsin (bnb aksi halde reddeder)
                llm_int8_enable_fp32_cpu_offload=True,
            )
        else:
            kw["torch_dtype"] = torch.bfloat16
        self.model = AutoModelForCausalLM.from_pretrained(model_dir, **kw)
        self.model.eval()
        self.max_new_tokens = max_new_tokens

    def generate(self, prompt: dict) -> str:
        torch = self.torch
        messages = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ]
        if getattr(self.tok, "chat_template", None):
            # transformers 5.x: chat_template_kwargs sessizce yutulabiliyor.
            # Kwarg'in gercekten etkili olup olmadigini temel render ile
            # karsilastirarak anla (yazma hatti <|...|> token'larini yuttugu
            # icin isaret metni kullanilmaz).
            temel = self.tok.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False
            )
            ids = None
            for kw in ({"enable_thinking": False}, {"chat_template_kwargs": {"enable_thinking": False}}):
                try:
                    onizleme = self.tok.apply_chat_template(
                        messages, add_generation_prompt=True, tokenize=False, **kw
                    )
                except (TypeError, ValueError):
                    continue
                if onizleme == temel:
                    continue  # kwarg yutuldu
                ids = self.tok(onizleme, return_tensors="pt", add_special_tokens=False)
                break
            if ids is None:
                # hicbir kwarg islevlenmediyse /no_think ile model tarafinda kapat
                msgs2 = [dict(m) for m in messages]
                msgs2[-1]["user"] = msgs2[-1]["user"] + chr(10) + "/no_think"
                ids = self.tok.apply_chat_template(
                    msgs2, add_generation_prompt=True, return_tensors="pt"
                )
        else:
            ids = self.tok(prompt["system"] + "\n" + prompt["user"], return_tensors="pt").input_ids
        if not hasattr(ids, "shape"):
            # transformers 5.x: apply_chat_template BatchEncoding döner (input_ids + attention_mask)
            ids = ids["input_ids"]
        ids = ids.to(self.model.device if hasattr(self.model, "device") else next(self.model.parameters()).device)
        with torch.no_grad():
            out = self.model.generate(
                ids, max_new_tokens=self.max_new_tokens, do_sample=False,
                pad_token_id=self.tok.eos_token_id,
            )
        return self.tok.decode(out[0][ids.shape[-1]:], skip_special_tokens=True).strip()


def checkpoint_yukle(yol: Path) -> dict:
    if not yol.exists():
        return {}
    gecmis = {}
    for satir in yol.read_text().splitlines():
        if satir.strip():
            kayit = json.loads(satir)
            gecmis[kayit["id"]] = kayit["pred"]
    return gecmis


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--davranis", required=True, choices=["dil_karar", "guvenlik"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-new-tokens", type=int, default=None)
    ap.add_argument("--quant", choices=["4bit"], default=None)
    ap.add_argument("--max-gpu-gb", type=int, default=4)
    ap.add_argument("--max-cpu-gb", type=int, default=22)
    ap.add_argument("--protokol-notu", default="")
    ap.add_argument("--checkpoint", type=Path, default=None)
    args = ap.parse_args()

    max_new = args.max_new_tokens or (16 if args.davranis == "dil_karar" else 128)
    run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{args.repo}_{args.davranis}")
    ckpt_yolu = args.checkpoint or (TAHMINLER_DIR / f"{run_id}.jsonl")
    SONUCLAR_DIR.mkdir(parents=True, exist_ok=True)
    TAHMINLER_DIR.mkdir(parents=True, exist_ok=True)

    ornekler = load_suite(args.davranis)
    gecmis = checkpoint_yukle(ckpt_yolu)
    print(f"[hazir] ornek={len(ornekler)} resume={len(gecmis)} run_id={run_id}", flush=True)

    t0 = time.time()
    engine = HFEngine(args.model_dir, max_new, args.quant, args.max_gpu_gb, args.max_cpu_gb)
    print(f"[motor] yüklendi ({time.time() - t0:.0f}s) — ölçüm başlıyor", flush=True)

    ckpt = ckpt_yolu.open("a")

    def on_pred(sid: str, pred: str) -> None:
        ckpt.write(json.dumps({"id": sid, "pred": pred}, ensure_ascii=False) + "\n")
        ckpt.flush()

    try:
        sonuc = run_eval(
            args.davranis, ornekler, args.repo, engine.generate,
            limit=args.limit, protokol_notu=args.protokol_notu,
            gecmis=gecmis, on_pred=on_pred,
        )
    finally:
        ckpt.close()

    sonuc["sure_saniye"] = round(time.time() - t0, 1)
    sonuc["quant"] = args.quant
    (SONUCLAR_DIR / f"{run_id}.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=2))
    satir = kanit_row(sonuc)
    mevcut = json.loads(KANITLAR_YOLU.read_text()) if KANITLAR_YOLU.exists() else []
    mevcut.append(satir)
    KANITLAR_YOLU.write_text(json.dumps(mevcut, ensure_ascii=False, indent=2))
    print(json.dumps(sonuc, ensure_ascii=False, indent=2), flush=True)
    print(f"[bitis] kanıt satırı -> {KANITLAR_YOLU}", flush=True)


if __name__ == "__main__":
    main()
