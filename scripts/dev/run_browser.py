#!/usr/bin/env python3
"""Ürünü gerçek bir tarayıcı penceresinde çalıştır — motoru bizzat gez.

Adblock motoru (network + kozmetik + scriptlet + prosedürel) gerçek Chromium
penceresine CDP üzerinden bağlanır; sen gezindikçe reklam/izleyiciler gözünün
önünde engellenir, terminalde canlı sayaç akar.

Kullanım:
    .venv/bin/python scripts/dev/run_browser.py [filtre_dosyası ...]

Her filtre dosyası bir satır-bir-kural (adblock sözdizimi) taşır. Dosya
verilmezse yerleşik demo kuralları kullanılır. Pencereyi sen kapatana kadar
motor ayakta kalır.
"""
import asyncio
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.browser_engine.adblock_session import compile_adblock
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession

DEMO = [
    "||ads.example.com^",
    "||doubleclick.net^",
    "||googlesyndication.com^",
    "||google-analytics.com^",
    "##.sponsored-ad",
    "##.sidebar-ad",
    "##.native-ad",
    "##.promo-banner",
    "##.cookie-row",
    "#?#.slot:has-text(Sponsored)",
]


def load_filters(paths):
    lines = list(DEMO)
    for p in paths:
        with open(p, encoding="utf-8") as f:
            lines += [ln for ln in f.read().splitlines()
                      if ln.strip() and not ln.startswith("!")]
    return lines


async def main(paths):
    blocked = {"n": 0}

    def on_decision(p):
        if p["action"] != "allow":
            blocked["n"] += 1
            print(f"[{p['action'].upper()} #{blocked['n']}] {p['url'][:110]}")

    bundle = compile_adblock(load_filters(paths))
    print(f"[motor] {bundle.stats['total']} kural "
          f"(network={bundle.stats['network']} cosmetic={bundle.stats['cosmetic']} "
          f"scriptlet={bundle.stats['scriptlets']} procedural={bundle.stats['procedural']})")
    print("[motor] gerçek pencere açılıyor — gezin, pencereyi kapattığınızda motor durur.")

    async with AdblockBrowserSession(bundle, headless=False, keep_open=True,
                                     on_blocked=on_decision) as sess:
        # pencere açık kalsın; kullanıcı kapatınca süreç biter
        while sess._proc.poll() is None:
            await asyncio.sleep(0.5)
        print(f"[motor] pencere kapandı. Toplam engellenen istek: {blocked['n']}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
