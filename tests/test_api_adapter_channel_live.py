import json
import os
import unittest
import urllib.error
import urllib.request

SERVER = "http://127.0.0.1:8090"


def _key():
    for line in open(os.path.expanduser("~/.config/oracle-router/browse_api.env")):
        if line.startswith("BROWSE_API_KEY="):
            return line.strip().split("=", 1)[1]
    return ""


def _browse(url):
    req = urllib.request.Request(
        SERVER + "/v1/jobs/browse",
        data=json.dumps({"url": url}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + _key()},
    )
    return json.load(urllib.request.urlopen(req, timeout=40))


class TestAdapterFieldInResponse(unittest.TestCase):
    """Live: /v1/jobs/browse must expose which channel (adapter vs engine) answered."""

    def test_adapter_result_exposes_adapter_name_and_metadata(self):
        d = _browse("https://www.npmjs.com/package/left-pad")
        self.assertEqual(d.get("engine"), "platform-adapter:npm")
        self.assertEqual(d.get("adapter"), "npm")  # explicit channel field
        self.assertIsInstance(d.get("adapter_metadata"), dict)
        self.assertEqual(d["adapter_metadata"].get("package"), "left-pad")

    def test_engine_fallback_has_no_adapter(self):
        d = _browse("https://example.com/")
        self.assertIsNone(d.get("adapter"))
        self.assertNotIn("platform-adapter", str(d.get("engine")))


if __name__ == "__main__":
    unittest.main()
