import unittest

from src.browser_engine import worker as worker_mod
from src.browser_engine.platform_adapters import AdapterResult


class _NeverCalled:
    def __init__(self):
        self.called = False

    def __call__(self, *args, **kwargs):
        self.called = True
        raise AssertionError("engine ladder must not run when an adapter answers")


class TestWorkerAdapterShortCircuit(unittest.TestCase):
    def test_execute_task_uses_platform_adapter_before_engine_ladder(self):
        driver = _NeverCalled()
        w = worker_mod.BrowserWorker(driver_fn=driver)
        result = w.execute_task("job1", "https://www.npmjs.com/package/left-pad")
        self.assertFalse(driver.called)
        self.assertTrue(result["oracle_passed"])
        self.assertEqual(result["final_engine"], "platform-adapter:npm")
        self.assertIn("left-pad", result["markdown"])
        self.assertEqual(result["adapter"], "npm")

    def test_unmatched_url_falls_through_to_engine_ladder(self):
        driver = _NeverCalled()
        w = worker_mod.BrowserWorker(driver_fn=driver)
        result = w.execute_task("job2", "https://example.com/anything")
        self.assertTrue(driver.called)  # ladder attempted (and yielded empty here)
        self.assertEqual(result.get("adapter"), None)

    def test_adapter_none_falls_through_to_engine_ladder(self):
        calls = []

        def driver(engine, url, session):
            calls.append(engine)
            return ""

        w = worker_mod.BrowserWorker(driver_fn=driver)
        # npm URL but registry unreachable (default get returns None => None result)
        w.execute_task("job3", "https://www.npmjs.com/package/definitely-not-real-pkg")
        self.assertTrue(calls)  # engines were attempted

    def test_adapter_result_conversion_helper(self):
        res = AdapterResult(adapter="npm", url="u", markdown="# m\n", metadata={"k": "v"})
        self.assertEqual(worker_mod._adapter_result_to_task_result("j", res, ["adapted:npm"])["adapter"], "npm")
        self.assertIn("# m", worker_mod._adapter_result_to_task_result("j", res, ["adapted:npm"])["markdown"])


if __name__ == "__main__":
    unittest.main()
