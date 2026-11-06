"""Paralel shard indirme testleri — sahte curl ile (ağ yok, stdlib unittest).

Korunması gereken güvenlik semantikleri:
- resume: curl `-C -` + `.curlpart` yan dosyası üzerinden kaldığı yerden devam
- dosya başına boyut doğrulama (index.json/weight_map'ten gelen beklenen boyutlar)
- çift-format güvenliği: model-*-of-* shard'lar varsa consolidated.safetensors asla indirilmez
- hata: bir shard başarısızsa ameliyat temiz iptal edilir, kısmi dosya resume için korunur
- sessiz bozulma yok: boyutu tutmayan dosya asla hedefe dönüştürülmez
- --limit-rate her curl sürecine ayrı ayrı uygulanır (paralel süreç başına tutarlı)
"""
import importlib.util
import unittest

if importlib.util.find_spec("huggingface_hub") is None:
    raise unittest.SkipTest(
        "huggingface_hub yok (agir opsiyonel bagimlilik, ameliyat ortami)")

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.mahoraga.real_surgery import (
    DEFAULT_MAX_PARALLEL,
    build_arg_parser,
    download_shards_parallel,
)


def payload_for(name: str, size: int) -> bytes:
    """Sahte curl ile aynı deterministik içerik üretir."""
    return (name.encode() * (size // len(name) + 1))[:size]


# Sahte curl: -o çıktısına deterministik bayt yazar, -C - resume'i taklit eder.
# FAKE_CURL_SIZES  -> {ad: beklenen_boyut} JSON dosyası
# FAKE_CURL_LOG    -> start/end/argv kayıtları (eşzamanlılık ölçümü için)
# FAKE_CURL_SLEEP  -> dosya başına taklit transfer süresi (saniye)
# FAKE_CURL_FAIL_SUBSTR  -> adında geçen dosyalarda yarım yaz + exit 7
# FAKE_CURL_SHORT_SUBSTR -> adında geçen dosyalarda boyut-1 yaz + exit 0
STUB = r'''#!/usr/bin/env python3
import json, os, sys, time

argv = sys.argv[1:]
out, url = None, None
i = 0
while i < len(argv):
    a = argv[i]
    if a in ("-o", "-H", "--limit-rate"):
        if a == "-o":
            out = argv[i + 1]
        i += 2
        continue
    if a.startswith("-"):
        i += 1
        continue
    url = a
    i += 1

name = url.rsplit("/", 1)[-1]
sizes = json.load(open(os.environ["FAKE_CURL_SIZES"]))
size = sizes[name]
payload = (name.encode() * (size // len(name) + 1))[:size]
log = os.environ["FAKE_CURL_LOG"]


def rec(msg):
    with open(log, "a") as fh:
        fh.write(msg + "\n")


rec("argv %s %s" % (name, json.dumps(argv)))
rec("start %s %.6f" % (name, time.time()))
sleep_s = float(os.environ.get("FAKE_CURL_SLEEP", "0"))
fail = os.environ.get("FAKE_CURL_FAIL_SUBSTR", "")
short = os.environ.get("FAKE_CURL_SHORT_SUBSTR", "")

cur = os.path.getsize(out) if os.path.exists(out) else 0
if fail and fail in name:
    stop = size // 2
elif short and short in name:
    stop = size - 1
else:
    stop = size

data = payload[cur:stop]
step = max(1, len(payload) // 4)
with open(out, "ab") as fh:
    for j in range(0, max(1, len(data)), step):
        fh.write(data[j:j + step])
        fh.flush()
        if sleep_s:
            time.sleep(sleep_s / 4)

if fail and fail in name:
    rec("end %s %.6f fail" % (name, time.time()))
    sys.exit(7)
rec("end %s %.6f ok" % (name, time.time()))
'''


class TestParallelShardDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dest = self.tmp / "model"
        self.dest.mkdir()
        self.stub = self.tmp / "fake_curl.py"
        self.stub.write_text(STUB)
        self.stub.chmod(0o755)
        self.sizes_file = self.tmp / "sizes.json"
        self.log_file = self.tmp / "curl.log"
        self.base = "https://example.invalid/org/model/resolve/main"
        self.env = {
            "FAKE_CURL_SIZES": str(self.sizes_file),
            "FAKE_CURL_LOG": str(self.log_file),
            "FAKE_CURL_SLEEP": "0",
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sizes(self, sizes: dict):
        self.sizes_file.write_text(json.dumps(sizes))

    def _run(self, remaining: dict, max_attempts: int = 3, **kw):
        kw.setdefault("tok", None)
        kw.setdefault("log", lambda m: None)
        kw.setdefault("max_parallel", 4)
        kw.setdefault("curl_bin", str(self.stub))
        kw.setdefault("sleep", lambda s: None)
        with mock.patch.dict(os.environ, self.env):
            return download_shards_parallel(
                remaining, str(self.dest), self.base,
                max_attempts=max_attempts, **kw)

    def _records(self):
        starts, ends, argvs = [], [], []
        if self.log_file.exists():
            for line in self.log_file.read_text().splitlines():
                parts = line.split(" ", 2)
                if parts[0] == "start":
                    starts.append((parts[1], float(parts[2])))
                elif parts[0] == "end":
                    p2 = parts[2].split(" ")
                    ends.append((parts[1], float(p2[0])))
                elif parts[0] == "argv":
                    argvs.append((parts[1], json.loads(parts[2])))
        return starts, ends, argvs

    def _max_overlap(self) -> int:
        starts, ends, _ = self._records()
        events = [(t, 1) for _, t in starts] + [(t, -1) for _, t in ends]
        cur = best = 0
        for _, delta in sorted(events):
            cur += delta
            best = max(best, cur)
        return best

    # --- N dosya tamamlanır, boyutlar doğrulanır, paralellik görülür ---

    def test_all_files_complete_and_sizes_verified_in_parallel(self):
        sizes = {
            "model-00001-of-00003.safetensors": 4000,
            "model-00002-of-00003.safetensors": 5000,
            "model-00003-of-00003.safetensors": 3000,
            "config.json": 1000,
            "tokenizer.json": 2000,
            "model.safetensors.index.json": 1500,
        }
        self._sizes(sizes)
        self.env["FAKE_CURL_SLEEP"] = "0.15"
        self._run(dict(sizes), max_parallel=4)

        for n, sz in sizes.items():
            target = self.dest / n
            self.assertTrue(target.exists(), f"{n} inmiş olmalı")
            self.assertEqual(target.stat().st_size, sz, f"{n} boyutu doğrulanmalı")
            self.assertEqual(target.read_bytes(), payload_for(n, sz))
            self.assertFalse((self.dest / (n + ".curlpart")).exists(),
                             f"{n} için .curlpart kalmamalı")

        overlap = self._max_overlap()
        self.assertGreaterEqual(overlap, 2, "gerçek paralellik bekleniyor")
        self.assertLessEqual(overlap, 4, "max_parallel üst sınırı aşılmamalı")

    def test_max_parallel_caps_concurrency(self):
        sizes = {f"model-0000{i}-of-00005.safetensors": 2000 for i in range(1, 6)}
        self._sizes(sizes)
        self.env["FAKE_CURL_SLEEP"] = "0.15"
        self._run(dict(sizes), max_parallel=2)
        for n, sz in sizes.items():
            self.assertEqual((self.dest / n).stat().st_size, sz)
        self.assertLessEqual(self._max_overlap(), 2, "en fazla 2 eşzamanlı curl")

    # --- resume semantiği: .curlpart + `-C -` kaldığı yerden devam ---

    def test_resume_continues_from_curlpart(self):
        sizes = {"model-00001-of-00001.safetensors": 4000}
        self._sizes(sizes)
        n = "model-00001-of-00001.safetensors"
        full = payload_for(n, 4000)
        part = self.dest / (n + ".curlpart")
        part.write_bytes(full[:2000])  # yarım kalmış önceki oturum

        self._run(dict(sizes))

        self.assertEqual((self.dest / n).read_bytes(), full, "resume tamamlanmalı")
        self.assertFalse(part.exists())
        starts, _, argvs = self._records()
        self.assertEqual(len(starts), 1, "resume: tek çağrı yeterli olmalı")
        self.assertTrue(
            any(a[i:i + 2] == ["-C", "-"] for _, a in argvs for i in range(len(a) - 1)),
            "curl -C - ile resume")

    # --- sessiz bozulma yok: boyut tutmayan dosya asla hedefe alınmaz ---

    def test_size_mismatch_never_promoted_to_target(self):
        sizes = {"model-00002-of-00002.safetensors": 3000}
        self._sizes(sizes)
        self.env["FAKE_CURL_SHORT_SUBSTR"] = "00002"
        n = "model-00002-of-00002.safetensors"

        with self.assertRaises(RuntimeError):
            self._run(dict(sizes), max_attempts=2)

        self.assertFalse((self.dest / n).exists(),
                         "boyutu tutmayan dosya hedefe dönüştürülmemeli")
        part = self.dest / (n + ".curlpart")
        self.assertTrue(part.exists(), "kısmi dosya silinmemeli")
        self.assertEqual(part.stat().st_size, 2999)

    # --- hata: ameliyat temiz iptal, kısmi dosya resume için korunur ---

    def test_failure_aborts_cleanly_and_preserves_partial(self):
        sizes = {f"model-0000{i}-of-00004.safetensors": 4000 for i in range(1, 5)}
        self._sizes(sizes)
        self.env["FAKE_CURL_FAIL_SUBSTR"] = "00002"
        self.env["FAKE_CURL_SLEEP"] = "0.2"
        bad = "model-00002-of-00004.safetensors"

        t0 = time.monotonic()
        with self.assertRaises(RuntimeError) as ctx:
            self._run(dict(sizes), max_parallel=4, max_attempts=2)
        elapsed = time.monotonic() - t0

        self.assertIn(bad, str(ctx.exception), "hata hangi shard'ı adıyla söylemeli")
        self.assertLess(elapsed, 10, "abort temiz ve hızlı olmalı")

        # başarısız shard: hedef yok, yarım .curlpart resume için korunur
        self.assertFalse((self.dest / bad).exists())
        part = self.dest / (bad + ".curlpart")
        self.assertTrue(part.exists(), "kısmi dosya resume için korunmalı")
        self.assertEqual(part.stat().st_size, 2000)
        self.assertEqual(part.read_bytes(), payload_for(bad, 4000)[:2000])

        # diğer dosyalar: ya tam inmiş (doğru boyut) ya kısmi — asla bozuk hedef
        for n, sz in sizes.items():
            target = self.dest / n
            if target.exists():
                self.assertEqual(target.stat().st_size, sz,
                                 f"{n} hedefe tam boyutuyla geçmeli")

    # --- --limit-rate her sürece ayrı ayrı, tutarlı uygulanır ---

    def test_limit_rate_applied_per_process(self):
        sizes = {f"model-0000{i}-of-00003.safetensors": 1000 for i in range(1, 4)}
        self._sizes(sizes)
        self._run(dict(sizes), limit_rate="12M")

        _, _, argvs = self._records()
        self.assertEqual(len(argvs), 3)
        for n, a in argvs:
            self.assertIn("--limit-rate", a, f"{n}: --limit-rate her süreçte olmalı")
            self.assertEqual(a[a.index("--limit-rate") + 1], "12M",
                             f"{n}: limit değeri tutarlı olmalı")

    # --- çift-format güvenliği: shard'lar varsa consolidated asla karışmaz ---

    def test_never_mixes_consolidated_with_shards(self):
        sizes = {
            "consolidated.safetensors": 999,
            "model-00001-of-00002.safetensors": 2000,
            "model-00002-of-00002.safetensors": 2500,
        }
        self._sizes(sizes)
        self._run(dict(sizes))

        self.assertFalse((self.dest / "consolidated.safetensors").exists(),
                         "consolidated + shard karışmamalı")
        starts, _, _ = self._records()
        self.assertNotIn("consolidated.safetensors", [n for n, _ in starts])
        for n in ("model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"):
            self.assertEqual((self.dest / n).stat().st_size, sizes[n])


class TestMaxParallelFlag(unittest.TestCase):
    def test_default_is_four(self):
        a = build_arg_parser().parse_args(["org/model-x"])
        self.assertEqual(a.max_parallel, 4)
        self.assertEqual(a.max_parallel, DEFAULT_MAX_PARALLEL)

    def test_flag_overrides(self):
        a = build_arg_parser().parse_args(
            ["org/model-x", "--max-parallel", "2", "--limit-rate", "12M"])
        self.assertEqual(a.max_parallel, 2)
        self.assertEqual(a.limit_rate, "12M")


if __name__ == "__main__":
    unittest.main()
