"""Branded surface renderers for Vane.

Every user-visible surface is rendered from ``tokens`` so the identity stays
consistent: new-tab page, shield panel (live block counter), Chromium theme
preferences and the freedesktop launcher entry. All HTML is a single inline
document — zero external requests (micro-minimalist, offline-safe).
"""
from __future__ import annotations

import json
import os
from urllib.parse import quote_plus

from . import i18n, tokens


def search_url(query: str, mode: str = "web") -> str:
    """Google search routing.

    ``web`` — plain results; ``ai`` — Google AI Mode. The base is Chromium,
    so AI Mode (``udm=50``) works natively and free: Vane is an AI browser
    without a model bill.
    """
    q = quote_plus(query)
    if mode == "ai":
        return f"https://www.google.com/search?udm=50&q={q}"
    return f"https://www.google.com/search?q={q}"

_BASE_CSS = f"""
  :root {{
    --bg: {tokens.BG}; --surface: {tokens.SURFACE}; --surface2: {tokens.SURFACE_2};
    --text: {tokens.TEXT}; --muted: {tokens.MUTED}; --accent: {tokens.ACCENT};
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: system-ui, "Inter", "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text); -webkit-font-smoothing: antialiased;
    letter-spacing: -0.01em;
  }}"""


def render_ntp(lang: str = "en") -> str:
    """The new-tab page: bare wordmark + a search box that works.

    User's rule: no logo, no tagline, no clock, no decoration — "sadece yazı
    yeter", and the page stays **scriptless** (a hard product test). The box
    is a real GET form so it searches from file:// too.

    Global-first and scriptless: pre-rendered per locale (``vane_ntp_<lang>.html``
    variants written by the app), switched via plain links in the footer.
    RTL locales (ar/he/fa/ur) get ``dir="rtl"`` statically.
    """
    d = i18n.LOCALES.get(lang, i18n.LOCALES["en"])
    rtl = ' dir="rtl"' if lang in i18n.RTL_LANGS else ""
    return f"""<!doctype html>
<html lang="{lang}"{rtl}>
<head>
<meta charset="utf-8">
<title>{tokens.NAME}</title>
<style>{_BASE_CSS}
  main {{ min-height: 100vh; display: flex; flex-direction: column;
          align-items: center; justify-content: center; gap: 32px; }}
  .wordmark {{ font-size: 21px; font-weight: 600; letter-spacing: 0.24em;
               text-transform: uppercase; }}
  form {{ width: min(560px, 86vw); }}
  input[type=search] {{ width: 100%; height: 48px; border-radius: 12px;
          background: var(--surface); border: 1px solid #262b35;
          color: var(--text); font-size: 15px; padding: 0 18px; outline: none;
          font-family: inherit; -webkit-appearance: none; }}
  input[type=search]:focus {{ border-color: {tokens.ACCENT}; }}
  .modes {{ display: flex; gap: 4px; margin-top: 10px; padding-left: 4px; }}
  .modes button {{ background: none; border: none; color: var(--muted);
          font: inherit; font-size: 12.5px; letter-spacing: 0.02em;
          padding: 7px 14px; border-radius: 9px; cursor: pointer; }}
  .modes button:hover {{ color: var(--text); background: var(--surface); }}
  :focus-visible {{ outline: 2px solid {tokens.ACCENT}; outline-offset: 2px; }}
  footer {{ position: fixed; bottom: 14px; right: 18px; display: flex;
          gap: 10px; opacity: 0.45; }}
  footer a {{ color: var(--muted); text-decoration: none; font-size: 11px; }}
  footer a:hover {{ color: var(--text); }}
  footer a[aria-current] {{ color: {tokens.ACCENT}; }}
</style>
</head>
<body>
<main>
  <div class="wordmark">{tokens.NAME}</div>
  <form action="https://www.google.com/search" method="get" role="search">
    <input type="search" name="q" autofocus autocomplete="off"
           aria-label="search" placeholder="{d["search_ph"]}">
    <div class="modes">
      <button type="submit" name="udm" value="14">{d["web"]}</button>
      <button type="submit" name="udm" value="50">{d["ai_mode"]}</button>
    </div>
  </form>
</main>
<footer>{i18n.lang_links(lang)}</footer>
</body>
</html>
"""


