"""Faz-C sinaps shard toplayıcı — kazanan mevki tensörleri (Σw·v hammaddesi).

Montaj manifestindeki kazanan sinapsların GERÇEK tensörlerini toplar:

  1. model.safetensors.index.json weight_map -> mevki-key -> shard eşlemesi
     (çift-format repolarda index.json weight_map GERÇEK dosya listesidir)
  2. Yalnız kazanan anahtarları içeren shard'lar indirilir (Toshiba çalışma
     kütüphanesi — portabilite ilkesi, plan §7.2)
  3. İndirilen shard'ların TÜM anahtarları için hash backfill
     (96.085 eksik kayıt — ek indirme yok, zaten gelen shard'lardan)
  4. Kazanan tensörler safetensors olarak 4 kopya yedeklenir (ALTIN-KIRMIZI)
  5. Shard gövdeleri silinir (sinaps çıkarıldı, gövde geçici)

STREAMING KURALI (101 GB shard dersi): safe_open().get_tensor() ve mmap dev
tensörlerde ENOMEM'e düşer. Hash ve çıkarım dosya baytları üzerinden
parça parça (chunked) yapılır; tensör ASLA RAM'e yüklenmez.

Kullanım:
  python3 fazc_shard_collect.py --dry-run                    # depolama planı
  python3 fazc_shard_collect.py --model REPO_ID              # tek model
  python3 fazc_shard_collect.py --all                        # tamamı (ön-sıra: kod)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import time
from pathlib import Path

# IDM mantığı: hf_transfer paralel parça indirme (hf_hub_download hızlandırması)
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")  # yeni Xet yolu (hf_transfer deprecated)

MANIFEST = "/home/pc/mahoraga_montaj_manifest.json"
WORK = Path("/mnt/toshiba/mahoraga/fazc_shards")  # geçici shard çalışma kütüphanesi
WINNERS_ROOT = Path("/home/pc/mahoraga_montaj/winners")
BACKUP_DIRS = [
    Path("/home/pc/mahoraga_synapses"),
    Path("/home/pc/synapse_backups_safe"),
    Path("/home/pc/backup_mahoraga/synapse_backups"),
    Path("/mnt/toshiba/mahoraga/synapse_backups"),
]
SYNAPSE_JSON_DIRS = BACKUP_DIRS  # *_synapses.json hash backfill de 4 kopya

CHUNK = 64 << 20  # 64 MB akış penceresi
DTYPE_MAP = {"BF16": "torch.bfloat16", "F32": "torch.float32", "F16": "torch.float16",
             "F64": "torch.float64", "I64": "torch.int64", "I32": "torch.int32",
             "I16": "torch.int16", "I8": "torch.int8", "U8": "torch.uint8", "BOOL": "bool"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_winners() -> list[dict]:
    m = json.load(open(MANIFEST))
    out = []
    for behavior, blk in m["davranislar"].items():
        for rec in blk["sinapslar"]:
            r = dict(rec)
            r["behavior"] = behavior
            out.append(r)
    return out


def repo_file_sizes(repo_id: str) -> dict:
    from huggingface_hub import HfApi

    info = HfApi().model_info(repo_id, files_metadata=True)
    return {s.rfilename: (s.size or 0) for s in info.siblings}


def load_weight_map(repo_id: str) -> dict | None:
    from huggingface_hub import hf_hub_download

    try:
        p = hf_hub_download(repo_id, "model.safetensors.index.json")
        return json.load(open(p)).get("weight_map", {})
    except Exception:
        return None


def plan_for_model(repo_id: str, winners: list[dict]) -> dict:
    """Kazanan anahtarlar -> gerekli shard'lar + indirme boyutu."""
    sizes = repo_file_sizes(repo_id)
    st_files = {n: s for n, s in sizes.items() if n.endswith(".safetensors")}
    wm = load_weight_map(repo_id)
    keys = [w["key"] for w in winners]
    if wm:
        needed = sorted({wm[k] for k in keys if k in wm})
        missing = [k for k in keys if k not in wm]
    else:
        needed = sorted(st_files)  # tek dosya / index yok: hepsi gerekli
        missing = []
    return {
        "repo_id": repo_id,
        "n_winners": len(keys),
        "winner_keys": keys,
        "needed_shards": needed,
        "download_bytes": sum(st_files.get(n, 0) for n in needed),
        "total_repo_bytes": sum(st_files.values()),
        "keys_not_in_weightmap": missing,
    }


# ---------- STREAMING safetensors yardımcıları (mmap'siz, RAM'siz) ----------

