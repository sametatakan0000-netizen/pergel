"""RED: browser migration — bring data IN from other browsers, export OUT.

The #1 barrier to switching browsers is data transfer. Pergel must make it
one command (and first-run automatic): bookmarks, history and passwords
from Chrome/Chromium/Edge/Brave/Vivaldi/Firefox, plus universal
Netscape HTML / JSON / CSV interchange.
"""
import json
import os
import sqlite3
import tempfile
import unittest

from src.brand.migrate import (
    detect_sources,
    export_csv,
    export_netscape_html,
    export_passwords_csv,
    import_chromium_bookmarks,
    import_chromium_history,
    import_csv,
    import_firefox_bookmarks_json,
    import_netscape_html,
    import_passwords_csv,
    migrate,
    write_chromium_bookmarks,
    write_chromium_history,
    write_chromium_passwords,
    read_chromium_passwords,
)

CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def make_chrome_profile(root, with_data=True):
    d = os.path.join(root, "Default")
    os.makedirs(d, exist_ok=True)
    if with_data:
        bm = {
            "roots": {
                "bookmark_bar": {"type": "folder", "name": "Bookmarks bar",
                                 "children": [
                    {"type": "url", "name": "Örnek",
                     "url": "https://ornek.test/"},
                    {"type": "folder", "name": "Klasör", "children": [
                        {"type": "url", "name": "Alt",
                         "url": "https://alt.test/"}]}]},
                "other": {"type": "folder", "name": "Other bookmarks",
                          "children": []},
                "synced": {"type": "folder", "name": "Mobile bookmarks",
                           "children": []},
            },
            "checksum": "deadbeef",
            "version": 1,
        }
        with open(os.path.join(d, "Bookmarks"), "w") as f:
            json.dump(bm, f, ensure_ascii=False)
        con = sqlite3.connect(os.path.join(d, "History"))
        con.executescript("""
            CREATE TABLE urls (id INTEGER PRIMARY KEY, url LONGVARCHAR,
                title LONGVARCHAR, visit_count INTEGER DEFAULT 0,
                typed_count INTEGER DEFAULT 0, last_visit_time INTEGER,
                hidden INTEGER DEFAULT 0);
            CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER,
                visit_time INTEGER, from_visit INTEGER,
                transition INTEGER DEFAULT 805306376,
                segment_id INTEGER, visit_duration INTEGER DEFAULT 0,
                incremented_omnibox_typed_score INTEGER DEFAULT 0);
        """)
        ts = int((1700000000 + CHROME_EPOCH_OFFSET) * 1_000_000)
        con.execute("INSERT INTO urls (url, title, last_visit_time) VALUES (?,?,?)",
                    ("https://ornek.test/", "Örnek", ts))
        con.commit(); con.close()
    return d


