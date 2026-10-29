"""Extension NTP locale-variant regression: every language link must resolve.

Bug: write_extension() wrote only pergel_ntp.html (lang="en"), so the scriptless
lang_links() footer pointed at pergel_ntp_<code>.html files that didn't exist
(ERR_FILE_NOT_FOUND), and new tabs showed English instead of the system language.
"""
import os
import tempfile
import unittest

from src.brand import i18n, render


class WriteExtensionLocaleVariants(unittest.TestCase):
    def test_writes_all_locale_variants(self):
        with tempfile.TemporaryDirectory() as dest:
            render.write_extension(dest)
            for code in i18n.LOCALES:
                path = os.path.join(dest, f"pergel_ntp_{code}.html")
                self.assertTrue(os.path.isfile(path),
                                f"missing locale variant: pergel_ntp_{code}.html")

    def test_default_ntp_uses_system_language(self):
        old = os.environ.get("LANG")
        os.environ["LANG"] = "tr_TR.UTF-8"
        try:
            with tempfile.TemporaryDirectory() as dest:
                render.write_extension(dest)
                with open(os.path.join(dest, "pergel_ntp.html")) as f:
                    html = f.read()
                self.assertIn('lang="tr"', html)
                self.assertIn("arayın veya URL yazın", html)  # tr search_ph
        finally:
            if old is None:
                os.environ.pop("LANG", None)
            else:
                os.environ["LANG"] = old

    def test_lang_links_all_targets_exist(self):
        with tempfile.TemporaryDirectory() as dest:
            render.write_extension(dest)
            links = i18n.lang_links("en")
            import re
            for href in re.findall(r'href="([^"]+)"', links):
                self.assertTrue(os.path.isfile(os.path.join(dest, href)),
                                f"lang link target missing: {href}")


if __name__ == "__main__":
    unittest.main()
