"""Gerçek Ameliyat Pipeline — HF Download + Safetensors Sömürü.

İndir -> Safetensors yükle -> Sinaps çıkar -> Yedekle -> Gövde sil
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download
from safetensors import safe_open
from safetensors.torch import load_file


def sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


DEFAULT_MAX_PARALLEL = 4
_SHARD_RE = re.compile(r"model-\d{5}-of-\d{5}\.safetensors$")


def download_shards_parallel(remaining: dict, local_dir: str, base: str,
                             tok: str | None = None, log=None,
                             max_parallel: int = DEFAULT_MAX_PARALLEL,
                             limit_rate: str | None = None,
                             curl_bin: str = "curl",
                             max_attempts: int = 30,
                             sleep=None) -> None:
    """Shard dosyalarını PARALEL indir (varsayılan 4 eşzamanlı curl süreci).

    remaining: {dosya_adı: beklenen_bayt | None} — index.json/weight_map ve HF
    dosya listesinden gelen beklenen boyutlar (biliniyorsa birebir doğrulanır).
    Korunan güvenlik semantikleri (seri yol ile birebir aynı):
    - resume: `curl -C -` ile `.curlpart` yan dosyası üzerinden kaldığı yerden devam
    - boyut doğrulama: boyut tutmayan dosya asla hedefe dönüştürülmez (sessiz
      bozulma yok); boyut fazla ise parça silinip baştan alınır
    - çift-format güvenliği: model-*-of-* shard'lar varsa consolidated.safetensors
      asla karışmaz (defense in depth — çağrılmadan önce de filtrelenir)
    - hata: bir shard denemeleri bitince ameliyat temiz iptal edilir (RuntimeError),
      uçaktaki curl süreçleri durdurulur; kısmi `.curlpart` dosyaları resume için
      korunur, asla silinmez
    - limit_rate: her curl sürecine AYNI `--limit-rate` değeri uygulanır
      (paralel süreç başına tutarlı; toplam bant = N x limit)

    sleep: testler için geri sayım fonksiyonu (varsayılan: abort-duyarlı bekleme).
    curl_bin: testler için sahte curl yoluna değiştirilebilir.
    """
    log = log or (lambda m: None)
    max_parallel = max(1, int(max_parallel))
    # çift-format güvenliği: shard ailesi varsa consolidated.safetensors asla karışmaz
    if any(_SHARD_RE.match(n) for n in remaining):
        remaining = {n: s for n, s in remaining.items()
                     if n != "consolidated.safetensors"}
    if not remaining:
        return

    abort = threading.Event()
    rest = sleep if sleep is not None else abort.wait
    failure: dict[str, str] = {}

    def _kill(proc):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def _one(n, sz):
        target = os.path.join(local_dir, n)
        part = target + ".curlpart"
        os.makedirs(os.path.dirname(target), exist_ok=True)
        for attempt in range(1, max_attempts + 1):
            if abort.is_set():
                return  # kısmi .curlpart resume için korunur
            hdr = ["-H", f"Authorization: Bearer {tok}"] if tok else []
            cmd = [curl_bin, "-sSL", "--fail", "--connect-timeout", "30",
                   "--speed-time", "120", "--speed-limit", "1000"]
            if limit_rate:
                cmd += ["--limit-rate", str(limit_rate)]
            cmd += ["-C", "-", "-o", part, *hdr, f"{base}/{n}"]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            while True:
                try:
                    rc = proc.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if abort.is_set():
                        _kill(proc)  # .curlpart yazılan kısım resume için kalır
                        return
            cur = os.path.getsize(part) if os.path.exists(part) else 0
            if (sz is not None and cur == sz) or (sz is None and rc == 0):
                if os.path.exists(part):
                    os.replace(part, target)
                log(f"    ✅ {n} ({(sz or 0)/1e9:.1f} GB)")
                return
            if sz is not None and cur > sz:  # bozuk/fazla — bastan al
                os.remove(part)
                log(f"    ⚠️ {n}: boyut fazla ({cur} > {sz}) — yeniden alınıyor")
            elif abort.is_set():
                return
            if attempt % 5 == 0 or attempt == 1:
                log(f"    ⚠️ {n}: deneme {attempt}/{max_attempts} ({cur/1e6:.0f}MB / {(sz or 0)/1e6:.0f}MB)")
            rest(min(5 * attempt, 60))
        # denemeler tükendi — ameliyatı temiz iptal et, shard adıyla haber ver
        failure[n] = f"indirme başarısız: {n} ({max_attempts} deneme)"
        abort.set()

    with ThreadPoolExecutor(max_workers=max_parallel) as ex:
        futs = [ex.submit(_one, n, sz) for n, sz in sorted(remaining.items())]
        for f in as_completed(futs):
            f.result()
    if failure:
        raise RuntimeError(next(iter(failure.values())))


class RealSurgery:
    """Gerçek model ameliyatı."""
    
    def __init__(self, backup_dir="./synapse_backups", work_dir="./surgery_work",
                 max_parallel: int = DEFAULT_MAX_PARALLEL, limit_rate: str | None = None):
        self.backup_dir = Path(backup_dir)
        self.work_dir = Path(work_dir)
        self.max_parallel = max(1, int(max_parallel))
        self.limit_rate = limit_rate
        for d in (self.backup_dir, self.work_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # dangling symlink (TOSHIBA bagli degil) — asagida kontrol
        for d in (self.backup_dir, self.work_dir):
            if not d.exists():
                raise RuntimeError(
                    f"{d} kullanilamaz — TOSHIBA bagli mi? (sudo mount /mnt/toshiba)"
                )
    
    def log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    
    def download_model(self, repo_id: str) -> str:
        """HF'den Safetensors indir. Takilmaya karsi zaman asimi + yeniden deneme."""
        import os
        self.log(f"  📥 İndiriliyor: {repo_id}")
        local_dir = self.work_dir / sanitize(repo_id)
        
        # Yerel tamamlilik onkontrolu: tum dosyalar dogru boyutta mevcutsa agir
        # snapshot dogrulamasini ATLA (xet yerel hash dogrulamasi 438GB'da saatler surer)
        try:
            from huggingface_hub import HfApi
            tok = os.environ.get("HF_TOKEN") or None
            siblings = HfApi().model_info(repo_id, files_metadata=True, token=tok).siblings
            names = {s.rfilename: s.size for s in siblings
                     if re.match(r".*\.(safetensors|json|txt|model)$", s.rfilename)}
            if any(re.match(r"model-\d{5}-of-\d{5}\.safetensors$", n) for n in names):
                names.pop("consolidated.safetensors", None)
            names, missing = prefer_complete_format(names, str(local_dir))
            if not missing:
                self.log(f"  ✅ Yerel doğrulama: tüm {len(names)} dosya tam — snapshot indirme atlandı")
                return str(local_dir)
            self.log(f"  ℹ️ Eksik/yarım dosya: {len(missing)} adet — snapshot indirme gerekiyor")
        except Exception as e:
            self.log(f"  ⚠️ Yerel ön kontrol atlandı ({str(e)[:80]}), snapshot indirmeye geçiliyor")
        
        # CURL-TABANLI INDIRME: hf_hub/xet katmani agirda kaliyor (CAS Client Error, 0 MB/s).
        # curl ayni HF CDN'den 24 MB/s gorduk (olcum 2026-11-03) — dosya indir, resume destekli.
        # 1 Gbps+ baglantida paralel 4 dosya (max_parallel, <2026-12): download_shards_parallel
        from huggingface_hub import HfApi
        tok = os.environ.get("HF_TOKEN") or None
        try:
            siblings = HfApi().model_info(repo_id, files_metadata=True, token=tok).siblings
            files = [(s.rfilename, s.size) for s in siblings
                     if re.match(r".*\.(safetensors|json|txt|model)$", s.rfilename)]
        except Exception as e:
            self.log(f"  ❌ Dosya listesi alınamadı: {e}")
            raise
        names = {n: sz for n, sz in files}
        if any(re.match(r"model-\d{5}-of-\d{5}\.safetensors$", n) for n in names):
            names.pop("consolidated.safetensors", None)  # çift-format artık
        names.pop(None, None)

        def complete(n, sz):
            p = os.path.join(str(local_dir), n)
            return os.path.exists(p) and (sz is None or os.path.getsize(p) == sz)

        names, _ = prefer_complete_format(names, str(local_dir))
        remaining = {n: sz for n, sz in names.items() if not complete(n, sz)}
        if not remaining:
            self.log(f"  ✅ Yerel doğrulama: tüm {len(names)} dosya tam — indirme atlandı")
            return str(local_dir)

        base = f"https://huggingface.co/{repo_id}/resolve/main"
        os.makedirs(str(local_dir), exist_ok=True)
        self.log(f"  📥 curl ile {len(remaining)} dosya indiriliyor ({sum(s or 0 for s in remaining.values())/1e9:.1f} GB) — paralel {min(self.max_parallel, len(remaining))} süreç")
        download_shards_parallel(
            remaining, str(local_dir), base, tok=tok, log=self.log,
            max_parallel=self.max_parallel, limit_rate=self.limit_rate,
        )
        self.log(f"  ✅ İndirildi: {local_dir}")
        return str(local_dir)
    
    def extract_weight_synapses(self, model_path: str, model_name: str) -> dict:
        """Safetensors ağırlıklarından sinaps çıkar. GPU hızlandırmalı (varsa)."""
        self.log(f"  🔬 Sinaps çıkarımı başlıyor...")
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            self.log(f"  🚀 GPU hızlandırma: {torch.cuda.get_device_name(0)}")
        
        model_dir = Path(model_path)
        safetensor_files = sorted(model_dir.glob("*.safetensors"))

        # Çift-format koruması: index.json weight_map GERÇEK dosya listesidir
        # (Mistral ailesi hem consolidated.safetensors hem shard yayınlar: 2x disk + 2x sayım + mmap OOM)
        index_file = pick_weight_index(str(model_dir))
        if index_file.exists():
            wm = json.loads(index_file.read_text()).get("weight_map", {})
            keep = set(wm.values())
            skipped = [f.name for f in safetensor_files if f.name not in keep]
            safetensor_files = [f for f in safetensor_files if f.name in keep]
            if skipped:
                self.log(f"  🧹 Atlanıyor (index dışı, çift-format artık): {', '.join(skipped)}")
        else:
            shards = [f for f in safetensor_files
                      if re.match(r"model-\d{5}-of-\d{5}\.safetensors$", f.name)]
            if shards and any(f.name == "consolidated.safetensors" for f in safetensor_files):
                self.log("  🧹 Çift-format: consolidated.safetensors atlanıyor (shard'lar tercih)")
                safetensor_files = shards

        if not safetensor_files:
            raise FileNotFoundError(f"No safetensors found in {model_path}")

        total_synapses = 0
        layer_synapses = {}
        all_hashes = []
        seen_keys = set()

        # Kesinti dayanıklılığı (checkpoint): her safetensors dosyası bitince NVMe'ye yazılır.
        # USB kopması / restart / crash'te işlenen dosyalar atlanır — ALTIN-KIRMIZI kural:
        # ilerleme NVMe'de yaşar, Toshiba yalnızca çalışma alanıdır.
        ckpt_dir = self.backup_dir / ".ckpt"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        ckpt_file = ckpt_dir / (sanitize(model_name) + ".jsonl")
        done = {}
        if ckpt_file.exists():
            with open(ckpt_file) as cf:
                for line in cf:
                    try:
                        rec = json.loads(line)
                        done[rec["file"]] = rec
                    except (ValueError, KeyError, OSError):
                        continue
            if done:
                self.log(f"  ↻ Kontrol noktası: {len(done)} dosya önceden işlenmiş — kaldığı yerden devam")

        for st_file in safetensor_files:
            if st_file.name in done:
                rec = done[st_file.name]
                all_hashes.extend(rec["tensors"])
                total_synapses += rec["n_synapses"]
                for lk, lv in rec["layers"].items():
                    layer_synapses[int(lk)] = layer_synapses.get(int(lk), 0) + lv
                seen_keys.update(t["key"] for t in rec["tensors"])
                continue
            self.log(f"    📄 İşleniyor: {st_file.name}")
            file_synapses = 0
            file_layers = {}
            file_records = []
            
            with safe_open(str(st_file), framework="pt") as f:
                for key in f.keys():
                    if key in seen_keys:
                        continue  # çift sayımı engelle
                    seen_keys.add(key)
                    # OOM koruması: büyük tensörler asla tümüyle RAM'e alınmaz
                    # (systemd-oomd 101 GB shard'da süreci öldürüyordu) — chunk'lı yol.
                    sl = f.get_slice(key)
                    shape = list(sl.get_shape())
                    n = 1
                    for d in shape:
                        n *= d
                    total_synapses += n
                    file_synapses += n
                    
                    # Layer tracking
                    layer_match = re.search(r"layers\.(\d+)", key)
                    if layer_match:
                        layer_idx = int(layer_match.group(1))
                        layer_synapses[layer_idx] = layer_synapses.get(layer_idx, 0) + n
                        file_layers[layer_idx] = file_layers.get(layer_idx, 0) + n
                    
                    # Hash for backup verification (sample-based for speed)
                    if n > 0:
                        if n >= 134_217_728:  # ≥128M eleman (~256 MB bf16): chunk'lı yol
                            rec = tensor_record_chunked(f, key)
                        else:
                            tensor = f.get_tensor(key)
                            # kısayol: tam fp32 tensör kopyası + GPU'a tüm-tensor transferi kaldırıldı
                            # (tek skalar mean için 2x RAM + PCIe trafiği gereksizdi; bf16/fp16 ⊂ fp32
                            #  olduğu için örnek değerleri ham tensörden okumak bit-aynı hash üretir)
                            sample = tensor.reshape(-1)[::max(1, n // 100)][:100]
                            h = hashlib.sha256()
                            for v in sample.to(torch.float32).tolist():
                                h.update(struct.pack("f", v))
                            # magnitude: fp32 birikimli CPU reduction (parça parça, kopyasız)
                            # FP8 (Float8_e8m0fnu) tensor'lerde abs_cpu desteklenmiyor — önce float32'ye çevir
                            mag = float(tensor.to(torch.float32).abs().mean())
                            rec = {
                                "key": key,
                                "shape": list(tensor.shape),
                                "n_synapses": n,
                                "hash": h.hexdigest()[:16],
                                "magnitude": mag,
                            }
                            del tensor
                        file_records.append(rec)
            # dosya tamamlandı — checkpoint'i NVMe'ye daya (fsync: ani kopmada bile satır kaybolmasın)
            with open(ckpt_file, "a") as cf:
                cf.write(json.dumps({"file": st_file.name, "n_synapses": file_synapses,
                                     "layers": file_layers, "tensors": file_records}) + "\n")
                cf.flush()
                os.fsync(cf.fileno())
            all_hashes.extend(file_records)

        result = {
            "model": model_name,
            "total_synapses": total_synapses,
            "n_layers": len(layer_synapses),
            "layer_synapses": layer_synapses,
            "tensors": all_hashes,
            "golden_red_rule": "NEVER DELETE - ALWAYS BACKUP",
        }
        
        self.log(f"  ✅ {total_synapses:,} sinaps çıkarıldı, {len(layer_synapses)} katman")
        return result
    
    def backup_synapses(self, extraction: dict) -> str:
        """Altın-kırmızı kural: Yedekle."""
        safe_name = sanitize(extraction["model"])
        backup_file = self.backup_dir / f"{safe_name}_synapses.json"
        
        with open(backup_file, "w") as f:
            json.dump(extraction, f, indent=2)
        
        self.log(f"  💾 Yedeklendi: {backup_file}")
        return str(backup_file)
    
    def verify_backup(self, backup_path: str) -> bool:
        """Yedekleme doğrulama."""
        with open(backup_path) as f:
            data = json.load(f)
        
        if data.get("golden_red_rule") != "NEVER DELETE - ALWAYS BACKUP":
            return False
        if data.get("total_synapses", 0) <= 0:
            return False
        return True
    
    def delete_model_body(self, model_path: str):
        """Model gövdesini sil (sinapslar güvende)."""
        path = Path(model_path)
        if path.exists():
            size_gb = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e9
            shutil.rmtree(path)
            self.log(f"  🗑️ Gövde silindi ({size_gb:.1f} GB freed)")
    
    def run_surgery(self, repo_id: str) -> dict:
        """Tam ameliyat pipeline'ı."""
        self.log(f"\n{'='*60}")
        self.log(f"🔪 AMELİYAT: {repo_id}")
        
        result = {
            "model": repo_id,
            "status": "started",
            "synapses": 0,
            "backup_path": "",
        }
        
        try:
            # 1. Download
            model_path = self.download_model(repo_id)
            
            # 2. Extract synapses
            extraction = self.extract_weight_synapses(model_path, repo_id)
            result["synapses"] = extraction["total_synapses"]
            
            # 3. Backup
            backup_path = self.backup_synapses(extraction)
            result["backup_path"] = backup_path
            
            # 4. Verify
            if not self.verify_backup(backup_path):
                raise Exception("BACKUP VERIFICATION FAILED")
            
            # 4.5 checkpoint temizliği: yedek doğrulandı, ilerleme kaydı artık gereksiz
            try:
                (self.backup_dir / ".ckpt" / (sanitize(repo_id) + ".jsonl")).unlink(missing_ok=True)
            except OSError:
                pass
            
            # 5. Delete body
            self.delete_model_body(model_path)
            
            result["status"] = "completed"
            self.log(f"  ✅ AMELİYAT TAMAM: {result['synapses']:,} sinaps")
            
        except Exception as e:
            result["status"] = f"failed: {e}"
            self.log(f"  ❌ HATA: {e}")
        
        return result
    
    def batch_surgery(self, repo_ids: list[str]) -> list[dict]:
        """Toplu ameliyat."""
        results = []
        for i, repo_id in enumerate(repo_ids):
            self.log(f"\nMODEL {i+1}/{len(repo_ids)}")
            results.append(self.run_surgery(repo_id))
        return results


def run_batch(repo_ids: list[str]) -> list[dict]:
    surgery = RealSurgery()
    return surgery.batch_surgery(repo_ids)


def prefer_complete_format(names: dict, local_dir: str):
    """Çift-format (consolidated-* / model-*) yayınlarda, yerelde TAM olan formatı seç.

    names: {dosya_adı: beklenen_boyut}. Döner: (indirilecek_dosyalar_dict, eksik_listesi).
    Kural: tam (boyutu doğru) bir format varsa diğerini indirme — 187 GB gereksiz trafik engellenir.
    """
    import os

    def _is_complete(group):
        return all(
            os.path.exists(os.path.join(local_dir, n))
            and (sz is None or os.path.getsize(os.path.join(local_dir, n)) == sz)
            for n, sz in group.items()
        )

    cons = {n: s for n, s in names.items() if re.match(r"consolidated-\d{5}-of-\d{5}\.safetensors$", n)}
    shards = {n: s for n, s in names.items() if re.match(r"model-\d{5}-of-\d{5}\.safetensors$", n)}
    if cons and shards and _is_complete(cons):
        keep = {n: s for n, s in names.items() if n not in shards}
        return keep, []
    if cons and shards and _is_complete(shards):
        keep = {n: s for n, s in names.items() if n not in cons}
        return keep, []
    missing = [n for n, sz in names.items()
               if not os.path.exists(os.path.join(local_dir, n))
               or (sz is not None and os.path.getsize(os.path.join(local_dir, n)) != sz)]
    return names, missing


def pick_weight_index(model_dir: str):
    """Çift-format'ta, dosyaları TAM olan formatın index'ini seç (model.* veya consolidated.*)."""
    import os
    from pathlib import Path
    d = Path(model_dir)
    cands = [d / "consolidated.safetensors.index.json", d / "model.safetensors.index.json"]
    for idx in cands:
        if not idx.exists():
            continue
        wm = json.loads(idx.read_text()).get("weight_map", {})
        files = {n: None for n in set(wm.values())}
        _, missing = prefer_complete_format(files, str(d))
        if not missing:
            return idx
    return next((c for c in cands if c.exists()), cands[1])


def tensor_record_chunked(f, key: str, chunk_elems: int = 16_000_000) -> dict:
    """Bir tensörün sinaps kaydını SABİT bellekle, chunk'layarak üret.

    Büyük tensörlerde (onlarca GB) eski yol tüm tensörü + fp32 kopyasını
    RAM'e alıyordu → systemd-oomd süreci öldürüyordu. Bu yol get_tensor'a
    hiç dokunmaz; safetensors get_slice ile ilk eksen boyunca parçalar okur.
    Hash örneklemi eski algoritmayla (global düz indeksli 100 örnek) birebir
    aynıdır; magnitude fp64 kümülatif toplamla hesaplanır.
    """
    import torch
    shape = list(f.get_slice(key).get_shape())
    n = 1
    for d in shape:
        n *= d
    if n == 0:
        return {"key": key, "shape": shape, "n_synapses": 0,
                "hash": hashlib.sha256().hexdigest()[:16], "magnitude": 0.0}

    width = n // shape[0] if shape[0] else n  # ilk eksen satırı
    rows_per_chunk = max(1, chunk_elems // max(1, width))
    step = max(1, n // 100)
    sample_positions = [i * step for i in range(100) if i * step < n]

    h = hashlib.sha256()
    abs_sum = 0.0
    collected = []
    flat_start = 0
    sl = f.get_slice(key)
    for r0 in range(0, shape[0], rows_per_chunk):
        r1 = min(r0 + rows_per_chunk, shape[0])
        chunk = sl[r0:r1].reshape(-1).to(torch.float32)
        abs_sum += float(chunk.abs().sum(dtype=torch.float64))
        flat_end = flat_start + chunk.numel()
        for p in sample_positions:
            if flat_start <= p < flat_end:
                collected.append(float(chunk[p - flat_start]))
        flat_start = flat_end
        del chunk

    for v in collected:
        h.update(struct.pack("f", v))
    return {"key": key, "shape": shape, "n_synapses": n,
            "hash": h.hexdigest()[:16], "magnitude": abs_sum / n}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Gerçek ameliyat pipeline — paralel shard indirme (curl)")
    p.add_argument("repos", nargs="+", help="HF repo id, ör. Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL,
                   help=f"eşzamanlı curl süreci sayısı (varsayılan {DEFAULT_MAX_PARALLEL})")
    p.add_argument("--limit-rate", default=None,
                   help="curl --limit-rate; her sürece ayrı ayrı uygulanır, ör. 12M")
    p.add_argument("--backup-dir", default="./synapse_backups")
    p.add_argument("--work-dir", default="./surgery_work")
    return p


def main(argv=None) -> int:
    a = build_arg_parser().parse_args(argv)
    surgery = RealSurgery(backup_dir=a.backup_dir, work_dir=a.work_dir,
                          max_parallel=a.max_parallel, limit_rate=a.limit_rate)
    results = surgery.batch_surgery(a.repos)
    return 0 if all(r["status"] == "completed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
