"""Vane application entry point — this is what ``/usr/bin/vane`` runs.

Wires the whole product together for the desktop user:

* compiles adblock filters (user/installed filter files, demo rules fallback),
* starts the loopback shield-stats endpoint,
* prepares the branded profile (theme Preferences, new-tab page, shield panel),
* launches the visible Chromium with the live enforcement engine attached.

No terminal knowledge required: launch icon -> browse.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Callable, Optional

try:  # repo layout (python -m / pytest)
    from src.brand import render, stats as stats_mod, tokens
    from src.browser_engine.adblock_session import compile_adblock
    from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
except ImportError:  # installed layout (/usr/lib/vane on sys.path)
    from brand import render, stats as stats_mod, tokens
    from browser_engine.adblock_session import compile_adblock
    from browser_engine.cdp_adblock_driver import AdblockBrowserSession

VERSION = "0.1.0"

DEMO = [
    "||ads.example.com^",
    "||doubleclick.net^",
    "||googlesyndication.com^",
    "||google-analytics.com^",
    "##.sponsored-ad",
    "##.sidebar-ad",
    "##.native-ad",
    "##.promo-banner",
]


def user_dirs() -> dict:
    """Per-user Vane dirs (config profile + filters)."""
    cfg = os.path.join(os.path.expanduser("~"), ".config", "vane")
    dirs = {
        "config": cfg,
        "profile": os.path.join(cfg, "profile"),
        "filters": os.path.join(cfg, "filters"),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def load_filters(paths: Optional[list] = None) -> list:
    """Filter lines from given files plus every ``*.txt`` in the user's
    filter dir; demo rules as the fallback floor."""
    lines = list(DEMO)
    candidates = list(paths or [])
    d = user_dirs()["filters"]
    candidates += sorted(
        os.path.join(d, f) for f in os.listdir(d) if f.endswith(".txt"))
    for p in candidates:
        with open(p, encoding="utf-8") as f:
            lines += [ln for ln in f.read().splitlines()
                      if ln.strip() and not ln.startswith("!")]
    return lines


def make_on_blocked(shield: "stats_mod.ShieldStats",
                    sink: Optional[Callable[[dict], None]] = None
                    ) -> Callable[[dict], None]:
    """Engine decision callback: feeds the live shield counter (and an
    optional terminal/log sink) without touching socket traffic."""
    def on_decision(decision: dict) -> None:
        shield.record(decision)
        if sink is not None:
            sink(decision)
    return on_decision


def prepare_profile(profile_dir: str, shield_port: int) -> str:
    """Write the branded surfaces into the Chromium profile dir.

    Returns the new-tab page path (to be opened as ``file://`` URL).
    """
    default = os.path.join(profile_dir, "Default")
    os.makedirs(default, exist_ok=True)
    prefs_path = os.path.join(default, "Preferences")
    prefs = {}
    if os.path.isfile(prefs_path):
        try:
            with open(prefs_path) as f:
                prefs = json.load(f)
        except (ValueError, OSError):
            prefs = {}
    prefs.update(render.theme_preferences())
    with open(prefs_path, "w") as f:
        json.dump(prefs, f)
    ntp = os.path.join(profile_dir, "vane_ntp.html")
    with open(ntp, "w") as f:
        f.write(render.render_ntp())
    shield = os.path.join(profile_dir, "vane_shield.html")
    with open(shield, "w") as f:
        f.write(render.render_shield_panel(shield_port))
    return ntp


async def run(filter_paths: Optional[list] = None,
              profile_dir: Optional[str] = None) -> int:
    dirs = user_dirs()
    profile = profile_dir or dirs["profile"]
    shield = stats_mod.ShieldStats()
    stop, port = stats_mod.serve_stats(stats=shield)
    try:
        ntp = prepare_profile(profile, port)
        bundle = compile_adblock(load_filters(filter_paths))
        print(f"[{tokens.NAME}] motor hazır: {bundle.stats['total']} kural, "
              f"kalkan paneli 127.0.0.1:{port}")
        async with AdblockBrowserSession(
                bundle, headless=False, keep_open=True,
                on_blocked=make_on_blocked(shield),
                user_data_dir=profile,
                start_url="file://" + ntp) as sess:
            while sess._proc.poll() is None:
                await asyncio.sleep(0.5)
        print(f"[{tokens.NAME}] pencere kapandı. Engellenen: "
              f"{shield.snapshot()['blocked_total']}")
        return 0
    finally:
        stop()


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="vane",
        description=f"{tokens.NAME} — {tokens.TAGLINE}")
    ap.add_argument("filters", nargs="*",
                    help="adblock kural dosyalari (satir-bir-kural)")
    ap.add_argument("--profile-dir", default=None,
                    help="Chromium profil dizini (varsayilan: ~/.config/vane/profile)")
    ap.add_argument("--version", action="version",
                    version=f"{tokens.NAME} {VERSION}")
    args = ap.parse_args(argv)
    return asyncio.run(run(args.filters, args.profile_dir))


if __name__ == "__main__":
    sys.exit(main())
