"""A2-A7 native capability layer — thin wrappers over existing engine layers.

None of these adds a new engine. Each rides a layer built earlier:

- A2 reader mode      -> ``worker.html_to_clean_markdown``
- A3 dark mode        -> ``adblock_session._css_inject_iife`` (extra CSS)
- A4 focus block      -> ``rule_engine.compile_rules`` (DNR block rules)
- A5 page note        -> ``worker.html_to_clean_markdown`` + metadata
- A6 screenshot       -> CDP ``Page.captureScreenshot``
- A7 translate        -> pluggable Nous-backed translator, cached, fail-safe

A7 is a global product feature (translation is core value, not an add-on), so
the translator is a backend-independent callable: the caller wires the Nous
model; this layer handles structure, caching and fail-safety.
"""


import base64
from dataclasses import dataclass, field
from typing import Callable, Iterable, List

from .worker import html_to_clean_markdown

__all__ = [
    "DARK_MODE_CSS",
    "PageNote",
    "build_focus_engine",
    "capture_screenshot",
    "make_translator",
    "note_from_page",
    "reader_mode",
    "translate_lines",
    "dark_mode_injection",
]


# --- A2 reader mode ------------------------------------------------------
def reader_mode(raw_html: str) -> str:
    """Return the clean, ad-free reading markdown for a raw HTML page."""
    return html_to_clean_markdown(raw_html)


# --- A3 dark mode --------------------------------------------------------
# A conservative, universally-safe dark theme: dark page background, light
# text. Deliberately high-contrast and hue-neutral so it works on any site
# without per-site tuning (a global product default).
DARK_MODE_CSS = (
    "html, body { background-color: #1b1b1b !important; color: #e6e6e6 !important; }"
    " a { color: #8ab4f8 !important; }"
    " img, video { opacity: 0.92; }"
)


def dark_mode_injection(injected_css: str = "") -> str:
    """Build the document-start JS that applies dark mode (plus any CSS)."""
    from .adblock_session import _css_inject_iife

    combined = (injected_css + "\n" + DARK_MODE_CSS).strip()
    return _css_inject_iife(combined)


# --- A4 focus block ------------------------------------------------------
def build_focus_engine(blocked_hosts: Iterable[str]):
    """Build a DNR engine that blocks the given hosts (distraction sites).

    Empty list -> allow-all engine (no distraction policy). Subdomains are
    covered by the ``||host^`` anchor form.
    """
    from .rule_engine import compile_rules

    rules = []
    for i, host in enumerate(blocked_hosts, start=1):
        host = host.strip()
        if not host:
            continue
        rules.append({
            "id": i,
            "priority": 1,
            "action": {"type": "block"},
            "condition": {"urlFilter": f"||{host}^", "resourceTypes": ["main_frame"]},
        })
    return compile_rules(rules)


# --- A5 page note --------------------------------------------------------
@dataclass
class PageNote:
    url: str
    title: str
    text: str
    source: str = "browse"
    tags: List[str] = field(default_factory=list)


def note_from_page(url: str, title: str, raw_html: str,
                   source: str = "browse") -> PageNote:
    """Capture a page as a clean-text note ready for storage/summarization."""
    return PageNote(url=url, title=title,
                    text=html_to_clean_markdown(raw_html), source=source)


# --- A6 screenshot -------------------------------------------------------
async def capture_screenshot(session, fmt: str = "png") -> bytes:
    """Capture the current page as screenshot bytes via CDP."""
    res = await session._call("Page.captureScreenshot", {"format": fmt})
    b64 = res["result"]["data"]
    return base64.b64decode(b64)


# --- A7 translation (global product feature) ----------------------------
TranslatorBackend = Callable[[str, str], str]


def make_translator(backend: TranslatorBackend, target_lang: str,
                    fail_safe: bool = True) -> Callable[[str], str]:
    """Wrap a Nous-backed translation backend into a cached, safe callable.

    ``backend(text, target_lang) -> str``. Repeated text is served from cache
    (cost control at global scale). When ``fail_safe`` is true a backend
    failure returns the original text instead of raising, so translation is
    never a hard dependency of the fetch path.
    """
    cache: dict = {}

    def translate(text: str) -> str:
        if not text:
            return text
        if text in cache:
            return cache[text]
        try:
            out = backend(text, target_lang)
        except Exception:
            if fail_safe:
                return text
            raise
        cache[text] = out
        return out

    return translate


def translate_lines(backend: TranslatorBackend, lines: Iterable[str],
                    target_lang: str, fail_safe: bool = True) -> List[str]:
    """Translate an extracted-document's lines, preserving blank lines.

    Each non-blank line is translated through the cached translator so
    markdown structure (headings, lists) survives the round trip.
    """
    translate = make_translator(backend, target_lang, fail_safe=fail_safe)
    out: List[str] = []
    for line in lines:
        if not line.strip():
            out.append("")
        else:
            out.append(translate(line))
    return out
