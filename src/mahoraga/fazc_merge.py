#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mahoraga Faz-C — MERGE-FIRST öğrenci uzman birleştirme (Σw·v).

Plan: docs/mahoraga-nihai-plan.md §Faz-C. Çıkarılan sinapslar doğrudan
doğrusal birleştirilir: v_merged(key) = Σ_k w_k·v_k (kovaryans ağırlıkları
yerine manifest n_synapses vekili — kayıtlı, doğrulanabilir), öğrenci
güncellemesi v' = (1-α)·v_student + α·v_merged (varsayılan α=0.3).

Kurallar:
- Yalnız ŞEKİL + anahtar adı birebir uyan tensörler doğrudan birleşir
  (direct_merge). Uymayanlar raporlanır → plan gereği akış bağlama /
  distilasyon (pilot dışı).
- Ham-bayt streaming (safe_open/mmap YOK — FUSE/mmap ENOMEM dersi).
- Çıktı: tek safetensors (Toshiba) + merge_manifest.json + 4 kopya yedek.
- Altın-kırmızı: manifest + sinapslar kalıcı; birleştirilmiş gövde türevdir.

Kullanım:
  rapor:  python3 fazc_merge.py --report --student REPO_ID [--behavior kod]
  birleş: python3 fazc_merge.py --merge --student-path /path/model.safetensors \
              [--student-index index.json] --behavior kod --alpha 0.3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import time
from pathlib import Path

import torch

ROOT = Path("/home/pc/mahoraga_montaj")
MANIFEST = Path("/home/pc/mahoraga_montaj_manifest.json")
WINNERS = ROOT / "winners"
OUT_ROOT = Path("/mnt/toshiba/mahoraga/fazc_merged")
MANIFEST_BACKUPS = [
    Path("/home/pc/mahoraga_synapses/merge_manifests"),
    Path("/home/pc/synapse_backups_safe/merge_manifests"),
    Path("/home/pc/backup_mahoraga/synapse_backups/merge_manifests"),
    Path("/mnt/toshiba/mahoraga/synapse_backups/merge_manifests"),
]
GIANT = 20 << 30
TOSHIBA_BACKUP_DIRS = [
    Path("/mnt/toshiba/mahoraga/synapse_backups"),
    Path("/mnt/toshiba/mahoraga/synapse_backups_b"),
    Path("/mnt/toshiba/mahoraga/synapse_backups_c"),
]


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def winner_file(model: str, key: str) -> Path:
    return WINNERS / model.replace("/", "__") / (key.replace(".", "__") + ".safetensors")


def load_winners(behavior: str | None = None) -> list[dict]:
    m = json.load(open(MANIFEST))
    out = []
    for b, blk in m["davranislar"].items():
        if behavior and b != behavior:
            continue
        for s in blk["sinapslar"]:
            fp = winner_file(s["model"], s["key"])
            meta = fp.with_suffix(".meta.json")
            rec = dict(s)
            rec["behavior"] = b
            rec["file"] = str(fp)
            rec["exists"] = fp.exists() and meta.exists()
            if meta.exists():
                rec["shape"] = json.load(open(meta)).get("shape")
                rec["dtype"] = json.load(open(meta)).get("dtype")
            out.append(rec)
    return out


# ---------- safetensors ham-bayt yardımcıları (mmap YOK) ----------

def read_header(path: Path) -> tuple[dict, int]:
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(n))
    return hdr, 8 + n


def read_tensor_raw(path: Path, hdr: dict, key: str) -> tuple[bytes, str]:
    info = hdr[key]
    s, e = info["data_offsets"]
    with open(path, "rb") as f:
        f.seek(read_header(path)[1] + s)
        return f.read(e - s), info["dtype"]


DTYPE_SIZE = {"F64": 8, "I64": 8, "F32": 4, "I32": 4, "F16": 2, "BF16": 2, "I16": 2, "U8": 1, "I8": 1, "F8_E4M3": 1}
TORCH_DT = {"F64": torch.float64, "F32": torch.float32, "F16": torch.float16,
            "BF16": torch.bfloat16, "I64": torch.int64, "I32": torch.int32,
            "I16": torch.int16, "I8": torch.int8, "U8": torch.uint8}


# ---------- rapor: manifest kazananları ↔ öğrenci indeksi ----------

