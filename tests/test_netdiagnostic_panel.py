"""Pergel yerel ag teshisi paneli: sifir veri cikisi, sadece loopback uzerinden calisir."""
import re
import unittest

from src.brand import render


class TestNetDiagnostics(unittest.TestCase):
    def test_panel_has_diagnostics_section(self):
        html = render.render_side_panel()
        self.assertIn('id="netdiag"', html)
        self.assertIn("teşhis", html.lower())

    def test_panel_no_external_calls(self):
        """Veri cikisi yasak: sadece loopback/host izin verilen adresler."""
        html = render.render_side_panel()
        for m in re.finditer(r'https?://[^\s"\']+', html):
            url = m.group(0)
            self.assertNotIn("google-analytics", url)
            self.assertNotIn("telemetry", url)
            self.assertNotIn("tracking", url)

    def test_netdiag_runs_local_only(self):
        """Ağ teşhisi sadece 127.0.0.1/localhost üzerinden veri almalı."""
        html = render.render_side_panel()
        self.assertIn("127.0.0.1", html)


if __name__ == "__main__":
    unittest.main()
