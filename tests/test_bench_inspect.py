import unittest

from src.bench.inspect import format_card, pick_stack

INFO = {"version": "156.0.8078.47", "install_size_kb": 500000, "startup_ms": 238.2,
        "idle_pss_kib": 87000, "pids": 3, "protocols": ["CDP"], "listening_ports": ["9222"],
        "outbound_hosts": ["example.com"]}


class InspectTests(unittest.TestCase):
    def test_card_has_required_fields(self):
        card = format_card("chrome-cft", "chromium", INFO, sources=["https://x"])
        for field in ("version", "install size", "startup", "idle PSS", "processes", "automation", "Sources"):
            self.assertIn(field.lower(), card.lower())

    def test_desk_research_card_is_labeled(self):
        card = format_card("comet", "chromium", {"version": "unknown"}, sources=["https://y"],
                           desk_research=True)
        self.assertIn("desk research — not run on this host", card)

    def test_pick_stack_sorts_family_and_kind(self):
        rows = [{"id": "b", "kind": "chromium", "family": "chromium"},
                {"id": "a", "kind": "lightpanda", "family": "lightpanda"},
                {"id": "c", "kind": "chromium", "family": "gecko"}]
        self.assertEqual([r["id"] for r in pick_stack(rows)], ["a", "b", "c"])

    def test_sources_required(self):
        with self.assertRaises(ValueError):
            format_card("x", "y", INFO, sources=[])
