"""AI-Native Browser Engine & Self-Evolution Lab Birleşik CLI Komuta Aracı."""
import argparse
import os
import pathlib
import json
import sys
import threading


REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
from src.devtools.codebase_graph import build_codebase_knowledge_graph
from src.devtools.security_audit import run_defensive_security_audit
from src.devtools.token_and_debt_hygiene import scan_shortcut_debt
from src.infra.hermes_config_builder import build_optimal_hermes_spec
from src.router.model_registry import fetch_profiles, save_snapshot
from src.api.server import BrowserFarmSaaSServer


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-Native Browser Farm & Lab CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("graph", help="Rebuild CODEBASE_GRAPH.json knowledge graph")
    sub.add_parser("doctor", help="Run full architecture, security, and debt audit")
    serve = sub.add_parser("serve", help="Serve the local router (Nous proxy must run separately)")
    serve.add_argument("--port", type=int, default=8090)
    serve.add_argument("--db-dir", default=REPO_ROOT)
    serve.add_argument("--nous-proxy-url", default="http://127.0.0.1:8645/v1")
    refresh = sub.add_parser("refresh-catalog", help="Rebuild verified model registry from public catalog + metadata (no inference)")
    refresh.add_argument("--registry-path", default=os.path.join(REPO_ROOT, "model_registry.json"))

    args = parser.parse_args()
    if args.command == "refresh-catalog":
        from datetime import datetime, timezone
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        profiles = fetch_profiles(fetched_at)
        save_snapshot(args.registry_path, profiles, fetched_at)
        print(json.dumps({
            "fetched_at": fetched_at, "total": len(profiles),
            "routable": sum(p.routable for p in profiles.values()),
            "catalog_only": sorted(m for m, p in profiles.items() if p.status == "catalog_only"),
        }, indent=2))
        return 0
    if args.command == "serve":
        server = BrowserFarmSaaSServer(
            port=args.port, db_dir=args.db_dir, nous_proxy_url=args.nous_proxy_url
        )
        stop = threading.Event()

        def catalog_loop() -> None:
            while not stop.is_set():
                try:
                    server.refresh_registry()
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    print(f"Registry refresh failed (keeping last snapshot): {exc}", file=sys.stderr)
                stop.wait(1200)

        threading.Thread(target=catalog_loop, daemon=True).start()
        server.start_background()
        print(f"Router listening on http://127.0.0.1:{server.port}/v1", flush=True)
        try:
            while True:
                stop.wait(3600)
        except KeyboardInterrupt:
            stop.set()
            server.shutdown()
        return 0

    if args.command == "graph":
        graph = build_codebase_knowledge_graph(os.path.join(REPO_ROOT, "src"))
        print(json.dumps(graph["summary"], indent=2))
        return 0

    if args.command == "doctor":
        graph = build_codebase_knowledge_graph(os.path.join(REPO_ROOT, "src"))
        sec = run_defensive_security_audit(os.path.join(REPO_ROOT, "src"))
        debt = scan_shortcut_debt(os.path.join(REPO_ROOT, "src"))
        spec = build_optimal_hermes_spec()
        report = {
            "status": "PROTOTYPE" if sec["status"] == "PASS" else "WARNING",
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