_BACKGROUND_JS = """// Pergel surface glue: omnibox AI keyword, command bar, side panel.
const AI_URL = q => "https://www.google.com/search?udm=50&q=" + encodeURIComponent(q);

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

// omnibox: "ai <query>" lands in Google AI Mode
chrome.omnibox.onInputEntered.addListener((text) => {
  chrome.tabs.create({ url: AI_URL(text) });
});

// Alt+K: Arc-style command bar
chrome.commands.onCommand.addListener((command) => {
  if (command === "vane-command-bar") {
    chrome.windows.create({ url: "commandbar.html", type: "popup",
                            width: 560, height: 440 });
  }
});
"""


def extension_manifest() -> dict:
    """MV3 manifest: every new tab opens the Pergel NTP, plus the SOTA UX
    surfaces — ``ai`` omnibox keyword (AI Mode), Alt+K command bar and the
    side panel."""
    return {
        "manifest_version": 3,
        "name": tokens.NAME,
        "short_name": tokens.NAME,
        "version": "0.1.0",
        "description": tokens.TAGLINE,
        "chrome_url_overrides": {"newtab": "vane_ntp.html"},
        "background": {"service_worker": "background.js"},
        "side_panel": {"default_path": "panel.html"},
        "action": {"default_title": tokens.NAME},
        "omnibox": {"keyword": "ai"},
        "commands": {
            "vane-command-bar": {
                "suggested_key": {"default": "Alt+K"},
                "description": "Command bar",
            }
        },
        "permissions": ["tabs", "sidePanel"],
    }


def render_commandbar() -> str:
    """Arc-style command bar: type to filter open tabs or search
    (Web / AI Modu). Tab click activates the tab and closes the palette."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{tokens.NAME}</title>
<style>{_BASE_CSS}
  body {{ width: 100%; height: 100vh; background: var(--bg);
          padding: 18px; overflow: hidden; }}
  input {{ width: 100%; height: 44px; border-radius: 10px;
          background: var(--surface); border: 1px solid #262b35;
          color: var(--text); font-size: 14px; padding: 0 14px;
          outline: none; font-family: inherit; }}
  input:focus {{ border-color: {tokens.ACCENT}; }}
  .modes {{ display: flex; gap: 4px; margin: 10px 0 6px; }}
  .modes button {{ background: none; border: none; color: var(--muted);
          font: inherit; font-size: 12px; padding: 6px 12px;
          border-radius: 8px; cursor: pointer; }}
  .modes button:hover {{ color: var(--text); background: var(--surface); }}
  ul {{ list-style: none; margin-top: 8px; max-height: 62vh; overflow: auto; }}
  li {{ padding: 9px 12px; border-radius: 8px; font-size: 13px;
        color: var(--text); white-space: nowrap; overflow: hidden;
        text-overflow: ellipsis; cursor: pointer; }}
  li:hover {{ background: var(--surface); }}
  li .u {{ color: var(--muted); font-size: 11px; }}
</style>
</head>
<body>
<input id="q" aria-label="search" data-i18n-ph="cmd_ph"
           placeholder="Search or find a tab" autofocus autocomplete="off">
<div class="modes">
  <button data-mode="web" data-i18n="web">Web</button>
  <button data-mode="ai" data-i18n="ai_mode">AI Mode</button>
</div>
<ul id="tabs"></ul>
<script>
  let tabs = [];
  function search(mode) {{
    const q = document.getElementById('q').value.trim();
    if (!q) return;
    const url = mode === 'ai'
      ? 'https://www.google.com/search?udm=50&q=' + encodeURIComponent(q)
      : 'https://www.google.com/search?q=' + encodeURIComponent(q);
    chrome.tabs.create({{ url }});
    window.close();
  }}
  function render(filter) {{
    const ul = document.getElementById('tabs');
    ul.innerHTML = '';
    tabs.filter(t => !filter ||
        (t.title || '').toLowerCase().includes(filter) ||
        (t.url || '').toLowerCase().includes(filter))
      .forEach(t => {{
        const li = document.createElement('li');
        li.innerHTML = '<div>' + (t.title || t.url) +
                       '</div><div class="u">' + (t.url || '') + '</div>';
        li.onclick = () => chrome.tabs.update(t.id, {{ active: true }})
                              .then(() => window.close());
        ul.appendChild(li);
      }});
  }}
  document.querySelectorAll('.modes button').forEach(b =>
    b.onclick = () => search(b.dataset.mode));
  const q = document.getElementById('q');
  q.addEventListener('input', e => render(e.target.value.toLowerCase()));
  q.addEventListener('keydown', e => {{
    if (e.key === 'Enter') search('web');
    if (e.key === 'Escape') window.close();
  }});
  chrome.tabs.query({{}}, all => {{ tabs = all; render(''); }});
</script>
<script>{i18n.i18n_js()}</script>
</body>
</html>
"""