def student_shape_map(repo_id: str) -> dict:
    """Öğrenci repo ağırlık haritası + şekil sözlüğü (sadece başlıklar indirilir)."""
    from huggingface_hub import hf_hub_download
    wm = {}
    try:
        p = hf_hub_download(repo_id, "model.safetensors.index.json")
        wm = json.load(open(p))["weight_map"]
    except Exception:
        wm = {}  # tekil dosya modeli
    import urllib.request
    try:
        from huggingface_hub import HfFolder
        _tok = HfFolder.get_token()
    except Exception:
        _tok = None

    def shapes_from(repo_file: str) -> dict:
        url = f"https://huggingface.co/{repo_id}/resolve/main/{repo_file}"
        headers = {"Range": "bytes=0-20000000"}
        if _tok:
            headers["Authorization"] = f"Bearer {_tok}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read(20_000_000)
        n = struct.unpack("<Q", data[:8])[0]
        while n + 8 > len(data):  # dev başlık
            req = urllib.request.Request(url, headers={**headers, "Range": f"bytes=0-{n + 8}"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read(n + 8)
        hdr = json.loads(data[8:8 + n])
        return {k: v.get("shape") for k, v in hdr.items() if k != "__metadata__"}

    shapes = {}
    if wm:
        for shard in sorted(set(wm.values())):
            shapes.update(shapes_from(shard))
    else:
        shapes.update(shapes_from("model.safetensors"))
    return {"weight_map": wm, "shapes": shapes}


def report(student_repo: str, behavior: str | None):
    log(f"rapor: öğrenci {student_repo}")
    stu = student_shape_map(student_repo)
    wins = load_winners(behavior)
    exact, shape_only, none_, missing_files = [], [], [], []
    for w in wins:
        if not w.get("exists"):
            missing_files.append(w)
            continue
        k, sh = w["key"], tuple(w.get("shape") or [])
        if k in stu["shapes"]:
            if tuple(stu["shapes"][k]) == sh:
                exact.append(w)
            else:
                shape_only.append((w, stu["shapes"][k]))
        else:
            none_.append(w)
    log(f"  toplam {len(wins)} kayıt | birebir anahtar+şekil: {len(exact)} | "
        f"anahtar var şekil farklı: {len(shape_only)} | anahtar yok: {len(none_)} | "
        f"dosya eksik: {len(missing_files)}")
    for w in exact:
        log(f"   ✓ {w['behavior']:10} {w['model'][:38]:40} {w['key']}")
    for w, sh in shape_only:
        log(f"   ≠ {w['behavior']:10} {w['key']}  kazanan{w['shape']} vs öğrenci{list(sh)}")
    out = {
        "student": student_repo,
        "exact": [(w["behavior"], w["model"], w["key"], w["shape"]) for w in exact],
        "shape_mismatch": [(w["key"], w["shape"], list(sh)) for w, sh in shape_only],
        "key_absent": [(w["behavior"], w["model"], w["key"]) for w in none_],
        "files_missing": [(w["model"], w["key"]) for w in missing_files],
    }
    p = ROOT / f"merge_report_{student_repo.replace('/', '__')}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    log(f"  rapor: {p}")
    return out


# ---------- birleştirme ----------

def merge(student_path: Path, behavior: str, alpha: float,
          index_path: Path | None, weight_by_synapses: bool = True):
    if not Path("/mnt/toshiba").is_mount():
        raise RuntimeError("Toshiba mount'lu değil — çıktı NVMe'ye düşer, durduruldu")
    s_hdr, s_base = read_header(student_path)
    s_meta = s_hdr.pop("__metadata__", None) or {}
    keys = [k for k in s_hdr]
    wins = [w for w in load_winners(behavior) if w.get("exists")]
    by_key: dict[str, list[dict]] = {}
    for w in wins:
        by_key.setdefault(w["key"], []).append(w)

    plan = []
    for k in keys:
        grp = by_key.get(k)
        if not grp:
            continue
        if any(tuple(w["shape"]) != tuple(s_hdr[k]["shape"]) for w in grp):
            log(f"  ≠ şekil uyuşmadı, atlandı: {k}")
            continue
        ws = [float(w.get("n_synapses") or 1.0) for w in grp] if weight_by_synapses else [1.0] * len(grp)
        tot = sum(ws) or 1.0
        plan.append({"key": k, "teachers": [(w["model"], w["behavior"], wi / tot)
                                            for w, wi in zip(grp, ws)]})
    log(f"birleşim planı: {len(plan)} tensör (α={alpha}, davranış={behavior})")
    if not plan:
        log("  doğrudan birleşecek tensör yok — plan gereği akış bağlama/distilasyon sınıfı")
        return None

    plan_map = {p["key"]: p for p in plan}
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = OUT_ROOT / f"{student_path.stem}__{behavior}__merged.safetensors"
    manifest = {
        "behavior": behavior, "alpha": alpha, "student": str(student_path),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "weight_rule": "w ∝ n_synapses (normalize)" if weight_by_synapses else "uniform",
        "formula": "v' = (1-alpha)*v_student + alpha*sum_k w_k*v_k",
        "merged_keys": [],
    }

    with open(student_path, "rb") as sf, open(out_path, "wb") as of:
        out_hdr: dict = {}
        offset = 0
        of.write(b"\x00" * 8)  # başlık yer tutucu
        for k in keys:
            s_info = s_hdr[k]
            s, e = s_info["data_offsets"]
            nbytes = e - s
            if k not in plan_map:
                sf.seek(s_base + s)
                remain = nbytes
                while remain:
                    chunk = sf.read(min(1 << 22, remain))
                    of.write(chunk)
                    remain -= len(chunk)
                out_hdr[k] = {"dtype": s_info["dtype"], "shape": s_info["shape"],
                              "data_offsets": [offset, offset + nbytes]}
                offset += nbytes
                continue
            # öğrenci tensörü (ham)
            sf.seek(s_base + s)
            s_raw = sf.read(nbytes)
            dt = TORCH_DT[s_info["dtype"]]
            s_t = torch.frombuffer(bytearray(s_raw), dtype=dt).clone()
            acc = torch.zeros_like(s_t, dtype=torch.float32)
            for model, _b, w in plan_map[k]["teachers"]:
                fp = winner_file(model, k)
                t_hdr, _ = read_header(fp)
                t_raw, t_dt = read_tensor_raw(fp, t_hdr, k)
                t_t = torch.frombuffer(bytearray(t_raw), dtype=TORCH_DT[t_dt])
                acc += w * t_t.to(torch.float32)
            merged = (1.0 - alpha) * s_t.to(torch.float32) + alpha * acc
            out_b = merged.to(dt).contiguous().numpy().tobytes()
            of.write(out_b)
            out_hdr[k] = {"dtype": s_info["dtype"], "shape": s_info["shape"],
                          "data_offsets": [offset, offset + len(out_b)]}
            offset += len(out_b)
            manifest["merged_keys"].append({
                "key": k, "teachers": [(m, round(w, 4)) for m, _b, w in plan_map[k]["teachers"]],
                "shape": s_info["shape"], "sha256": hashlib.sha256(out_b).hexdigest()[:32],
            })
        # başlığı yaz
        hdr_json = json.dumps({"__metadata__": s_meta, **out_hdr}).encode()
        of.seek(0)
        of.write(struct.pack("<Q", len(hdr_json)) + hdr_json)

    manifest["out_file"] = str(out_path)
    manifest["out_sha256"] = hashlib.sha256(out_path.read_bytes()).hexdigest()
    mp = out_path.with_suffix(".merge_manifest.json")
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    for d in MANIFEST_BACKUPS:
        d.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(mp, d / mp.name)
    log(f"  ✓ birleşik gövde: {out_path} ({out_path.stat().st_size / 1e9:.1f} GB)")
    log(f"  ✓ manifest 4 kopya yedeklendi: {mp.name}")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--student")
    ap.add_argument("--student-path")
    ap.add_argument("--student-index")
    ap.add_argument("--behavior", default=None)
    ap.add_argument("--alpha", type=float, default=0.3)
    ap.add_argument("--uniform-weights", action="store_true")
    a = ap.parse_args()
    if a.report:
        report(a.student, a.behavior)
    elif a.merge:
        idx = Path(a.student_index) if a.student_index else None
        merge(Path(a.student_path), a.behavior, a.alpha, idx,
              weight_by_synapses=not a.uniform_weights)
    else:
        ap.error("--report veya --merge gerekli")


if __name__ == "__main__":
    main()
