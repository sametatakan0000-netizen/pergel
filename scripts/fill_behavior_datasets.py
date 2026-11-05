#!/usr/bin/env python3
"""Davranış testi kataloğunu gerçek kamuya açık veri setleriyle doldurur.

Kural (kullanıcı): mevcut public benchmark verisini kullan; kendi test
setimizi uydurmayız. Yalnız METADATA/görev verisi indirilir (ağırlık yok).

- kod       -> SWE-bench Verified (princeton-nlp/SWE-bench_Verified, 500 görev)
- araç      -> tau-bench retail + airline (sierra-research/tau-bench GitHub)
- güvenlik  -> AdvBench harmful_behaviors (llm-attacks) — PAQ/IA ret testi tabanı
- dil/karar -> Banking77 (PolyAI/banking77) — niyet sınıflandırma

Çıktılar: /home/pc/mahoraga_davranis_veri/*.jsonl + güncellenmiş
/home/pc/mahoraga_davranis_katalogu.json (doldurma alanları).
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request

OUT = "/home/pc/mahoraga_davranis_veri"
CATALOG = "/home/pc/mahoraga_davranis_katalogu.json"
UA = {"User-Agent": "mahoraga-fill/1.0"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def hf_rows(dataset: str, split: str, want: int) -> list[dict]:
    """HuggingFace datasets-server rows API (sayfa 100)."""
    rows, offset = [], 0
    while len(rows) < want:
        url = (
            f"https://datasets-server.huggingface.co/rows?dataset={urllib.parse.quote(dataset, safe='')}"
            f"&config=default&split={split}&offset={offset}&length=100"
        )
        data = json.loads(get(url))
        batch = [r["row"] for r in data.get("rows", [])]
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
    return rows[:want]


def write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    import urllib.parse  # noqa: F401 (hf_rows içinde kullanılır)
    os.makedirs(OUT, exist_ok=True)
    fill = {}

    # kod: SWE-bench Verified — tam 500 görev
    print("kod: SWE-bench Verified indiriliyor...")
    swe = hf_rows("princeton-nlp/SWE-bench_Verified", "test", 500)
    write_jsonl(f"{OUT}/kod_swebench_verified.jsonl",
                [{"id": r["instance_id"], "repo": r["repo"],
                  "problem_statement": r["problem_statement"],
                  "fail_to_pass": r.get("FAIL_TO_PASS")} for r in swe])
    fill["kod"] = {"kaynak": "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified",
                   "dosya": f"{OUT}/kod_swebench_verified.jsonl", "ornek": len(swe),
                   "alanlar": ["id", "repo", "problem_statement", "fail_to_pass"],
                   "ilk_ornek": swe[0]["instance_id"] if swe else None}

    # araç: tau-bench GitHub — görevler Python tasks.py içinde (veri=AST)
    print("araç: tau-bench (tasks.py AST) indiriliyor...")
    import ast

    def node_val(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [node_val(e) for e in node.elts]
        if isinstance(node, ast.Dict):
            return {node_val(k): node_val(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Call):
            return {"_call": getattr(node.func, "id", "?"),
                    **{kw.arg: node_val(kw.value) for kw in node.keywords if kw.arg}}
        return None

    arac_recs = []
    for dom, fname in (("retail", "tasks.py"), ("retail", "tasks_dev.py"),
                       ("airline", "tasks.py"), ("airline", "tasks_test.py")):
        try:
            src = get(f"https://raw.githubusercontent.com/sierra-research/tau-bench/main/tau_bench/envs/{dom}/{fname}").decode("utf-8", "replace")
        except Exception:
            continue
        tree = ast.parse(src)
        for stmt in tree.body:
            targets = [t.id for t in getattr(stmt, "targets", []) if isinstance(t, ast.Name)]
            if isinstance(stmt, ast.Assign) and "tasks" in targets and isinstance(stmt.value, ast.List):
                for el in stmt.value.elts:
                    rec = {"domain": dom, "split_file": fname}
                    rec.update(node_val(el) or {})
                    arac_recs.append(rec)
    write_jsonl(f"{OUT}/arac_taubench.jsonl", arac_recs)
    fill["arac"] = {"kaynak": "https://github.com/sierra-research/tau-bench (tau_bench/envs/*/tasks*.py, AST)",
                    "dosya": f"{OUT}/arac_taubench.jsonl", "ornek": len(arac_recs),
                    "dagilim": {d: sum(1 for r in arac_recs if r["domain"] == d) for d in ("retail", "airline")},
                    "ilk_ornek": arac_recs[0].get("id") if arac_recs else None}

    # güvenlik: AdvBench harmful_behaviors (PAQ/IA ret davranışı tabanı)
    print("güvenlik: AdvBench indiriliyor...")
    csv_raw = get("https://raw.githubusercontent.com/llm-attacks/llm-attacks/main/data/advbench/harmful_behaviors.csv").decode("utf-8", "replace")
    reader = list(csv.reader(csv_raw.splitlines()))
    hdr, body = reader[0], reader[1:]
    guv_recs = [{"id": f"adv-{i}", "goal": row[0]} for i, row in enumerate(body) if row]
    write_jsonl(f"{OUT}/guvenlik_advbench.jsonl", guv_recs)
    fill["guvenlik"] = {"kaynak": "https://github.com/llm-attacks/llm-attacks (AdvBench)",
                        "dosya": f"{OUT}/guvenlik_advbench.jsonl", "ornek": len(guv_recs),
                        "alanlar": ["id", "goal"], "not": "PAQ marjinal kayıp + IA ret testi tabanı"}

    # dil/karar: Banking77 niyet sınıflandırma (test split)
    print("dil/karar: Banking77 indiriliyor...")
    b77 = hf_rows("PolyAI/banking77", "test", 300)
    write_jsonl(f"{OUT}/dil_karar_banking77.jsonl",
                [{"id": f"b77-{i}", "niyet": r.get("label"), "metin": r.get("text")}
                 for i, r in enumerate(b77)])
    fill["dil_karar"] = {"kaynak": "https://huggingface.co/datasets/PolyAI/banking77",
                         "dosya": f"{OUT}/dil_karar_banking77.jsonl", "ornek": len(b77),
                         "alanlar": ["id", "niyet", "metin"],
                         "not": "karmaşık/niyet ayrışımı için sınıflandırma tabanı"}

    # kataloğu güncelle
    cat = json.load(open(CATALOG))
    for cls, info in fill.items():
        cat["suites"][cls]["doldurma"] = info
    cat["doldurma_tarihi"] = "2026-11-05"
    json.dump(cat, open(CATALOG, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v["ornek"] for k, v in fill.items()}, ensure_ascii=False))
    print("katalog güncellendi:", CATALOG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
