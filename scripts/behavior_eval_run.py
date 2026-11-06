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

Alternatif motor: --taban-url ile OpenAI-uyumlu sunucu (llama.cpp / vLLM vb.)
kullanılır — model her çalıştırmada yeniden yüklenmez (sıcak sunucu). Bu yol için
--motor-ad zorunlu, --model-dir yasaktır; run_id "_openai" eki alır (checkpoint
çakışması olmaz), quant alanı "gguf-openai" olur.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.request
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


class OpenAIEngine:
    """OpenAI-uyumlu /chat/completions sunucu motoru (llama.cpp / vLLM vb.).

    Isıtılmış sunucu üzerinden çalışır; her çalıştırmada model yüklemesi gerekmez.
    generate(istemler) her istem için bir POST atar (şimdilik toplu değil),
    choices[0].message.content değerlerini istem sırasıyla döndürür.
    """

    DENEME = 3
    BEKLEME = 2.0  # saniye — 5xx/URLError geri çekilmesi

    def __init__(self, base_url: str, model_name: str, max_new: int):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model_name = model_name
        self.max_new = max_new

    def generate(self, prompts: list[str]) -> list[str]:
        return [self._istek(istem) for istem in prompts]

    def _istek(self, prompt: str) -> str:
        govde = json.dumps({
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_new,
            "temperature": 0,
            "top_p": 1,
        }).encode("utf-8")
        istek = urllib.request.Request(
            self.url, data=govde,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        for deneme in range(self.DENEME):
            if deneme:
                time.sleep(self.BEKLEME)
            try:
                with urllib.request.urlopen(istek, timeout=120) as yanit:
                    return self._coz(yanit.read())
            except urllib.error.HTTPError as e:
                metin = e.read().decode("utf-8", "replace")
                e.close()
                if 500 <= e.code < 600 and deneme < self.DENEME - 1:
                    continue  # 5xx: geri çekilip tekrar dene
                raise RuntimeError(f"OpenAI sunucu hatası HTTP {e.code}: {metin}") from e
            except urllib.error.URLError as e:
                if deneme < self.DENEME - 1:
                    continue  # bağlantı hatası: geri çekilip tekrar dene
                raise RuntimeError(f"OpenAI sunucuya ulaşılamadı: {e}") from e
        raise RuntimeError("OpenAI sunucu hatası: denemeler tükendi")  # pragma: no cover

    @staticmethod
    def _coz(govde: bytes) -> str:
        try:
            return json.loads(govde.decode("utf-8"))["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"OpenAI yanıt gövdesi çözülemedi: {govde[:500]!r}") from e


def arguman_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--taban-url", default=None,
                    help="OpenAI-uyumlu sunucu taban adresi (örn. http://127.0.0.1:8001/v1)")
    ap.add_argument("--motor-ad", default=None,
                    help="Sunucuya gönderilen model adı (--taban-url ile zorunlu)")
    ap.add_argument("--davranis", required=True, choices=["dil_karar", "guvenlik"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-new-tokens", type=int, default=None)
    ap.add_argument("--quant", choices=["4bit"], default=None)
    ap.add_argument("--max-gpu-gb", type=int, default=4)
    ap.add_argument("--max-cpu-gb", type=int, default=22)
    ap.add_argument("--protokol-notu", default="")
    ap.add_argument("--checkpoint", type=Path, default=None)
    return ap


def argumanlar_dogrula(args) -> None:
    """Motor yolu kuralları: --taban-url var mı, yok mu? İhlalde ValueError.

    - --taban-url verildiyse: --motor-ad zorunlu, --model-dir yasak.
    - --taban-url yoksa (HF yolu): --model-dir ve --repo zorunlu.
    """
    hatalar = []
    if args.taban_url:
        if not args.motor_ad:
            hatalar.append("--taban-url ile --motor-ad zorunludur")
        if args.model_dir:
            hatalar.append("--taban-url ile --model-dir birlikte verilemez")
    else:
        if not args.model_dir:
            hatalar.append("--taban-url yoksa --model-dir zorunludur")
        if not args.repo:
            hatalar.append("--taban-url yoksa --repo zorunludur")
    if hatalar:
        raise ValueError("; ".join(hatalar))


def run_id_hesapla(args) -> str:
    """Sunucu yolunda run_id '_openai' eki alır — HF checkpoint'leriyle çakışmaz."""
    if args.taban_url:
        ham = f"{args.motor_ad}_{args.davranis}_openai"
    else:
        ham = f"{args.repo}_{args.davranis}"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", ham)


def main() -> None:
    ap = arguman_parser()
    args = ap.parse_args()
    try:
        argumanlar_dogrula(args)
    except ValueError as e:
        ap.error(str(e))

    max_new = args.max_new_tokens or (16 if args.davranis == "dil_karar" else 128)
    run_id = run_id_hesapla(args)
    ckpt_yolu = args.checkpoint or (TAHMINLER_DIR / f"{run_id}.jsonl")
    SONUCLAR_DIR.mkdir(parents=True, exist_ok=True)
    TAHMINLER_DIR.mkdir(parents=True, exist_ok=True)

    ornekler = load_suite(args.davranis)
    gecmis = checkpoint_yukle(ckpt_yolu)
    print(f"[hazir] ornek={len(ornekler)} resume={len(gecmis)} run_id={run_id}", flush=True)

    t0 = time.time()
    if args.taban_url:
        engine = OpenAIEngine(args.taban_url, args.motor_ad, max_new)
        model_ad = args.motor_ad

        def generate(prompt: dict) -> str:
            # run_eval tek prompt(dict)->str bekler; sunucu motora düz metin gider
            return engine.generate([prompt["system"] + "\n" + prompt["user"]])[0]

        print(f"[motor] sunucu motoru hazır ({args.taban_url}) — ölçüm başlıyor", flush=True)
    else:
        engine = HFEngine(args.model_dir, max_new, args.quant, args.max_gpu_gb, args.max_cpu_gb)
        model_ad = args.repo
        generate = engine.generate
        print(f"[motor] yüklendi ({time.time() - t0:.0f}s) — ölçüm başlıyor", flush=True)

    ckpt = ckpt_yolu.open("a")

    def on_pred(sid: str, pred: str) -> None:
        ckpt.write(json.dumps({"id": sid, "pred": pred}, ensure_ascii=False) + "\n")
        ckpt.flush()

    try:
        sonuc = run_eval(
            args.davranis, ornekler, model_ad, generate,
            limit=args.limit, protokol_notu=args.protokol_notu,
            gecmis=gecmis, on_pred=on_pred,
        )
    finally:
        ckpt.close()

    sonuc["sure_saniye"] = round(time.time() - t0, 1)
    sonuc["quant"] = "gguf-openai" if args.taban_url else args.quant
    (SONUCLAR_DIR / f"{run_id}.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=2))
    satir = kanit_row(sonuc)
    mevcut = json.loads(KANITLAR_YOLU.read_text()) if KANITLAR_YOLU.exists() else []
    mevcut.append(satir)
    KANITLAR_YOLU.write_text(json.dumps(mevcut, ensure_ascii=False, indent=2))
    print(json.dumps(sonuc, ensure_ascii=False, indent=2), flush=True)
    print(f"[bitis] kanıt satırı -> {KANITLAR_YOLU}", flush=True)


if __name__ == "__main__":
    main()
