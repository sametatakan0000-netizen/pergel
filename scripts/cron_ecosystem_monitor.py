#!/usr/bin/env python3
"""Deterministik Ekosistem ve Kod Tabanı Parmak İzi Betiği (Hermes Cron `monitor` için)."""
import os
import pathlib
import sys

REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, REPO_ROOT)
from src.devtools.codebase_graph import build_codebase_knowledge_graph
from src.devtools.self_evolution_engine import compute_ecosystem_fingerprint
from src.devtools.token_and_debt_hygiene import scan_shortcut_debt


def main() -> int:
    graph = build_codebase_knowledge_graph(os.path.join(REPO_ROOT, "src"))
    debt = scan_shortcut_debt(os.path.join(REPO_ROOT, "src"))
    state = {
        "graph_summary": graph["summary"],
        "dead_code_candidates": graph["dead_code_candidates"],
        "debt_count": len(debt),
        "tracked_sota_repos": [
            "NousResearch/hermes-agent",
            "rtk-ai/rtk",
            "DietrichGebert/ponytail",
            "JuliusBrussee/caveman",
            "upstash/context7",
            "Graphify-Labs/graphify",
            "tirth8205/code-review-graph",
            "DeusData/codebase-memory-mcp",
            "mattpocock/skills",
            "obra/superpowers",
        ],
    }
    print(compute_ecosystem_fingerprint(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
