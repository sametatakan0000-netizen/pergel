import os
import tempfile
import unittest
from src.api.job_store import JobStore


class TestJobStore(unittest.TestCase):
    def test_create_update_and_fetch_job_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(os.path.join(tmp, "jobs.db"))
            job = store.create_job(
                target_url="https://example.com",
                goal="Extract pricing",
                needs_vision=False,
                js_complexity="low",
                webhook_url="https://client.example.com/hook",
            )
            self.assertEqual(job["status"], "queued")
            self.assertTrue(job["job_id"].startswith("job_"))
            self.assertEqual(job["session_name"], f"farm_{job['job_id']}")

            store.mark_running(job["job_id"], engine="lightpanda")
            running = store.get_job(job["job_id"])
            self.assertEqual(running["status"], "running")
            self.assertEqual(running["engine"], "lightpanda")

            store.mark_completed(
                job["job_id"],
                engine="chromium-browser-use",
                extracted_markdown="# Pricing\n$10/mo",
                oracle_passed=True,
            )
            done = store.get_job(job["job_id"])
            self.assertEqual(done["status"], "completed")
            self.assertEqual(done["engine"], "chromium-browser-use")
            self.assertTrue(done["oracle_passed"])
            self.assertIn("$10/mo", done["extracted_markdown"])


if __name__ == "__main__":
    unittest.main()
