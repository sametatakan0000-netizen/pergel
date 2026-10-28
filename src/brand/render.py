"""Branded surface renderers for Vane.

Every user-visible surface is rendered from ``tokens`` so the identity stays
consistent: new-tab page, shield panel (live block counter), Chromium theme
preferences and the freedesktop launcher entry. All HTML is a single inline
document — zero external requests (micro-minimalist, offline-safe).
"""
from __future__ import annotations

from . import tokens

_MONOGRAM = (
    '<svg class="monogram" viewBox="0 0 96 96" fill="none" aria-label="Vane">'
    '<circle cx="48" cy="48" r="44" stroke="{accent}" stroke-width="2.5" '
    'opacity="0.55"/>'
    '<path d="M28 30 L48 68 L68 30" stroke="{accent}" stroke-width="7" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M48 68 L48 22" stroke="{text}" stroke-width="3.5" '
    'stroke-linecap="round" opacity="0.8"/>'
    "</svg>"
).format(accent=tokens.ACCENT, text=tokens.TEXT)

_BASE_CSS = f"""
  :root {{
    --bg: {tokens.BG}; --surface: {tokens.SURFACE}; --surface2: {tokens.SURFACE_2};
    --text: {tokens.TEXT}; --muted: {tokens.MUTED}; --accent: {tokens.ACCENT};
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: system-ui, "Inter", "Segoe UI", sans-serif;
    background: radial-gradient(1200px 700px at 50% -10%, #1a2029 0%, var(--bg) 55%);
    color: var(--text); -webkit-font-smoothing: antialiased;
    letter-spacing: -0.01em;
  }}"""


def render_ntp() -> str:
    """The branded new-tab page: monogram, wordmark, clock, shield chip."""
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>{tokens.NAME}</title>
<style>{_BASE_CSS}
  main {{ min-height: 100vh; display: flex; flex-direction: column;
          align-items: center; justify-content: center; gap: 22px; }}
  .monogram {{ width: 92px; height: 92px; filter: drop-shadow(0 10px 40px #3de1be2e); }}
  .wordmark {{ font-size: 30px; font-weight: 650; letter-spacing: 0.14em;
               text-transform: uppercase; }}
  .wordmark b {{ color: var(--accent); font-weight: 650; }}
  .tagline {{ color: var(--muted); font-size: 13.5px; letter-spacing: 0.02em; }}
  .clock {{ font-size: 66px; font-weight: 250; letter-spacing: -0.03em;
            font-variant-numeric: tabular-nums; margin-top: 8px; }}
  .bar {{ width: min(520px, 84vw); height: 52px; border-radius: 26px;
          background: var(--surface); border: 1px solid #262b35;
          display: flex; align-items: center; padding: 0 22px; gap: 12px;
          color: var(--muted); font-size: 15px; }}
  .bar .dot {{ width: 8px; height: 8px; border-radius: 50%;
               background: var(--accent); box-shadow: 0 0 12px var(--accent); }}
  .chip {{ display: flex; align-items: center; gap: 9px; padding: 9px 18px;
           border-radius: 999px; background: var(--surface); font-size: 13px;
           color: var(--muted); border: 1px solid #232833; }}
  .chip b {{ color: var(--accent); font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<main>
  {_MONOGRAM}
  <div class="wordmark">VA<b>N</b>E</div>
  <div class="tagline">{tokens.TAGLINE}</div>
  <div class="clock" id="clock">--:--</div>
  <div class="bar"><span class="dot"></span>Ara ya da adres yaz</div>
  <div class="chip">kalkan aktif · <b id="blocked">0</b> istek engellendi</div>
</main>
<script>
  const t = () => {{
    document.getElementById('clock').textContent =
      new Date().toLocaleTimeString('tr-TR', {{hour: '2-digit', minute: '2-digit'}});
  }};
  t(); setInterval(t, 10000);
</script>
</body>
</html>
"""


def render_shield_panel(stats_port: int) -> str:
    """Compact shield panel: live blocked counter polled from the local
    stats endpoint (the Brave-shield-style differentiator)."""
    return f"""<!doctype html>
<html lang="tr">
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
<header>{_MONOGRAM}<span class="name">{tokens.NAME} Kalkan</span></header>
<div class="count"><div class="num" id="num">0</div>
  <div class="lbl">bugün engellenen istek</div></div>
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
    python traces: the menu shows only Vane."""
    return f"""[Desktop Entry]
Version=1.0
Type=Application
Name={tokens.NAME}
GenericName=Web Browser
Comment={tokens.TAGLINE}
Exec=vane %U
Icon=vane
Terminal=false
Categories=Network;WebBrowser;
Keywords=web;browser;internet;shield;adblock;
StartupWMClass=vane
"""
