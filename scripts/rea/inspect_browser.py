#!/usr/bin/env python3
"""Static inspection of an installed Chromium-family browser directory (passive, local files only).

Usage: python scripts/rea/inspect_browser.py <id> <app_dir> <out_json>
Reads: version strings, bundled extension manifests (audited), embedded vendor endpoints in
the extension/component JSON, native-messaging manifests. Does not execute the browser,
does not touch the network, and never writes outside <out_json>.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.rea.audit import audit_manifest  # noqa: E402
from src.rea.endpoints import extract_endpoints  # noqa: E402


def find_manifests(app_dir: str):
    out = []
    for root, _, files in os.walk(app_dir):
        if "manifest.json" in files and "/locales/" not in root.lower():
            out.append(os.path.join(root, "manifest.json"))
    return out


def main(argv):
    bid, app_dir, out_path = argv[1], argv[2], argv[3]
    report = {"id": bid, "app_dir": app_dir, "bundled_extensions": [], "vendor_endpoints": []}
    endpoints = set()
    for path in find_manifests(app_dir):
        try:
            m = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(m, dict):
            continue
        report["bundled_extensions"].append({
            "path": os.path.relpath(path, app_dir), "name": str(m.get("name", ""))[:80],
            "version": m.get("version"), "manifest_version": m.get("manifest_version"),
            "findings": audit_manifest(m)})
        endpoints.update(extract_endpoints(json.dumps(m)))
    for js in glob.glob(os.path.join(app_dir, "**", "*.json"), recursive=True)[:400]:
        try:
            if os.path.getsize(js) < 2_000_000:
                endpoints.update(extract_endpoints(open(js, encoding="utf-8", errors="ignore").read()))
        except OSError:
            pass
    report["vendor_endpoints"] = sorted(endpoints)[:300]
    # bundled Chromium milestone from the VERSION file or locales dir presence is not reliable; record what we can
    ver_files = glob.glob(os.path.join(app_dir, "**", "VERSION"), recursive=True)[:3]
    report["version_files"] = {os.path.relpath(p, app_dir): open(p).read().strip()[:200] for p in ver_files}
    json.dump(report, open(out_path, "w"), indent=2)
    print(f"{bid}: {len(report['bundled_extensions'])} bundled manifests, "
          f"{len(report['vendor_endpoints'])} endpoints, "
          f"{sum(len(e['findings']) for e in report['bundled_extensions'])} findings")


if __name__ == "__main__":
    main(sys.argv)
