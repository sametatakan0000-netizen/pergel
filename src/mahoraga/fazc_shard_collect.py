"""Faz-C sinaps shard toplayıcı — kazanan mevki tensörleri (Σw·v hammaddesi).

Montaj manifestindeki (57 mevki) kazanan sinapsların GERÇEK tensörlerini toplar:

  1. model.safetensors.index.json weight_map -> mevki-key -> shard eşlemesi
     (çift-format repolarda index.json weight_map GERÇEK dosya listesidir)
  2. Yalnız kazanan anahtarları içeren shard'lar indirilir (Toshiba çalışma
     kütüphanesi — portabilite ilkesi, plan §7.2)
  3. İndirilen shard'ların TÜM anahtarları için hash backfill
     (96.085 eksik kayıt — ek indirme yok, zaten gelen shard'lardan)
  4. Kazanan tensörler safetensors olarak 4 kopya yedeklenir (ALTIN-KIRMIZI)
  5. Shard gövdeleri silinir (sinaps çıkarıldı, gövde geçici)

Kullanım:
  python3 fazc_shard_collect.py --dry-run                    # depolama planı
  python3 fazc_shard_collect.py --model REPO_ID              # tek model
  python3 fazc_shard_collect.py --all                        # tamamı (ön-sıra: kod)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

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


def sha256_tensor(t) -> str:
    import numpy as np

    h = hashlib.sha256()
    arr = t.numpy() if hasattr(t, "numpy") else np.asarray(t)
    h.update(arr.tobytes())
    return h.hexdigest()


def collect_model(repo_id: str, winners: list[dict]) -> dict:
    from huggingface_hub import hf_hub_download
    from safetensors import safe_open
    from safetensors.numpy import save_file

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
    if syn_paths:
        syn = json.load(open(syn_paths[0]))
        syn_records = {t["key"]: t for t in syn.get("tensors", [])}

    for shard in plan["needed_shards"]:
        log(f"  ↓ shard: {shard}")
        local = hf_hub_download(repo_id, shard, local_dir=str(work_dir))
        seen_hashes = {}
        with safe_open(local, framework="np") as f:
            for key in f.keys():
                t = f.get_tensor(key)
                h = sha256_tensor(t)
                seen_hashes[key] = h
                if key in win_by_key:
                    outp = model_dir / f"{key.replace('.', '__')}.safetensors"
                    save_file({key: t}, str(outp))
                    meta = outp.with_suffix(".meta.json")
                    meta.write_text(json.dumps({
                        "model": repo_id, "key": key, "mevki": win_by_key[key]["mevki"],
                        "behavior": win_by_key[key]["behavior"], "aile": win_by_key[key]["aile"],
                        "sha256": h, "shape": list(t.shape),
                        "dtype": str(t.dtype), "bytes": int(t.size * t.itemsize),
                    }, ensure_ascii=False, indent=1))
                    result["winners_saved"].append(str(outp))
                    log(f"    ✅ kazanan tensör: {key} {list(t.shape)} ({t.size * t.itemsize / 1e9:.2f} GB)")
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
    """ALTIN-KIRMIZI: kazanan tensör dosyaları 4 kopyaya + sha256 doğrulama."""
    model_dir = WINNERS_ROOT / repo_id.replace("/", "__")
    if not model_dir.exists():
        return {}
    copied = {}
    for d in BACKUP_DIRS:
        dst = d / "winners" / model_dir.name
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for fp in model_dir.iterdir():
            target = dst / fp.name
            target.write_bytes(fp.read_bytes())
            if hashlib.sha256(fp.read_bytes()).hexdigest() != hashlib.sha256(target.read_bytes()).hexdigest():
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
    win_total = 0
    for m, w, p in plans:
        per_win = p["download_bytes"] / max(1, p["n_winners"])
        est_win = sum(0 for _ in w)  # gerçek tensör boyutu shard'dan biliniyor; tahmin:
        log(f"  {m}: {p['n_winners']} mevki → {len(p['needed_shards'])} shard, "
            f"indirme {p['download_bytes'] / 1e9:.1f} GB")
        if p["keys_not_in_weightmap"]:
            log(f"    ⚠️ weight_map'te olmayan anahtarlar: {p['keys_not_in_weightmap']}")
    log(f"TOPLAM indirme: {total / 1e9:.1f} GB | seçili model sayısı: {len(plans)}")
    log(f"Depolama: / (NVMe) geçici kazananlar + yedekler; /mnt/toshiba shard çalışma kütüphanesi")

    if args.dry_run:
        return

    for m, w, p in plans:
        log(f"\n=== TOPLAMA: {m} ({len(w)} mevki) ===")
        res = collect_model(m, w)
        res["backup"] = backup_winners(m)
        out = Path("/home/pc/mahoraga_montaj") / f"collect_{m.replace('/', '__')}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        log(f"TAMAM: {m} — {len(res['winners_saved'])} tensör, "
            f"{res['hashes_backfilled']} hash backfill")


if __name__ == "__main__":
    main()
