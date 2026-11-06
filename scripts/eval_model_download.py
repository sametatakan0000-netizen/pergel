#!/usr/bin/env python3
"""Davranış ölçümü için model gövdesi indirici — HF REST + curl (xet/CAS takılmasına dayanıklı).

Kullanım:
  python3 eval_model_download.py --repo Qwen/Qwen3-8B --dest /mnt/toshiba/eval_models --rate 12M

Kurallar (llm-pipeline-ops):
- Dosya listesi: GET /api/models/{id}?blobs=true (ön kontrol: repo id doğrulaması).
- Çift-format koruması: shard'lar varsa consolidated.safetensors atlanır; .gguf/.bin alınmaz.
- curl -C - ile resume; .curlpart yan dosyası = eksik işaretçisi (tamamlanınca rename).
- --limit-rate ile bant kotası (kullanıcı oturumu korunur).
- Bittiğinde boyut doğrulaması yapılır; eksik dosya = hata (exit 1).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

FILE_RE = re.compile(r".*\.(safetensors|json|txt|model)$")
SHARD_RE = re.compile(r"model-\d{5}-of-\d{5}\.safetensors$")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def list_files(repo: str) -> dict[str, int | None]:
    url = f"https://huggingface.co/api/models/{repo}?blobs=true"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    names = {s["rfilename"]: s.get("size") for s in d.get("siblings", []) if FILE_RE.match(s["rfilename"])}
    if any(SHARD_RE.match(n) for n in names):
        names.pop("consolidated.safetensors", None)
    return names


def complete(path: str, size: int | None) -> bool:
    return os.path.exists(path) and (size is None or os.path.getsize(path) == size)


def download(repo: str, dest: str, rate: str | None) -> None:
    local_dir = os.path.join(dest, re.sub(r"[^a-zA-Z0-9_-]", "_", repo))
    os.makedirs(local_dir, exist_ok=True)
    names = list_files(repo)
    remaining = {n: s for n, s in names.items() if not complete(os.path.join(local_dir, n), s)}
    total = sum(s or 0 for s in remaining.values())
    log(f"{repo}: {len(names)} dosya, {len(remaining)} eksik, {total/1e9:.1f} GB")
    if not remaining:
        log("zaten tam — atlandı")
        return
    base = f"https://huggingface.co/{repo}/resolve/main"
    tok = os.environ.get("HF_TOKEN")
    for i, (n, sz) in enumerate(sorted(remaining.items()), 1):
        target = os.path.join(local_dir, n)
        part = target + ".curlpart"
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        log(f"({i}/{len(remaining)}) {n} ({(sz or 0)/1e9:.2f} GB)")
        ok = False
        for attempt in range(1, 31):
            cmd = ["curl", "-sSL", "--fail", "--connect-timeout", "30",
                   "--speed-limit", "1000", "--speed-time", "120",
                   "-C", "-", "-o", part, f"{base}/{n}"]
            if rate:
                cmd[1:1] = ["--limit-rate", rate]
            if tok:
                cmd += ["-H", f"Authorization: Bearer {tok}"]
            r = subprocess.run(cmd)
            if r.returncode == 0 and (sz is None or os.path.getsize(part) == sz):
                os.replace(part, target)
                ok = True
                break
            log(f"  deneme {attempt} basarisiz (rc={r.returncode}) — 5s bekleyip tekrar")
            time.sleep(5)
        if not ok:
            log(f"  ❌ {n} indirilemedi (30 deneme)")
            sys.exit(1)
    # doğrulama
    bad = [n for n, s in names.items() if not complete(os.path.join(local_dir, n), s)]
    if bad:
        log(f"❌ eksik kalan dosya: {bad}")
        sys.exit(1)
    log(f"✅ {repo} tam: {local_dir} ({len(names)} dosya dogrulandi)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dest", default="/mnt/toshiba/eval_models")
    ap.add_argument("--rate", default=None, help="curl --limit-rate, ör. 12M")
    a = ap.parse_args()
    if not os.path.ismount("/mnt/toshiba"):
        raise RuntimeError("Toshiba mount'lu değil — /mnt/toshiba")
    download(a.repo, a.dest, a.rate)
