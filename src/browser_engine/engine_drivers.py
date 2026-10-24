"""Gerçek tarayıcı motorları: tier-1 lightpanda (Zig/V8, `fetch --dump html`) ve
tier-2 Chromium (Playwright headless shell). tier-3 camofox bilinçli olarak ertelendi
(stealth, hukuki/ToS riski) ve düz-HTTP yedeğine düşer.

Politika değişmezleri: robots.txt HER motordan ÖNCE kontrol edilir; politika bloğu
FetchBlocked fırlatır ve eskalasyon asla bypass edemez. 2 MB gövde sınırı korunur.
"""
import os
import shutil
import subprocess
from typing import Optional

from src.browser_engine.worker import (
    MAX_BODY_BYTES,
    FetchBlocked,
    _allowed_by_robots,
    _default_url_driver,
)

LIGHTPANDA_TIMEOUT_S = 30
CHROMIUM_TIMEOUT_S = 30
_UA_BASE = "HermesBrowserFarm/1.0"


class EngineUnavailable(RuntimeError):
    """Engine missing or failed -> worker escalates to the next tier."""


def _lightpanda_bin() -> Optional[str]:
    cand = (os.environ.get("LIGHTPANDA_BIN")
            or shutil.which("lightpanda")
            or os.path.expanduser("~/.local/bin/lightpanda"))
    return cand if cand and os.path.exists(cand) else None


def _lightpanda_html(url: str, session_name: str) -> str:
    binary = _lightpanda_bin()
    if not binary:
        raise EngineUnavailable("lightpanda binary not installed")
    proc = subprocess.run(
        [binary, "fetch", url, "--dump", "html"],
        capture_output=True, timeout=LIGHTPANDA_TIMEOUT_S,
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0 or not out.strip():
        raise EngineUnavailable(f"lightpanda fetch failed (rc={proc.returncode})")
    return out[:MAX_BODY_BYTES]


def _chromium_html(url: str, session_name: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # shortcut: optional dep like trafilatura; require in production deploys
        raise EngineUnavailable("playwright not installed") from exc
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent=f"{_UA_BASE} (chromium-browser-use; {session_name})")
            page.goto(url, timeout=CHROMIUM_TIMEOUT_S * 1000, wait_until="load")
            return page.content()[:MAX_BODY_BYTES]
        finally:
            browser.close()
    # shortcut: one browser launch per fetch; pool/reuse when throughput matters


def engine_driver(engine: str, url: str, session_name: str) -> str:
    """`BrowserWorker.driver_fn` contract: raw HTML string, exception on failure."""
    if not _allowed_by_robots(url, "HermesBrowserFarm"):
        raise FetchBlocked(f"robots.txt disallows {url}")
    if engine == "lightpanda":
        return _lightpanda_html(url, session_name)
    if engine == "chromium-browser-use":
        return _chromium_html(url, session_name)
    # shortcut: camofox deferred (stealth opt-in + legal review), plain-HTTP until then
    return _default_url_driver(engine, url, session_name)
