import io
import json
import struct
import unittest
import zipfile

from src.rea.audit import audit_manifest
from src.rea.crx import extract_crx
from src.rea.endpoints import extract_endpoints


def make_crx3(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    header = b"\x0a\x00"  # tiny protobuf-ish header payload; content is irrelevant to extraction
    return b"Cr24" + struct.pack("<II", 3, len(header)) + header + buf.getvalue()


class CrxTests(unittest.TestCase):
    def test_extract_crx3_recovers_manifest(self):
        crx = make_crx3({"manifest.json": json.dumps({"name": "x", "version": "1"}), "a.js": "1"})
        files = extract_crx(crx)
        self.assertEqual(json.loads(files["manifest.json"])["name"], "x")
        self.assertIn("a.js", files)

    def test_plain_zip_is_accepted(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("manifest.json", "{}")
        self.assertIn("manifest.json", extract_crx(buf.getvalue()))

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            extract_crx(b"not an extension")

    def test_zip_slip_paths_are_rejected(self):
        crx = make_crx3({"../evil.js": "x", "ok.js": "y"})
        files = extract_crx(crx)
        self.assertNotIn("../evil.js", files)
        self.assertIn("ok.js", files)


class EndpointTests(unittest.TestCase):
    def test_extracts_and_dedupes_urls_and_drops_schema_noise(self):
        text = ("fetch('https://api.example.com/v1/x'); 'https://api.example.com/v1/x' "
                "xmlns='http://www.w3.org/2000/svg' http://json-schema.org/draft-07/schema "
                "wss://stream.example.com/ws \"https://cdn.example.com/a.js\"")
        urls = extract_endpoints(text)
        self.assertEqual(urls.count("https://api.example.com/v1/x"), 1)
        self.assertIn("wss://stream.example.com/ws", urls)
        self.assertFalse(any("w3.org" in u or "json-schema.org" in u for u in urls))

    def test_strips_trailing_punctuation(self):
        self.assertEqual(extract_endpoints("see https://a.example.com/x)."), ["https://a.example.com/x"])


class AuditTests(unittest.TestCase):
    def test_flags_broad_host_permissions_and_dangerous_apis(self):
        m = {"manifest_version": 3, "permissions": ["debugger", "nativeMessaging", "storage"],
             "host_permissions": ["<all_urls>"],
             "externally_connectable": {"matches": ["*://*/*"]},
             "content_security_policy": {"extension_pages": "script-src 'self' 'unsafe-eval'"}}
        ids = {f["id"] for f in audit_manifest(m)}
        self.assertEqual(ids, {"broad-host", "debugger", "native-messaging", "ext-connectable-wildcard", "unsafe-eval"})

    def test_minimal_manifest_is_clean(self):
        m = {"manifest_version": 3, "permissions": ["sidePanel", "storage"],
             "host_permissions": ["http://127.0.0.1:8090/*"]}
        self.assertEqual(audit_manifest(m), [])

    def test_mv2_is_flagged(self):
        self.assertIn("mv2", {f["id"] for f in audit_manifest({"manifest_version": 2})})


class ComponentManifestTests(unittest.TestCase):
    def test_mv2_not_flagged_for_chromium_component_manifests(self):
        from src.rea.audit import is_component_manifest
        widevine = {"manifest_version": 2, "name": "WidevineCdm", "version": "4.10.1", "x-cdm-codecs": "vp8"}
        mei = {"manifest_version": 2, "name": "MEI Preload", "version": "1.0.7.1"}
        hyphen = {"manifest_version": 2, "name": "hyphens-data", "version": "1.0.0.0"}
        for m in (widevine, mei, hyphen):
            self.assertTrue(is_component_manifest(m), m["name"])
            self.assertEqual([f["id"] for f in audit_manifest(m)], [])

    def test_real_mv2_extension_still_flagged(self):
        ext = {"manifest_version": 2, "name": "Some Extension", "version": "1", "permissions": ["tabs"],
               "background": {"scripts": ["bg.js"]}}
        self.assertIn("mv2", {f["id"] for f in audit_manifest(ext)})


class NetProbeTests(unittest.TestCase):
    HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"

    def test_parses_established_ipv4_and_skips_loopback_and_listen(self):
        from src.rea.netprobe import parse_proc_net_tcp
        text = (self.HEADER +
                "   0: 0100007F:2382 0100007F:C350 01 00000000:00000000 00:00000000 00000000  1000 0 1\n"   # loopback
                "   1: 0F01A8C0:C000 22D8B8AC:01BB 01 00000000:00000000 00:00000000 00000000  1000 0 2\n"   # 172.184.216.34:443
                "   2: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000 0 3\n")  # LISTEN
        self.assertEqual(parse_proc_net_tcp(text), {"172.184.216.34:443"})

    def test_parses_ipv6(self):
        from src.rea.netprobe import parse_proc_net_tcp
        text = (self.HEADER +
                "   0: 00000000000000000000000001000000:9C40 2A0014501001000000000000 00000000:01BB 01 0:0 0:0 0 1000 0 9\n")
        # malformed row (missing field): must be ignored, not crash
        self.assertEqual(parse_proc_net_tcp(text), set())

    def test_syn_sent_counts_as_attempted_contact(self):
        from src.rea.netprobe import parse_proc_net_tcp
        text = self.HEADER + "   0: 0F01A8C0:C000 22D8B8AC:01BB 02 00000000:00000000 00:00000000 00000000  1000 0 2\n"
        self.assertEqual(parse_proc_net_tcp(text), {"172.184.216.34:443"})
