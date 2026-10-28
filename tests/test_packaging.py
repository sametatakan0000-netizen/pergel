"""RED: Vane packaging — icon set, deb staging tree, launcher.

End users don't run scripts: they double-click a desktop icon. The .deb must
ship the full Vane identity — hicolor icon set, freedesktop launcher, the
engine under /usr/lib/vane, and a /usr/bin/vane entry point — with nothing
Chromium-ish visible in the menu. The deb must actually build with dpkg-deb.
"""
import os
import subprocess
import tempfile
import unittest

from PIL import Image

from src.brand.icons import render_icons
from src.brand.package import build_deb, stage_tree

SIZES = (16, 32, 48, 128, 256, 512)


class TestIconSet(unittest.TestCase):
    def test_renders_all_hicolor_png_sizes(self):
        with tempfile.TemporaryDirectory() as td:
            out = render_icons(td)
            for s in SIZES:
                p = out["png"].format(size=s)
                self.assertTrue(os.path.isfile(p), f"missing {s}px icon")
                with Image.open(p) as im:
                    self.assertEqual(im.size, (s, s))

    def test_icons_carry_the_accent_not_blank(self):
        with tempfile.TemporaryDirectory() as td:
            out = render_icons(td)
            with Image.open(out["png"].format(size=256)) as im:
                colors = im.convert("RGB").getcolors(maxcolors=100_000)
            # mint accent (#3DE1BE = 61,225,190) pixels must exist
            self.assertTrue(any(c[1] == (61, 225, 190) for c in colors),
                            "icon must contain the brand accent")

    def test_scalable_svg_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = render_icons(td)
            with open(out["svg"]) as f:
                svg = f.read()
            self.assertIn("<svg", svg)
            self.assertIn("3DE1BE", svg.upper())


class TestDebStaging(unittest.TestCase):
    def test_tree_ships_identity_and_launcher(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.path.join(td, "vane-browser_0.1.0_amd64")
            stage_tree(root)
            self.assertTrue(os.access(os.path.join(root, "usr/bin/vane"),
                                      os.X_OK))
            with open(os.path.join(root, "usr/share/applications/"
                                        "vane.desktop")) as f:
                desktop = f.read()
            self.assertIn("Name=Vane", desktop)
            self.assertIn("Icon=vane", desktop)
            for s in SIZES:
                self.assertTrue(os.path.isfile(os.path.join(
                    root, f"usr/share/icons/hicolor/{s}x{s}/apps/vane.png")))
            self.assertTrue(os.path.isfile(os.path.join(
                root, "usr/share/icons/hicolor/scalable/apps/vane.svg")))
            # engine ships inside the package
            self.assertTrue(os.path.isfile(os.path.join(
                root, "usr/lib/vane/vane_app.py")))

    def test_control_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.path.join(td, "vane-browser_0.1.0_amd64")
            stage_tree(root)
            with open(os.path.join(root, "DEBIAN/control")) as f:
                control = f.read()
            self.assertIn("Package: vane-browser", control)
            self.assertIn("Architecture: all", control)
            self.assertIn("Depends:", control)
            self.assertIn("Homepage:", control)


class TestDebBuild(unittest.TestCase):
    def test_build_deb_produces_installable_package(self):
        with tempfile.TemporaryDirectory() as td:
            deb = build_deb(td)
            self.assertTrue(os.path.isfile(deb))
            meta = subprocess.run(["dpkg-deb", "-f", deb], check=True,
                                  capture_output=True, text=True).stdout
            self.assertIn("Package: vane-browser", meta)
            contents = subprocess.run(["dpkg-deb", "-c", deb], check=True,
                                      capture_output=True, text=True).stdout
            self.assertIn("./usr/bin/vane", contents)
            self.assertIn("vane.desktop", contents)


if __name__ == "__main__":
    unittest.main()