def read_st_header(fp) -> dict:
    """safetensors başlığını ayrıştır: {key: {dtype, shape, start, end}}."""
    fp.seek(0)
    n = struct.unpack("<Q", fp.read(8))[0]
    header = json.loads(fp.read(n))
    base = 8 + n
    out = {}
    for key, v in header.items():
        if key == "__metadata__":
            continue
        s, e = v["data_offsets"]
        out[key] = {"dtype": v["dtype"], "shape": v["shape"],
                    "start": base + s, "end": base + e}
    return out


def hash_range(fp, start: int, end: int) -> str:
    """Dosya aralığının sha256'sı — parça parça okuma, RAM'e yükleme yok."""
    h = hashlib.sha256()
    fp.seek(start)
    left = end - start
    while left > 0:
        b = fp.read(min(CHUNK, left))
        if not b:
            break
        h.update(b)
        left -= len(b)
    return h.hexdigest()


def extract_winner(fp, info: dict, key: str, outp: Path) -> int:
    """Tensörü ham baytlarıyla yeni safetensors dosyasına kopyalar (kayıpsız)."""
    nbytes = info["end"] - info["start"]
    hdr = {key: {"dtype": info["dtype"], "shape": info["shape"],
                 "data_offsets": [0, nbytes]}}
    hb = json.dumps(hdr).encode()
    with open(outp, "wb") as out:
        out.write(struct.pack("<Q", len(hb)))
        out.write(hb)
        fp.seek(info["start"])
        left = nbytes
        while left > 0:
            b = fp.read(min(CHUNK, left))
            out.write(b)
            left -= len(b)
    return nbytes


def download_shard(repo_id: str, shard: str, work_dir: Path) -> Path:
    """IDM mantığı: aria2c 16 bağlantılı paralel indirme; olmazsa hf_hub_download."""
    dst = work_dir / shard
    ctrl = dst.parent / (dst.name + ".aria2")  # yarım indirme kontrol dosyası
    if dst.exists() and not ctrl.exists():
        return dst  # tamamlanmış
    dst.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("aria2c"):
        url = f"https://huggingface.co/{repo_id}/resolve/main/{shard}"
        cmd = ["aria2c", "-x", "16", "-s", "16", "-k", "4M", "-c",
               "--console-log-level=warn", "--summary-interval=0",
               "--file-allocation=none", "--auto-file-renaming=false",
               "-d", str(dst.parent), "-o", dst.name, url]
        token = os.environ.get("HF_TOKEN")
        if token:
            cmd += ["--header", f"Authorization: Bearer ***"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and dst.exists() and not ctrl.exists():
            return dst
        log(f"    ⚠️ aria2c başarısız (rc={r.returncode}), hf_hub_download'a düşüldü")
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(repo_id, shard, local_dir=str(work_dir)))


def collect_model(repo_id: str, winners: list[dict]) -> dict:
    plan = plan_for_model(repo_id, winners)
    win_by_key = {w["key"]: w for w in winners}
    model_dir = WINNERS_ROOT / repo_id.replace("/", "__")
    model_dir.mkdir(parents=True, exist_ok=True)
    work_dir = WORK / repo_id.replace("/", "__")
    work_dir.mkdir(parents=True, exist_ok=True)

    result = {"repo_id": repo_id, "shards": [], "hashes_backfilled": 0,
              "winners_saved": [], "errors": []}

    # hash backfill: mevcut *_synapses.json kayıtları
    syn_name = repo_id.replace("/", "_") + "_synapses.json"
    syn_paths = [d / syn_name for d in SYNAPSE_JSON_DIRS if (d / syn_name).exists()]
    syn_records = {}
    syn = {}
    if syn_paths:
        syn = json.load(open(syn_paths[0]))
        syn_records = {t["key"]: t for t in syn.get("tensors", [])}

    for shard in plan["needed_shards"]:
        log(f"  ↓ shard: {shard}")
        local = download_shard(repo_id, shard, work_dir)
        seen_hashes = {}
        with open(local, "rb") as fp:
            hdr = read_st_header(fp)
            for key, info in hdr.items():
                h = hash_range(fp, info["start"], info["end"])  # streaming hash
                seen_hashes[key] = h
                if key in win_by_key:
                    outp = model_dir / f"{key.replace('.', '__')}.safetensors"
                    n = extract_winner(fp, info, key, outp)  # ham bayt kopya
                    meta = outp.with_suffix(".meta.json")
                    meta.write_text(json.dumps({
                        "model": repo_id, "key": key, "mevki": win_by_key[key]["mevki"],
                        "behavior": win_by_key[key]["behavior"], "aile": win_by_key[key]["aile"],
                        "sha256": h, "shape": info["shape"],
                        "dtype": DTYPE_MAP.get(info["dtype"], info["dtype"]),
                        "safetensors_dtype": info["dtype"], "bytes": n,
                    }, ensure_ascii=False, indent=1))
                    result["winners_saved"].append(str(outp))
                    log(f"    ✅ kazanan tensör: {key} {info['shape']} ({n / 1e9:.2f} GB)")
        # hash backfill (geri kalan eksik kayıtlar bu shard'lardan dolar)
        for key, h in seen_hashes.items():
            rec = syn_records.get(key)
            if rec is not None and not rec.get("hash"):
                rec["hash"] = h[:16]
                rec["hash_durumu"] = "tamam"
                result["hashes_backfilled"] += 1
        Path(local).unlink()  # gövde silinir — sinapslar alındı
        result["shards"].append(shard)
        log(f"    🗑️ shard gövdesi silindi")

    if syn_paths and result["hashes_backfilled"]:
        syn["tensors"] = list(syn_records.values())
        blob = json.dumps(syn, ensure_ascii=False, indent=1)
        for p in syn_paths:  # 4 kopya güncelle
            p.write_text(blob)
        log(f"  🔁 hash backfill: {result['hashes_backfilled']} kayıt → {len(syn_paths)} kopya güncellendi")

    return result


