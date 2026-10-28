"""Live demo: real Chromium + CDP adblock engine, visual proof.

Serves a realistic ad/tracker-heavy page over loopback HTTP, then renders it in
the real headless Chromium twice:
  (a) WITHOUT enforcement  -> ads/trackers visible, screenshot A
  (b) WITH the 4-layer engine -> ads blocked/hidden, clean markdown, screenshot B

Writes before/after screenshots + extracted markdown to docs/demo/. Real browser,
real CDP, no mock.
"""
import asyncio
import http.server
import json
import os
import socketserver
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.browser_engine.adblock_session import compile_adblock
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession, _chromium
from src.browser_engine import cdp_adblock_driver as drv

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "demo")
os.makedirs(OUT, exist_ok=True)

# A realistic article page polluted with ad/tracker shapes (self-hosted, no live web).
PAGE = """<!doctype html><html><head><meta charset='utf-8'><title>Kernel Haber — Çekirdek 7.0 Yayında</title>
<style>
 body{font-family:Georgia,serif;margin:0;background:#f4f1ea;color:#1a1a1a}
 .top{background:#20232a;color:#fff;padding:14px 22px;font-size:22px;font-weight:bold}
 .wrap{display:flex;gap:26px;max-width:960px;margin:22px auto}
 .main{flex:1} .side{width:250px}
 h1{font-size:30px;line-height:1.2} .byline{color:#777;font-size:13px;margin:8px 0 18px}
 p{line-height:1.65;font-size:17px}
 .sponsored-ad{background:#ffe9a8;border:2px dashed #d9a400;padding:16px;margin:18px 0;font-family:Arial}
 .sidebar-ad{background:#ffd0d0;border:2px solid #d33;padding:14px;margin:14px 0;font-family:Arial;font-size:14px}
 .native-ad{background:#dff0ff;border-left:5px solid #2a7;margin:16px 0;padding:12px}
 .promo-banner{background:#222;color:#0f0;padding:12px;text-align:center;font-family:Arial;letter-spacing:2px}
 .slot{margin:12px 0;padding:10px;background:#eee}
 .cookie-row{background:#333;color:#fff;padding:10px;font-family:Arial}
</style></head><body>
<div class='top'>Kernel Haber</div>
<div class='promo-banner'>★ SPONSOR: Kripto ile zengin olun — hemen tıklayın ★</div>
<div class='cookie-row'>Bu sitede 47 reklam ortağı çerez kullanır — kabul et</div>
<div class='wrap'>
 <div class='main'>
  <h1>Çekirdek 7.0 kararlı sürümü yayınlandı</h1>
  <div class='byline'>Yazan: Ayşe Yılmaz · 27 Ekim 2026 · 6 dk okuma</div>
  <p>Linux çekirdeği 7.0 bugün kararlı sürüm olarak duyuruldu. Yeni sürüm, ağ yığınında
  önemli iyileştirmeler, daha düşük gecikme ve gelişmiş bellek yönetimi getiriyor.</p>
  <div class='sponsored-ad'>SATILIK: Oyuncu klavyesi %90 indirim — TIKLA</div>
  <p>Topluluk, uzun süredir beklenen zamanlayıcı iyileştirmelerinin performans testlerinde
  ölçülebilir fark yarattığını bildiriyor. Bağımsız ölçümlerde gecikme %12 düştü.</p>
  <div class='native-ad'><b>İçerik ortağı:</b> Bulut sunucularında %50 indirim — kod: KERNEL</div>
  <p>Dağıtım sürümleri paketlerini önümüzdeki hafta yayınlamaya başlayacak. Kullanıcıların
  yükseltmeden önce sürücü uyumluluğunu kontrol etmesi öneriliyor.</p>
  <div class='slot'>Sponsored: masaj koltuğu kampanyası</div>
  <div class='slot'>Organik: okuyucu yorumları bölümü</div>
  <img src='http://127.0.0.1:PORT/ads.example.com/tracker.gif' width=1 height=1>
  <script src='http://127.0.0.1:PORT/ads.example.com/popup.js'></script>
 </div>
 <div class='side'>
  <div class='sidebar-ad'>REKLAM: Bahis sitesi — anında üyelik</div>
  <div class='sidebar-ad'>REKLAM: Kilo verdiren çay</div>
  <div class='slot'>Sponsored: VPN aboneliği</div>
  <div class='slot'>Organik: çok okunanlar listesi</div>
 </div>
</div>
</body></html>"""

FILTERS = [
    "||ads.example.com^",                       # network block (tracker.gif, popup.js)
    "test.com##.sponsored-ad",                  # cosmetic hide
    "test.com##.sidebar-ad",                    # cosmetic hide
    "test.com##.native-ad",                     # cosmetic hide
    "test.com##.promo-banner",                  # cosmetic hide
    "test.com##.cookie-row",                    # cosmetic hide
    "test.com#?#.slot:has-text(Sponsored)",     # procedural hide
]


def _serve(html):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


async def _snap(sess, url, host, path, timeout=20):
    await sess._render(url, host, timeout)
    shot = await sess._call("Page.captureScreenshot", {"format": "png"})
    import base64
    data = base64.b64decode(shot["result"]["data"])
    with open(path, "wb") as f:
        f.write(data)
    return data


async def main():
    html = PAGE
    srv, port = _serve(html)
    html = html.replace("PORT", str(port))
    srv.RequestHandlerClass.do_GET = lambda self: (
        self.send_response(200),
        self.send_header("Content-Type", "text/html; charset=utf-8"),
        self.send_header("Content-Length", str(len(html.encode()))),
        self.end_headers(),
        self.wfile.write(html.encode()),
    )
    url = f"http://127.0.0.1:{port}/"
    print("chromium:", _chromium())

    # (a) WITHOUT enforcement: empty filter list -> ads render
    clean_bundle = compile_adblock([])
    async with AdblockBrowserSession(clean_bundle) as s0:
        before_png = await _snap(s0, url, "test.com", os.path.join(OUT, "before_ads.png"))
        before_text = s0._last_text

    # (b) WITH the 4-layer engine -> ads blocked/hidden
    bundle = compile_adblock(FILTERS)
    async with AdblockBrowserSession(bundle) as s1:
        after_png = await _snap(s1, url, "test.com", os.path.join(OUT, "after_clean.png"))
        md = await s1.browse(url, host="test.com", timeout=20)
        after_text = s1._last_text

    report = {
        "chromium": _chromium(),
        "url": url,
        "filter_stats": bundle.stats,
        "before_text_len": len(before_text),
        "after_text_len": len(after_text),
        "before_has_ad": "SATILIK" in before_text and "REKLAM" in before_text,
        "after_has_ad": ("SATILIK" in after_text) or ("REKLAM" in after_text) or ("Sponsored" in after_text),
        "after_has_real_content": "çekirdeği" in after_text.lower() or "7.0" in after_text,
        "after_has_organic": "Organik" in after_text,
        "before_bytes": len(before_png),
        "after_bytes": len(after_png),
    }
    with open(os.path.join(OUT, "live_demo_report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "after_clean.md"), "w") as f:
        f.write("# Temiz markdown çıktısı (gerçek engine)\n\n")
        f.write(md["markdown"][0])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n--- AFTER (temiz metin) ---")
    print(after_text[:600])
    srv.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
