"""Regex extraction fallback: structured content must survive as Markdown.

Production reality (verified 2026-11-03): the installed .deb launcher runs
system python3, which has no trafilatura (and apt has no python3-trafilatura),
so the dependency-free fallback IS the production extractor for every fetch.
Since 2026-11-04 that fallback is `_parser_markdown` (stdlib HTMLParser, see
test_parser_markdown.py for its contract); `_regex_markdown` below is the
documented last-resort layer and still pins the original table/heading fixes.
Two defects made it corrupt structured content:

1. Table cells concatenated into mush (`<td>url</td><td>required</td>` ->
   "urlrequired") because only ``</p>|</div>|<br>`` produced line breaks and
   generic tag-stripping glued adjacent cell text together.
2. `<h4>`-`<h6>` headings vanished as plain text (only h1-h3 were converted).

These tests pin the contract: rows are lines, cells are pipe-separated,
and all six heading levels keep their Markdown prefix.
"""
import unittest

from src.browser_engine.worker import _regex_markdown, html_to_clean_markdown

TABLE_PAGE = (
    "<html><body><h1>urllib.request</h1>"
    "<p>Module for opening URLs.</p>"
    "<table><tr><th>Parameter</th><th>Default</th><th>Doc</th></tr>"
    "<tr><td>url</td><td>required</td><td>target address</td></tr>"
    "<tr><td>data</td><td>None</td><td>payload</td></tr></table>"
    "</body></html>"
)


class TableExtraction(unittest.TestCase):
    def setUp(self):
        self.md = _regex_markdown(TABLE_PAGE)

    def test_cells_are_pipe_separated_not_concatenated(self):
        normalized = " ".join(self.md.split())
        self.assertNotIn("urlrequired", normalized, self.md)
        self.assertNotIn("ParameterDefault", normalized, self.md)
        self.assertIn("url | required | target address", normalized, self.md)
        self.assertIn("Parameter | Default | Doc", normalized, self.md)

    def test_table_rows_become_separate_lines(self):
        row_lines = [ln for ln in self.md.splitlines() if " | " in ln]
        self.assertGreaterEqual(len(row_lines), 3, self.md)

    def test_cell_attributes_do_not_break_separation(self):
        md = _regex_markdown(
            '<table><tr><td class="c">a</td><td align="right">b</td></tr></table>'
        )
        self.assertIn("a | b", " ".join(md.split()), md)


class HeadingLevels(unittest.TestCase):
    def test_h4_to_h6_keep_markdown_prefix(self):
        md = _regex_markdown("<h4>Four</h4><h5>Five</h5><h6>Six</h6>")
        self.assertIn("#### Four", md, md)
        self.assertIn("##### Five", md, md)
        self.assertIn("###### Six", md, md)

    def test_h1_to_h3_unchanged(self):
        md = _regex_markdown("<h1>One</h1><h2>Two</h2><h3>Three</h3>")
        self.assertIn("# One", md, md)
        self.assertIn("## Two", md, md)
        self.assertIn("### Three", md, md)


class EndToEndNoMush(unittest.TestCase):
    """Through the public extractor: no trafilatura-vs-regex path may glue cells."""

    def test_public_extractor_separates_table_cells(self):
        out = html_to_clean_markdown(TABLE_PAGE)
        self.assertNotIn("urlrequired", out.replace(" ", ""), out)
        self.assertIn("required", out, out)


if __name__ == "__main__":
    unittest.main()