def backup_winners(repo_id: str) -> dict:
    """ALTIN-KIRMIZI: kazanan tensör dosyaları 4 kopyaya + streaming sha256 doğrulama."""
    model_dir = WINNERS_ROOT / repo_id.replace("/", "__")
    if not model_dir.exists():
        return {}
    copied = {}
    for d in BACKUP_DIRS:
        dst = d / "winners" / model_dir.name
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for fp in sorted(model_dir.iterdir()):
            target = dst / fp.name
            shutil.copyfile(fp, target)
            with open(fp, "rb") as a, open(target, "rb") as b:
                if hash_range(a, 0, fp.stat().st_size) != hash_range(b, 0, target.stat().st_size):
                    raise RuntimeError(f"Yedek doğrulama BAŞARISIZ: {target}")
            n += 1
        copied[str(dst)] = n
    log(f"  4 kopya yedek doğrulandı: {repo_id} ({list(copied.values())[0]} dosya)")
    return copied


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    winners = load_winners()
    models = sorted({w["model"] for w in winners})
    if args.model:
        models = [args.model]
    elif not args.all:
        models = models[:1]

    log(f"Manifest: {len(winners)} kazanan mevki, {len(models)} model seçildi")
    plans = []
    for m in models:
        w = [x for x in winners if x["model"] == m]
        try:
            plans.append((m, w, plan_for_model(m, w)))
        except Exception as e:
            log(f"  ⚠️ plan hatası {m}: {e}")

    total = sum(p["download_bytes"] for _, _, p in plans)
    for m, w, p in plans:
        log(f"  {m}: {p['n_winners']} mevki → {len(p['needed_shards'])} shard, "
            f"indirme {p['download_bytes'] / 1e9:.1f} GB")
        if p["keys_not_in_weightmap"]:
            log(f"    ⚠️ weight_map'te olmayan anahtarlar: {p['keys_not_in_weightmap']}")
    log(f"TOPLAM indirme: {total / 1e9:.1f} GB | seçili model sayısı: {len(plans)}")

    if args.dry_run:
        return

    for m, w, p in plans:
        out = Path("/home/pc/mahoraga_montaj") / f"collect_{m.replace('/', '__')}.json"
        if out.exists():
            log(f"\n=== ATLANDI (tamamlanmış): {m} ===")
            continue
        log(f"\n=== TOPLAMA: {m} ({len(w)} mevki) ===")
        res = collect_model(m, w)
        res["backup"] = backup_winners(m)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        log(f"TAMAM: {m} — {len(res['winners_saved'])} tensör, "
            f"{res['hashes_backfilled']} hash backfill")

    # nihai doğrulama: benzersiz (model, key) sayısı == winner dosya sayısı
    uniq = {(w["model"], w["key"]) for w in winners}
    files = list(WINNERS_ROOT.rglob("*.safetensors"))
    log(f"\nDOĞRULAMA: {len(uniq)} benzersiz (model, key) mevki ↔ {len(files)} kazanan dosya")
    if len(files) != len(uniq):
        log("⚠️ EŞLEŞMEYOR — eksik/fazla dosya var, sessiz geçme!")


if __name__ == "__main__":
    main()
