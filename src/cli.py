"""AI-Native Browser Engine & Self-Evolution Lab Birleşik CLI Komuta Aracı."""
import argparse
import json
import sys

from src.devtools.codebase_graph import build_codebase_knowledge_graph
from src.devtools.security_audit import run_defensive_security_audit
from src.devtools.token_and_debt_hygiene import scan_shortcut_debt
from src.infra.hermes_config_builder import build_optimal_hermes_spec


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-Native Browser Farm & Lab CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("graph", help="Rebuild CODEBASE_GRAPH.json knowledge graph")
    sub.add_parser("doctor", help="Run full architecture, security, and debt audit")

    args = parser.parse_args()
    if args.command == "graph":
        graph = build_codebase_knowledge_graph("/root/ai_browser_farm/src")
        print(json.dumps(graph["summary"], indent=2))
        return 0

    if args.command == "doctor":
        graph = build_codebase_knowledge_graph("/root/ai_browser_farm/src")
        sec = run_defensive_security_audit("/root/ai_browser_farm/src")
        debt = scan_shortcut_debt("/root/ai_browser_farm/src")
        spec = build_optimal_hermes_spec()
        report = {
            "status": "READY" if sec["status"] == "PASS" else "WARNING",
            "codebase_graph": graph["summary"],
            "security_audit": sec["status"],
            "shortcut_debt_count": len(debt),
            "hermes_aux_slots_verified": len(spec["auxiliary"]),
        }
        print(json.dumps(report, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
