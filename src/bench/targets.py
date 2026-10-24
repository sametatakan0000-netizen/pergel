"""Builds Target objects from the install manifest (~/.local/share/bench-browsers/manifest.json)."""
import json
import os
from typing import Callable, Dict

from src.bench.adapters import CdpAdapter, PlaywrightAdapter, chromium_argv, lightpanda_argv
from src.bench.install import MANIFEST
from src.bench.runner import Target

CHROMIUM_KINDS = {"chromium"}
PW_PREFIXES = {"firefox-pw": "~/.cache/ms-playwright/firefox-", "webkit-pw": "~/.cache/ms-playwright/webkit-"}


def load_manifest() -> Dict[str, dict]:
    if not os.path.exists(MANIFEST):
        return {}
    return json.load(open(MANIFEST))


def build_target(target_id: str, entry: dict) -> Target:
    kind, exe = entry["kind"], entry["exe"]
    launch_env = entry.get("launch_env", "")
    if launch_env:
        for pair in launch_env.split():
            if "=" in pair:
                key, val = pair.split("=", 1)
                os.environ[key] = os.path.expanduser(val)
    if kind == "lightpanda":
        return Target(target_id, lambda e=exe: CdpAdapter(target_id, lambda port, prof: lightpanda_argv(e, port)))
    if kind in CHROMIUM_KINDS:
        return Target(target_id, lambda e=exe: CdpAdapter(target_id, lambda port, prof: chromium_argv(e, port, prof)))
    if target_id in PW_PREFIXES:
        name = "firefox" if target_id == "firefox-pw" else "webkit"
        prefix = os.path.expanduser(PW_PREFIXES[target_id])
        return Target(target_id, lambda: PlaywrightAdapter(target_id, name, prefix))
    raise ValueError(f"unsupported kind {kind!r} for {target_id}")


def register_installed(registry: Dict[str, Callable[[], object]]) -> None:
    for tid, entry in load_manifest().items():
        try:
            target = build_target(tid, entry)
        except ValueError:
            continue
        registry[tid] = target.make_adapter
