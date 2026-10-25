"""A2-A7 native capability layer — thin wrappers over the existing engine.

Every capability here rides a layer we already built (cosmetic/DNR/injection/
clean-markdown/CDP); none adds a new engine. Translation (A7) is a global
product feature: pluggable Nous-backed translator, cached, cost-aware.

RED first (module absent), then GREEN.
"""
import asyncio
import unittest

from src.browser_engine.adblock_session import build_injection
from src.browser_engine.cdp_adblock_driver import AdblockBrowserSession
from src.browser_engine.native_capabilities import (
    DARK_MODE_CSS,
    PageNote,
    build_focus_engine,
    capture_screenshot,
    make_translator,
    note_from_page,
    reader_mode,
    translate_lines,
)

CHUNK = "----8<----"

SAMPLE_HTML = (
    "<html><head><title>T</title></head><body>"
    "<nav>menu junk</nav>"
    "<article><h1>Headline</h1><p>Body sentence one. Body sentence two.</p></article>"
    "</body></html>"
)


class ReaderModeTests(unittest.TestCase):
    def test_reader_mode_returns_clean_markdown(self):
        md = reader_mode(SAMPLE_HTML)
        self.assertIn("Headline", md)
        self.assertNotIn("menu junk", md)

    def test_reader_mode_empty_on_blank(self):
        self.assertEqual(reader_mode(""), "")


class DarkModeTests(unittest.TestCase):
    def test_dark_mode_css_targets_page_background(self):
        self.assertIn("background", DARK_MODE_CSS)
        self.assertIn("color", DARK_MODE_CSS)

    def test_dark_mode_appends_to_injection(self):
        bundle_css = ""
        injected = build_injection.__globals__["_css_inject_iife"]
        combined = (bundle_css + "\n" + DARK_MODE_CSS).strip()
        js = injected(combined)
        self.assertIn("createTextNode" if False else "textContent", js)
        self.assertIn("invert" if "invert" in DARK_MODE_CSS else "background", js)


class FocusBlockTests(unittest.TestCase):
    def test_focus_engine_blocks_listed_hosts(self):
        eng = build_focus_engine(["news.example", "videos.example"])
        decision = eng.check("https://news.example/story", "document")
        self.assertIn(decision.action, ("block", "redirect"))

    def test_focus_engine_allows_other_hosts(self):
        eng = build_focus_engine(["news.example"])
        decision = eng.check("https://work.example/", "document")
        self.assertEqual(decision.action, "allow")

    def test_focus_engine_empty_list_allows_all(self):
        eng = build_focus_engine([])
        self.assertEqual(eng.check("https://anything.example/", "document").action, "allow")


class PageNoteTests(unittest.TestCase):
    def test_note_from_page_bundles_clean_text(self):
        note = note_from_page(
            url="https://x.example/a", title="T", raw_html=SAMPLE_HTML,
            source="browse",
        )
        self.assertIsInstance(note, PageNote)
        self.assertEqual(note.url, "https://x.example/a")
        self.assertIn("Headline", note.text)
        self.assertNotIn("menu junk", note.text)

    def test_note_record_fields(self):
        note = note_from_page("https://x.example/", "T", "<p>hi</p>", source="fetch")
        self.assertEqual(note.source, "fetch")
        self.assertTrue(note.text)


class TranslateTests(unittest.TestCase):
    def test_translator_passes_target_language(self):
        seen = {}

        def backend(text, lang):
            seen["lang"] = lang
            return text.upper()

        tr = make_translator(backend, target_lang="tr")
        self.assertEqual(tr("hello"), "HELLO")
        self.assertEqual(seen["lang"], "tr")

    def test_translator_caches_repeats(self):
        calls = []

        def backend(text, lang):
            calls.append(text)
            return text

        tr = make_translator(backend, target_lang="en")
        tr("same")
        tr("same")
        self.assertEqual(len(calls), 1)

    def test_translate_lines_preserves_structure(self):
        def backend(text, lang):
            return "[T] " + text

        out = translate_lines(backend, ["# Title", "", "body"], target_lang="en")
        self.assertEqual(out[0], "[T] # Title")
        self.assertEqual(out[1], "")  # blank lines pass through

    def test_backend_failure_is_fail_safe(self):
        def backend(text, lang):
            raise RuntimeError("model down")

        tr = make_translator(backend, target_lang="en", fail_safe=True)
        self.assertEqual(tr("hello"), "hello")  # original text, no crash


def _has_chromium():
    try:
        from src.browser_engine.cdp_adblock_driver import _chromium
        return _chromium() is not None
    except Exception:
        return False


@unittest.skipUnless(_has_chromium(), "chromium not present for live CDP")
class ScreenshotTests(unittest.TestCase):
    def test_capture_screenshot_returns_png_bytes(self):
        from src.browser_engine.adblock_session import AdblockBundle

        async def run():
            async with AdblockBrowserSession(AdblockBundle()) as s:
                await s.fetch("data:text/html,<title>S</title><p>hi</p>")
                return await capture_screenshot(s)

        data = asyncio.run(run())
        self.assertTrue(data.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
