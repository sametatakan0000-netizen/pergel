import unittest
from src.infra.webhook_dispatcher import WebhookDispatcher, compute_hmac_signature


class TestWebhookDispatcher(unittest.TestCase):
    def test_webhook_dispatcher_signs_payload_and_retries_on_failure(self):
        attempts = []

        def flaky_sender(url: str, body: bytes, headers: dict) -> int:
            attempts.append((url, body, headers))
            if len(attempts) == 1:
                raise ConnectionError("Temporary network glitch")
            return 200

        dispatcher = WebhookDispatcher(
            secret="super-secret-key", sender_fn=flaky_sender, max_retries=3
        )
        payload = {"job_id": "job_123", "status": "completed"}
        res = dispatcher.dispatch("https://client.example.com/webhook", payload)

        self.assertTrue(res["delivered"])
        self.assertEqual(res["attempts"], 2)
        sent_url, sent_body, sent_headers = attempts[-1]
        expected_sig = compute_hmac_signature("super-secret-key", sent_body)
        self.assertEqual(
            sent_headers["X-BrowserFarm-Signature"], f"sha256={expected_sig}"
        )


if __name__ == "__main__":
    unittest.main()
