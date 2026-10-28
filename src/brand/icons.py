"""Pergel icon set — one monogram, rendered to the full hicolor scale.

The mark: graphite tile, faint mint ring, a compass (pergel) drawn as two
mint legs from a light pivot dot with a scribe arc between them — the
geometry of the drawing instrument the browser is named after. Raster icons
are rendered supersampled with PIL (no native deps) and downscaled with
LANCZOS so every size keeps the exact accent in stroke interiors.
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw

from . import tokens

SIZES = (16, 32, 48, 128, 256, 512)

# the legs path — shared by SVG and the test suite as the mark signature
LEGS = "M30 70 L48 26 L66 70"
ARC = "M32 62 Q48 78 64 62"


def icon_svg() -> str:
    """Scalable source-of-truth mark."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        f'<rect x="2" y="2" width="92" height="92" rx="22" fill="{tokens.BG}"/>'
        f'<circle cx="48" cy="48" r="38" stroke="{tokens.ACCENT}" '
        'stroke-width="2.5" opacity="0.55" fill="none"/>'
        f'<path d="{LEGS}" stroke="{tokens.ACCENT}" '
        'stroke-width="7" stroke-linecap="round" stroke-linejoin="round" '
        'fill="none"/>'
        f'<path d="{ARC}" stroke="{tokens.ACCENT}" '
        'stroke-width="3.5" stroke-linecap="round" fill="none" opacity="0.8"/>'
        f'<circle cx="48" cy="26" r="5" fill="{tokens.TEXT}"/>'
        "</svg>"
    )


def _draw_mark(im: Image.Image) -> None:
    d = ImageDraw.Draw(im)
    w, h = im.size
    s = w / 96.0

    def pt(x, y):
        return (x * s, y * s)

    d.rounded_rectangle([pt(2, 2), pt(94, 94)], radius=int(22 * s),
                        fill=tokens.rgb(tokens.BG))
    ring_w = max(2, int(2.5 * s))
    d.ellipse([pt(10, 10), pt(86, 86)], outline=tokens.rgb(tokens.ACCENT),
              width=ring_w)
    leg_w = max(3, int(7 * s))
    a = tokens.rgb(tokens.ACCENT)
    d.line([pt(48, 26), pt(30, 70)], fill=a, width=leg_w)
    d.line([pt(48, 26), pt(66, 70)], fill=a, width=leg_w)
    r = leg_w // 2
    for cx, cy in ((30, 70), (66, 70)):
        d.ellipse([pt(cx - r / s, cy - r / s), pt(cx + r / s, cy + r / s)],
                  fill=a)
    # scribe arc between the legs (bottom half of the arc box)
    arc_w = max(2, int(3.5 * s))
    d.arc([pt(32, 46), pt(64, 78)], start=0, end=180, fill=a, width=arc_w)
    # pivot dot
    px, py = pt(48, 26)
    pr = max(2, int(5 * s))
    d.ellipse([px - pr, py - pr, px + pr, py + pr],
              fill=tokens.rgb(tokens.TEXT))


def render_icon(size: int) -> Image.Image:
    """One icon at ``size`` px, supersampled 4x for clean antialiasing."""
    big = Image.new("RGB", (size * 4, size * 4), (0, 0, 0, 0))
    _draw_mark(big)
    return big.resize((size, size), Image.LANCZOS)


def render_icons(out_dir: str) -> dict:
    """Write ``pergel.svg`` and ``pergel-{size}.png`` into ``out_dir``.

    Returns ``{"svg": <path>, "png": <template with {size}>}``.
    """
    os.makedirs(out_dir, exist_ok=True)
    svg_path = os.path.join(out_dir, "pergel.svg")
    with open(svg_path, "w") as f:
        f.write(icon_svg())
    png_tpl = os.path.join(out_dir, "pergel-{size}.png")
    for size in SIZES:
        render_icon(size).save(png_tpl.format(size=size))
    return {"svg": svg_path, "png": png_tpl}