def render_side_panel() -> str:
    """Side panel: open-tab overview + free 'sentez' — synthesises the open
    tabs into one Google AI Mode query (zero cost, no model call)."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{tokens.NAME}</title>
<style>{_BASE_CSS}
  body {{ background: var(--bg); padding: 16px; }}
  h2 {{ font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
        color: var(--muted); font-weight: 600; margin-bottom: 12px; }}
  button.s {{ width: 100%; height: 38px; border-radius: 10px; border: none;
          background: {tokens.ACCENT}; color: #fff; font: inherit;
          font-size: 13px; font-weight: 600; cursor: pointer; }}
  button.s:hover {{ opacity: 0.88; }}
  ul {{ list-style: none; margin-top: 14px; }}
  li {{ padding: 8px 0; border-bottom: 1px solid #1c212a; font-size: 12.5px;
        color: var(--text); white-space: nowrap; overflow: hidden;
        text-overflow: ellipsis; cursor: pointer; }}
  li:hover {{ color: {tokens.ACCENT}; }}
</style>
</head>
<body>
<h2>{tokens.NAME} · <span data-i18n="tabs_label">Tabs</span></h2>
<button class="s" id="sentez" data-i18n="synthesize">Synthesize with AI Mode</button>
<ul id="tabs"></ul>
<script>
  chrome.tabs.query({{}}, tabs => {{
    const ul = document.getElementById('tabs');
    tabs.forEach(t => {{
      const li = document.createElement('li');
      li.textContent = t.title || t.url;
      li.onclick = () => chrome.tabs.update(t.id, {{ active: true }});
      ul.appendChild(li);
    }});
    document.getElementById('sentez').onclick = () => {{
      const titles = tabs.map(t => t.title).filter(Boolean).slice(0, 8)
                         .join(', ');
      const url = 'https://www.google.com/search?udm=50&q=' +
        encodeURIComponent((window.T && window.T.sentez_prompt ||
                'summarize and compare these: ') + titles);
      chrome.tabs.create({{ url }});
    }};
  }});
</script>
<script>{i18n.i18n_js()}</script>
</body>
</html>
"""


def performance_preferences() -> dict:
    """Speed layer — real Chromium 156 prefs (verified in the binary):
    vertical tab strip + memory saver mode."""
    return {
        "vertical_tabs": {"enabled": True},
        "performance_tuning": {"memory_saver_mode": {"state": 1}},
    }