class TestChromiumImport(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.default = make_chrome_profile(self.root)

    def test_bookmarks_folders_preserved(self):
        rows = import_chromium_bookmarks(self.default)
        urls = {r["url"]: r for r in rows}
        self.assertIn("https://ornek.test/", urls)
        self.assertIn("https://alt.test/", urls)
        self.assertEqual(urls["https://alt.test/"]["folder"], "Klasör")

    def test_history_converts_chrome_epoch(self):
        rows = import_chromium_history(self.default)
        self.assertEqual(rows[0]["url"], "https://ornek.test/")
        self.assertEqual(rows[0]["ts"], 1700000000)  # unix seconds


class TestFirefoxImport(unittest.TestCase):
    def test_firefox_json_export(self):
        data = {"children": [
            {"type": "text/x-moz-place", "title": "FF Sayfa",
             "uri": "https://ff.test/"},
            {"type": "text/x-moz-place-container", "title": "FF Klasör",
             "children": [{"type": "text/x-moz-place", "title": "Alt FF",
                           "uri": "https://ff-alt.test/"}]},
        ], "title": "", "type": "text/x-moz-place-container", "root": "placesRoot"}
        p = os.path.join(tempfile.mkdtemp(), "ff.json")
        with open(p, "w") as f:
            json.dump(data, f)
        rows = import_firefox_bookmarks_json(p)
        urls = {r["url"]: r for r in rows}
        self.assertEqual(urls["https://ff-alt.test/"]["folder"], "FF Klasör")
        self.assertIn("https://ff.test/", urls)


class TestUniversalFormats(unittest.TestCase):
    def test_netscape_html_round_trip(self):
        rows = [{"title": "Bir", "url": "https://bir.test/", "folder": "F"}]
        p = os.path.join(tempfile.mkdtemp(), "bm.html")
        export_netscape_html(rows, p)
        back = import_netscape_html(p)
        self.assertEqual(back[0]["url"], "https://bir.test/")
        self.assertEqual(back[0]["title"], "Bir")

    def test_csv_round_trip(self):
        rows = [{"title": "İki", "url": "https://iki.test/", "folder": ""}]
        p = os.path.join(tempfile.mkdtemp(), "bm.csv")
        export_csv(rows, p)
        back = import_csv(p)
        self.assertEqual(back[0]["url"], "https://iki.test/")

    def test_password_csv_round_trip(self):
        rows = [{"origin": "https://giris.test/", "username": "kullanici",
                 "password": "sifre-gizli-123"}]
        p = os.path.join(tempfile.mkdtemp(), "pw.csv")
        export_passwords_csv(rows, p)
        back = import_passwords_csv(p)
        self.assertEqual(back[0]["password"], "sifre-gizli-123")


class TestChromiumWrite(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.default = make_chrome_profile(self.root)

    def test_write_bookmarks_merges_without_duplication(self):
        rows = [{"title": "Yeni", "url": "https://yeni.test/", "folder": ""}]
        write_chromium_bookmarks(rows, self.default, source="test")
        write_chromium_bookmarks(rows, self.default, source="test")
        back = import_chromium_bookmarks(self.default)
        self.assertEqual([r for r in back if r["url"] == "https://yeni.test/"],
                         [r for r in back if r["url"] == "https://yeni.test/"][:1])
        self.assertEqual(len([r for r in back if r["url"] == "https://yeni.test/"]), 1)

    def test_write_history_readable_back(self):
        rows = [{"url": "https://tasindi.test/", "title": "Taşındı", "ts": 1700000123}]
        write_chromium_history(rows, self.root + "/p2")
        back = import_chromium_history(self.root + "/p2")
        self.assertEqual(back[0]["url"], "https://tasindi.test/")
        self.assertEqual(back[0]["ts"], 1700000123)

    def test_write_passwords_self_consistent(self):
        rows = [{"origin": "https://giris.test/", "username": "ada",
                 "password": "gizli-sifre-999"}]
        write_chromium_passwords(rows, self.default)
        back = read_chromium_passwords(self.default)
        self.assertEqual(back[0]["password"], "gizli-sifre-999")
        self.assertEqual(back[0]["username"], "ada")


class TestMigrate(unittest.TestCase):
    def test_detect_sources_finds_chromium_family(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".config"), exist_ok=True)
        make_chrome_profile(os.path.join(root, ".config", "google-chrome"))
        found = detect_sources(home=root)
        self.assertTrue(any(b == "chrome" for b, _ in found["chromium"]))

    def test_migrate_report_has_counts_but_no_secrets(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".config"), exist_ok=True)
        make_chrome_profile(os.path.join(root, ".config", "google-chrome"))
        out = tempfile.mkdtemp()
        report = migrate(out, home=root, passwords_csv=None)
        blob = json.dumps(report, ensure_ascii=False)
        self.assertIn("bookmarks", report)
        self.assertNotIn("sifre", blob)  # no secret material in any report
        self.assertGreaterEqual(report["bookmarks"], 2)

    def test_migrate_accepts_passwords_csv(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".config"), exist_ok=True)
        make_chrome_profile(os.path.join(root, ".config", "google-chrome"))
        csvp = os.path.join(root, "pw.csv")
        export_passwords_csv([{"origin": "https://x.test/", "username": "u",
                               "password": "cok-gizli"}], csvp)
        report = migrate(root + "/out", home=root, passwords_csv=csvp)
        self.assertEqual(report["passwords"], 1)
        self.assertNotIn("cok-gizli", json.dumps(report))


class TestPergelCliWiring(unittest.TestCase):
    def test_migrate_flag_short_circuits_and_reports_counts(self):
        from src.brand import pergel_app
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".config"), exist_ok=True)
        make_chrome_profile(os.path.join(root, ".config", "google-chrome"))
        prof = tempfile.mkdtemp()
        rc = pergel_app.main(["--migrate", "--profile-dir", prof, "--home", root])
        self.assertEqual(rc, 0)

    def test_auto_migration_runs_once(self):
        from src.brand import pergel_app
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".config"), exist_ok=True)
        make_chrome_profile(os.path.join(root, ".config", "google-chrome"))
        prof = tempfile.mkdtemp()
        first = pergel_app.maybe_auto_migrate(prof, home=root)
        self.assertGreaterEqual(first.get("bookmarks", 0), 2)
        second = pergel_app.maybe_auto_migrate(prof, home=root)
        self.assertEqual(second, {})  # marker: no re-import, no dupes


if __name__ == "__main__":
    unittest.main()
