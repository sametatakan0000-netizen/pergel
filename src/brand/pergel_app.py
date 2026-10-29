"""Pergel application entry point — this is what ``/usr/bin/pergel`` runs.

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
import shutil
import sys
from typing import Callable, Optional

try:  # repo layout (python -m / pytest)
    from src.brand import i18n, migrate, render, stats as stats_mod, tokens
    from src.browser_engine.adblock_session import compile_adblock
    from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
except ImportError:  # installed layout (/usr/lib/pergel on sys.path)
    from brand import i18n, migrate, render, stats as stats_mod, tokens
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
    """Per-user Pergel dirs (config profile + filters), with a one-time
    migration of the legacy ``~/.config/pergel`` layout."""
    home = os.path.expanduser("~")
    cfg = os.path.join(home, ".config", "pergel")
    legacy = os.path.join(home, ".config", "pergel")
    if not os.path.isdir(cfg) and os.path.isdir(legacy):
        shutil.copytree(legacy, cfg)
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


def launch_flags(extension_dir: str) -> list:
    """Window identity + chrome the user must never see.

    ``--class=Pergel`` gives the window its own WM_CLASS (dock/menu identity);
    ``--disable-infobars`` kills the "Chrome for Testing" banner and the
    ``--no-sandbox`` warning bar; the load-extension pair makes every new tab
    open the Pergel NTP instead of Chromium's Google page.
    """
    return ["--class=Pergel", "--disable-infobars",
            "--no-first-run", "--no-default-browser-check",
            "--disable-search-engine-choice-screen",
            "--disable-blink-features=AutomationControlled",
            "--load-extension=" + extension_dir,
            "--disable-extensions-except=" + extension_dir]


def ensure_extension() -> str:
    """Resolve (and materialise) the new-tab override extension.

    Installed layout ships it under /usr/lib/pergel/extension; repo/dev runs
    build it into the user config dir instead.
    """
    installed = os.path.join("/usr/lib/pergel", "extension")
    if os.path.isfile(os.path.join(installed, "manifest.json")):
        return installed
    return render.write_extension(
        os.path.join(user_dirs()["config"], "extension"))


def maybe_auto_migrate(profile_dir: str, home: Optional[str] = None) -> dict:
    """First-run data migration: pull bookmarks/history from every browser
    found on the machine into the Pergel profile. Runs ONCE (marker file);
    later runs never re-import. Counts only — no secret material."""
    # marker lives INSIDE the profile dir so every profile migrates once
    # and tests stay isolated (no shared /tmp or home state)
    marker = os.path.join(os.path.abspath(profile_dir), ".migrated")
    if os.path.exists(marker):
        return {}
    report = migrate.migrate(profile_dir, home=home)
    with open(marker, "w") as f:
        json.dump(report, f)
    return report


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
    prefs.update(render.performance_preferences())
    with open(prefs_path, "w") as f:
        json.dump(prefs, f)
    # global-first NTP: default in the SYSTEM language plus one pre-rendered
    # variant per locale (scriptless pages switch via plain links)
    lang = os.environ.get("LANG", "en").split(".")[0].split("_")[0].lower()
    if lang not in i18n.LOCALES:
        lang = "en"
    ntp = os.path.join(profile_dir, "pergel_ntp.html")
    with open(ntp, "w", encoding="utf-8") as f:
        f.write(render.render_ntp(lang))
    for code in i18n.LOCALES:
        with open(os.path.join(profile_dir, f"pergel_ntp_{code}.html"), "w", encoding="utf-8") as f:
            f.write(render.render_ntp(code))
    shield = os.path.join(profile_dir, "pergel_shield.html")
    with open(shield, "w", encoding="utf-8") as f:
        f.write(render.render_shield_panel(shield_port))
    panel = os.path.join(profile_dir, "pergel_panel.html")
    with open(panel, "w", encoding="utf-8") as f:
        f.write(render.render_side_panel(shield_port))
    return ntp


async def run(filter_paths: Optional[list] = None,
              profile_dir: Optional[str] = None) -> int:
    dirs = user_dirs()
    profile = profile_dir or dirs["profile"]
    shield = stats_mod.ShieldStats()
    stop, port = stats_mod.serve_stats(stats=shield)
    try:
        maybe_auto_migrate(profile)
        ntp = prepare_profile(profile, port)
        bundle = compile_adblock(load_filters(filter_paths))
        ext = ensure_extension()
        print(f"[{tokens.NAME}] motor hazır: {bundle.stats['total']} kural, "
              f"kalkan paneli 127.0.0.1:{port}")
        async with AdblockBrowserSession(
                bundle, headless=False, keep_open=True,
                on_blocked=make_on_blocked(shield),
                user_data_dir=profile,
                start_url="file://" + ntp,
                extra_args=launch_flags(ext)) as sess:
            while sess._proc.poll() is None:
                await asyncio.sleep(0.5)
        print(f"[{tokens.NAME}] pencere kapandı. Engellenen: "
              f"{shield.snapshot()['blocked_total']}")
        return 0
    finally:
        stop()


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pergel",
        description=f"{tokens.NAME} — {tokens.TAGLINE}")
    ap.add_argument("filters", nargs="*",
                    help="adblock kural dosyalari (satir-bir-kural)")
    ap.add_argument("--profile-dir", default=None,
                    help="Chromium profil dizini (varsayilan: ~/.config/pergel/profile)")
    ap.add_argument("--migrate", action="store_true",
                    help="import data from other browsers (bookmarks, history)")
    ap.add_argument("--passwords-csv", default=None,
                    help="disa aktarilmis parola CSV dosyasi (url,username,password)")
    ap.add_argument("--home", default=None,
                    help="kaynak tarayici profillerinin aranacagi dizin (test kolayligi)")
    ap.add_argument("--version", action="version",
                    version=f"{tokens.NAME} {VERSION}")
    args = ap.parse_args(argv)
    if args.migrate:
        profile = args.profile_dir or user_dirs()["profile"]
        report = migrate.migrate(profile, home=args.home,
                                 passwords_csv=args.passwords_csv)
        print(f"[{tokens.NAME}] aktarim tamam: "
              f"{report['bookmarks']} yer imi, {report['history']} gecmis, "
              f"{report['passwords']} parola")
        return 0
    return asyncio.run(run(args.filters, args.profile_dir))


if __name__ == "__main__":
    sys.exit(main())
