import json
import os
import tempfile
import unittest
import urllib.request
from src.api.server import BrowserFarmSaaSServer


class TestE2ESaaSProduct(unittest.TestCase):
    def test_full_saas_api_browse_fanout_router_and_health_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            webhooks_received = []

            def mock_driver(engine: str, url: str, session_name: str) -> str:
                return f"<html><body><h1>Scraped {url}</h1><p>Engine: {engine}</p></body></html>"

            def mock_webhook_sender(url: str, body: bytes, headers: dict) -> int:
                webhooks_received.append(
                    (url, json.loads(body.decode("utf-8")), headers)
                )
                return 200

            server = BrowserFarmSaaSServer(
                host="127.0.0.1",
                port=0,
                db_dir=tmp,
                driver_fn=mock_driver,
                webhook_sender_fn=mock_webhook_sender,
            )
            server.start_background()
            try:
                base_url = f"http://127.0.0.1:{server.port}"

                # 1. Health Endpoint
                with urllib.request.urlopen(f"{base_url}/v1/health", timeout=5) as resp:
                    health = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")

                # 2. Submit Browse Job + Webhook Delivery
                req_data = json.dumps(
                    {
                        "url": "https://target.example.com/pricing",
                        "goal": "Get pricing",
                        "needs_vision": False,
                        "js_complexity": "low",
                        "webhook_url": "https://customer.example.com/callback",
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"{base_url}/v1/jobs/browse",
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    job_res = json.loads(resp.read().decode("utf-8"))

                self.assertEqual(job_res["status"], "completed")
                self.assertIn(
                    "# Scraped https://target.example.com/pricing",
                    job_res["extracted_markdown"],
                )
                self.assertEqual(len(webhooks_received), 1)
                self.assertIn("X-BrowserFarm-Signature", webhooks_received[0][2])

                # 3. Fetch Job by ID
                job_id = job_res["job_id"]
                with urllib.request.urlopen(
                    f"{base_url}/v1/jobs/{job_id}", timeout=5
                ) as resp:
                    fetched = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(fetched["job_id"], job_id)
                self.assertEqual(fetched["status"], "completed")
            finally:
                server.shutdown()


if __name__ == "__main__":
    unittest.main()