def write_extension(dest: str) -> str:
    """Write the new-tab override extension (and its SOTA UX surfaces) into
    ``dest``."""
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "manifest.json"), "w") as f:
        json.dump(extension_manifest(), f, ensure_ascii=False, indent=2)
    with open(os.path.join(dest, "vane_ntp.html"), "w") as f:
        f.write(render_ntp())
    with open(os.path.join(dest, "background.js"), "w") as f:
        f.write(_BACKGROUND_JS)
    with open(os.path.join(dest, "commandbar.html"), "w") as f:
        f.write(render_commandbar())
    with open(os.path.join(dest, "panel.html"), "w") as f:
        f.write(render_side_panel())
    return dest


def render_shield_panel(stats_port: int) -> str:
    """Compact shield panel: live blocked counter polled from the local
    stats endpoint (the Brave-shield-style differentiator)."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{tokens.NAME} · Kalkan</title>
<style>{_BASE_CSS}
  body {{ width: 360px; min-height: 420px; background: var(--bg); }}
  header {{ display: flex; align-items: center; gap: 12px; padding: 20px 22px; }}
  .monogram {{ width: 34px; height: 34px; }}
  header .name {{ font-weight: 650; letter-spacing: 0.12em; font-size: 13px;
                  text-transform: uppercase; }}
  .count {{ text-align: center; padding: 18px 0 6px; }}
  .count .num {{ font-size: 68px; font-weight: 250; color: var(--accent);
                 font-variant-numeric: tabular-nums; letter-spacing: -0.03em; }}
  .count .lbl {{ color: var(--muted); font-size: 13px; letter-spacing: 0.06em;
                 text-transform: uppercase; }}
  ul {{ list-style: none; padding: 14px 22px 22px; }}
  li {{ display: flex; justify-content: space-between; gap: 14px;
        padding: 9px 0; border-bottom: 1px solid #1c212a; font-size: 12.5px; }}
  li .rule {{ color: var(--text); overflow: hidden; text-overflow: ellipsis;
              white-space: nowrap; }}
  li .n {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<header><span class="name" data-i18n="shield_label">{tokens.NAME} Shield</span></header>
<div class="count"><div class="num" id="num">0</div>
  <div class="lbl" data-i18n="blocked_today">requests blocked today</div></div>
<ul id="rules"></ul>
<script>
  async function tick() {{
    try {{
      const r = await fetch('http://127.0.0.1:{stats_port}/stats');
      const s = await r.json();
      document.getElementById('num').textContent = s.blocked_total;
      document.getElementById('rules').innerHTML =
        (s.top_rules || []).slice(0, 8).map(x =>
          `<li><span class="rule">${{x.rule}}</span><span class="n">${{x.count}}</span></li>`
        ).join('');
    }} catch (e) {{ /* motor kapalıysa sessiz kal */ }}
  }}
  tick(); setInterval(tick, 1500);
</script>
<script>{i18n.i18n_js()}</script>
</body>
</html>
"""


def theme_preferences() -> dict:
    """Chromium ``Preferences`` fragment painting frame/toolbar in brand
    colours (best-effort theming of the native window chrome)."""
    return {
        "theme": {
            "colors": {
                "frame": list(tokens.rgb(tokens.BG)),
                "toolbar": list(tokens.rgb(tokens.SURFACE)),
                "tab_text": list(tokens.rgb(tokens.TEXT)),
            }
        }
    }


def render_desktop_entry() -> str:
    """freedesktop.org launcher — what the user double-clicks. No Chromium or
    python traces: the menu shows only Pergel."""
    return f"""[Desktop Entry]
Version=1.0
Type=Application
Name={tokens.NAME}
GenericName=Web Browser
Comment={tokens.TAGLINE}
Comment[tr]=Minimalist AI-yerel web tarayıcı
Exec=pergel %U
Icon=pergel
StartupWMClass=Pergel
Terminal=false
Categories=Network;WebBrowser;
Keywords=web;browser;internet;shield;adblock;
StartupWMClass=pergel
"""
