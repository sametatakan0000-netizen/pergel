"""Tests for Replika Rebuild: Session Manager, Tab Hibernator, Privacy Filters."""
import json
import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brand.session_manager import SessionManager
from brand.tab_hibernator import TabHibernator


class TestSessionManager:
    def test_save_and_load(self, tmp_path):
        sm = SessionManager(str(tmp_path))
        tabs = [
            {"url": "https://example.com", "title": "Example", "pinned": False, "index": 0},
            {"url": "https://github.com", "title": "GitHub", "pinned": True, "index": 1},
        ]
        assert sm.save_session(tabs) is True
        state = sm.load_session()
        assert state is not None
        assert len(state["tabs"]) == 2
        assert state["tabs"][0]["url"] == "https://example.com"

    def test_load_empty(self, tmp_path):
        sm = SessionManager(str(tmp_path))
        assert sm.load_session() is None

    def test_crash_recovery(self, tmp_path):
        sm = SessionManager(str(tmp_path))
        assert sm.has_crashed_session() is False
        sm.save_session([{"url": "https://example.com", "title": "T", "pinned": False, "index": 0}])
        assert sm.has_crashed_session() is True

    def test_clear_session(self, tmp_path):
        sm = SessionManager(str(tmp_path))
        sm.save_session([{"url": "https://example.com", "title": "T", "pinned": False, "index": 0}])
        sm.clear_session()
        assert sm.load_session() is None

    def test_get_restore_urls(self, tmp_path):
        sm = SessionManager(str(tmp_path))
        sm.save_session([
            {"url": "https://a.com", "title": "A", "pinned": False, "index": 0},
            {"url": "https://b.com", "title": "B", "pinned": False, "index": 1},
        ])
        urls = sm.get_restore_urls()
        assert urls == ["https://a.com", "https://b.com"]

    def test_backup_rotation(self, tmp_path):
        sm = SessionManager(str(tmp_path))
        sm.save_session([{"url": "https://old.com", "title": "Old", "pinned": False, "index": 0}])
        sm.save_session([{"url": "https://new.com", "title": "New", "pinned": False, "index": 0}])
        # Primary should have new, backup should have old
        primary = json.loads(sm.session_file.read_text(encoding="utf-8"))
        assert primary["tabs"][0]["url"] == "https://new.com"

    def test_corrupt_file_recovery(self, tmp_path):
        sm = SessionManager(str(tmp_path))
        sm.session_file.write_text("not json", encoding="utf-8")
        assert sm.load_session() is None


class TestTabHibernator:
    def test_track_and_idle(self):
        th = TabHibernator(idle_timeout=1)
        th.track_activity("tab1")
        assert th.should_hibernate("tab1") is False
        time.sleep(1.1)
        assert th.should_hibernate("tab1") is True

    def test_hibernated_not_re_hibernated(self):
        th = TabHibernator(idle_timeout=1)
        th.track_activity("tab1")
        th.mark_hibernated("tab1")
        assert th.should_hibernate("tab1") is False

    def test_wake_from_hibernation(self):
        th = TabHibernator(idle_timeout=1)
        th.track_activity("tab1")
        th.mark_hibernated("tab1")
        th.mark_active("tab1")
        assert th.should_hibernate("tab1") is False
        assert "tab1" not in th.hibernated_tabs

    def test_idle_tabs_list(self):
        th = TabHibernator(idle_timeout=1)
        th.track_activity("tab1")
        th.track_activity("tab2")
        time.sleep(1.1)
        idle = th.get_idle_tabs()
        assert "tab1" in idle
        assert "tab2" in idle

    def test_memory_stats(self):
        th = TabHibernator(idle_timeout=300)
        th.track_activity("tab1")
        th.mark_hibernated("tab1")
        stats = th.get_memory_stats()
        assert stats["total_tracked"] == 1
        assert stats["hibernated"] == 1

    def test_unknown_tab_not_hibernated(self):
        th = TabHibernator(idle_timeout=1)
        assert th.should_hibernate("nonexistent") is False


class TestPrivacyFilters:
    def test_filter_file_exists(self):
        from pathlib import Path
        f = Path(__file__).parent.parent / "src" / "brand" / "filters_privacy.txt"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "google-analytics.com" in content
        assert "doubleclick.net" in content

    def test_filter_has_major_trackers(self):
        from pathlib import Path
        f = Path(__file__).parent.parent / "src" / "brand" / "filters_privacy.txt"
        content = f.read_text(encoding="utf-8")
        # Key tracker domains
        for domain in ["facebook.net", "hotjar.com", "criteo.com", "taboola.com"]:
            assert domain in content, f"Missing tracker: {domain}"
