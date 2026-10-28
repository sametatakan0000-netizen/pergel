"""Debian packaging for Vane — stage tree + dpkg-deb build.

Layout (the identity users see):

  /usr/bin/vane                       double-click entry point
  /usr/share/applications/vane.desktop
  /usr/share/icons/hicolor/*/apps/pergel.png + scalable/pergel.svg
  /usr/lib/pergel/{vane_app.py, brand/, browser_engine/}

The menu shows only "Pergel" — no python/Chromium traces in the launcher.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from .icons import SIZES, render_icons
from .render import render_desktop_entry, write_extension

PKG = "pergel-browser"
VERSION = "0.1.0"
_ARCH = "all"

_CONTROL = f"""Package: {PKG}
Version: {VERSION}
Section: web
Priority: optional
Architecture: {_ARCH}
Depends: python3 (>= 3.10), python3-websockets
Recommends: chromium | chromium-browser | google-chrome-stable
Maintainer: Pergel Team <pergel@localhost>
Description: Pergel - minimalist AI-native web browser
 Pergel is a double-click web browser with a built-in ad/tracker blocking
 engine, DNS-rebinding protection and a live shield panel.
Homepage: https://github.com/hfy/ai_browser_farm
"""

_LAUNCHER = """#!/usr/bin/env python3
# Pergel launcher — installed entry point (users never see this file).
import os
import sys

sys.path.insert(0, "/usr/lib/pergel")
from vane_app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
"""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def stage_tree(root: str) -> str:
    """Build the package file tree under ``root``; returns ``root``."""
    # --- control metadata
    os.makedirs(os.path.join(root, "DEBIAN"), exist_ok=True)
    with open(os.path.join(root, "DEBIAN/control"), "w") as f:
        f.write(_CONTROL)

    # --- launcher
    bindir = os.path.join(root, "usr/bin")
    os.makedirs(bindir, exist_ok=True)
    launcher = os.path.join(bindir, "pergel")
    with open(launcher, "w") as f:
        f.write(_LAUNCHER)
    os.chmod(launcher, 0o755)
    # compat alias for muscle memory (vane -> pergel)
    alias = os.path.join(bindir, "vane")
    if not os.path.lexists(alias):
        os.symlink("pergel", alias)

    # --- desktop entry
    appdir = os.path.join(root, "usr/share/applications")
    os.makedirs(appdir, exist_ok=True)
    with open(os.path.join(appdir, "pergel.desktop"), "w") as f:
        f.write(render_desktop_entry())

    # --- icon set (hicolor tree)
    with tempfile.TemporaryDirectory() as td:
        out = render_icons(td)
        for size in SIZES:
            d = os.path.join(root, f"usr/share/icons/hicolor/{size}x{size}/apps")
            os.makedirs(d, exist_ok=True)
            shutil.copy(out["png"].format(size=size),
                        os.path.join(d, "pergel.png"))
        svgdir = os.path.join(root, "usr/share/icons/hicolor/scalable/apps")
        os.makedirs(svgdir, exist_ok=True)
        shutil.copy(out["svg"], os.path.join(svgdir, "pergel.svg"))

    # --- engine + brand code under /usr/lib/vane
    libdir = os.path.join(root, "usr/lib/pergel")
    os.makedirs(libdir, exist_ok=True)
    for pkg in ("brand", "browser_engine"):
        shutil.copytree(os.path.join(_REPO_ROOT, "src", pkg),
                        os.path.join(libdir, pkg),
                        ignore=shutil.ignore_patterns("__pycache__", ".*"))
    # top-level entry module next to the packages
    shutil.copy(os.path.join(_REPO_ROOT, "src/brand/vane_app.py"),
                os.path.join(libdir, "vane_app.py"))
    # new-tab override extension (chrome_url_overrides.newtab)
    write_extension(os.path.join(libdir, "extension"))
    return root


def build_deb(out_dir: str) -> str:
    """Stage and build the .deb with dpkg-deb; returns the package path."""
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, f"{PKG}_{VERSION}_{_ARCH}")
        stage_tree(root)
        deb = os.path.join(out_dir, f"{PKG}_{VERSION}_{_ARCH}.deb")
        subprocess.run(
            ["dpkg-deb", "--build", "--root-owner-group", root, deb],
            check=True, capture_output=True, text=True)
    return deb
