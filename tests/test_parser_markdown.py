"""Production extraction fallback: real parser defects the regex path still has.

Production reality (verified 2026-11-03): the installed .deb runs system python3
without trafilatura/bs4, so the no-dependency fallback IS the production
extractor. The regex fallback still silently corrupts content:

1. Literal angle brackets in visible text (`5 < 10 and 10 > 5`) match the
   generic `<[^>]+>` tag-strip and get eaten -> data loss in code/prose/math.
2. HTML comments leak: `<!-- note: 5 > 3 -->` is cut at the first `>`, so
   `3 -->` lands in the extracted text.
3. Unquoted `href=/path` attributes are not recognized as links -> URL lost.
4. `<dt>`/`</dd>` produce no line break -> `alpha` + `first item` glue together.

These tests pin the contract through the PUBLIC extractor (the path every
fetch actually takes without trafilatura).
"""
import unittest

from src.browser_engine.worker import html_to_clean_markdown


class LiteralAngleBrackets(unittest.TestCase):
    def test_comparison_text_survives(self):
        out = html_to_clean_markdown("<p>Bounds: 5 < 10 and 10 > 5 stay intact</p>")
        self.assertIn("5 < 10 and 10 > 5 stay intact", " ".join(out.split()), out)


class CommentHygiene(unittest.TestCase):
    def test_comment_content_never_leaks(self):
        out = html_to_clean_markdown(
            "<!-- internal note: 5 > 3 is true --><p>Visible body</p>"
        )
        self.assertIn("Visible body", out, out)
        self.assertNotIn("internal note", out, out)
        self.assertNotIn("-->", out, out)


class UnquotedHref(unittest.TestCase):
    def test_unquoted_href_becomes_markdown_link(self):
        out = html_to_clean_markdown('<a href=/docs/intro>Intro</a>')
        self.assertIn("[Intro](/docs/intro)", " ".join(out.split()), out)


class DefinitionListSeparation(unittest.TestCase):
    def test_dt_dd_do_not_glue(self):
        out = html_to_clean_markdown("<dl><dt>alpha</dt><dd>first item</dd></dl>")
        self.assertNotIn("alphafirst", out.replace(" ", ""), out)
        self.assertIn("alpha", out, out)
        self.assertIn("first item", out, out)


class StructureStillKept(unittest.TestCase):
    """Regression guard: the new fallback must keep yesterday's contract too."""

    def test_table_cells_and_headings_survive_public_path(self):
        page = (
            "<html><body><h2>API</h2>"
            "<table><tr><td>url</td><td>required</td></tr></table></body></html>"
        )
        out = html_to_clean_markdown(page)
        normalized = " ".join(out.split())
        self.assertIn("## API", normalized, out)
        self.assertIn("url | required", normalized, out)


if __name__ == "__main__":
    unittest.main()
