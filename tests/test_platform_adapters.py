import base64
import unittest

from src.browser_engine.platform_adapters import (
    AdapterResult,
    AdapterRegistry,
    GithubAdapter,
    NpmAdapter,
    default_registry,
)


class FakeGetJson:
    """Injected fetcher: maps API URL -> JSON payload (or None = failure)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, api_url):
        self.calls.append(api_url)
        if api_url not in self.routes:
            return None
        return self.routes[api_url]


class TestNpmAdapter(unittest.TestCase):
    def test_can_handle_npmjs_package_pages_only(self):
        a = NpmAdapter()
        self.assertTrue(a.can_handle("https://www.npmjs.com/package/left-pad"))
        self.assertTrue(a.can_handle("https://www.npmjs.com/package/@scope/pkg"))
        self.assertFalse(a.can_handle("https://www.npmjs.com/search?q=x"))
        self.assertFalse(a.can_handle("https://example.com/package/left-pad"))

    def test_fetch_builds_markdown_from_registry_json(self):
        payload = {
            "name": "left-pad",
            "description": "String left pad",
            "dist-tags": {"latest": "1.3.0"},
            "license": "WTFPL",
            "homepage": "https://github.com/camwest/left-pad",
            "readme": "# left-pad\n\nUsage: leftPad('a', 3)",
        }
        get = FakeGetJson({"https://registry.npmjs.org/left-pad": payload})
        res = NpmAdapter().fetch("https://www.npmjs.com/package/left-pad", get)
        self.assertIsInstance(res, AdapterResult)
        self.assertEqual(res.adapter, "npm")
        self.assertIn("left-pad", res.markdown)
        self.assertIn("1.3.0", res.markdown)
        self.assertIn("String left pad", res.markdown)
        self.assertIn("Usage: leftPad", res.markdown)

    def test_scoped_package_is_url_encoded_for_registry(self):
        get = FakeGetJson({"https://registry.npmjs.org/@scope%2Fpkg": {
            "name": "@scope/pkg", "dist-tags": {"latest": "2.0.0"}, "description": "d"}})
        res = NpmAdapter().fetch("https://www.npmjs.com/package/@scope/pkg", get)
        self.assertIsNotNone(res)
        self.assertEqual(get.calls, ["https://registry.npmjs.org/@scope%2Fpkg"])

    def test_registry_failure_returns_none_so_ladder_takes_over(self):
        get = FakeGetJson({})
        self.assertIsNone(NpmAdapter().fetch("https://www.npmjs.com/package/nope", get))


class TestGithubAdapter(unittest.TestCase):
    def test_can_handle_repo_root_only(self):
        a = GithubAdapter()
        self.assertTrue(a.can_handle("https://github.com/python/cpython"))
        self.assertFalse(a.can_handle("https://github.com/python/cpython/issues/1"))
        self.assertFalse(a.can_handle("https://github.com/settings"))
        self.assertFalse(a.can_handle("https://gitlab.com/a/b"))

    def test_fetch_repo_with_decoded_readme(self):
        readme_b64 = base64.b64encode("# Hello\n\nRepo readme".encode()).decode()
        get = FakeGetJson({
            "https://api.github.com/repos/o/r": {
                "full_name": "o/r", "description": "A repo", "stargazers_count": 42,
                "license": {"spdx_id": "MIT"}, "default_branch": "main"},
            "https://api.github.com/repos/o/r/readme": {
                "encoding": "base64", "content": readme_b64},
        })
        res = GithubAdapter().fetch("https://github.com/o/r", get)
        self.assertEqual(res.adapter, "github")
        self.assertIn("o/r", res.markdown)
        self.assertIn("42", res.markdown)
        self.assertIn("MIT", res.markdown)
        self.assertIn("Repo readme", res.markdown)

    def test_missing_readme_still_returns_metadata(self):
        get = FakeGetJson({"https://api.github.com/repos/o/r": {
            "full_name": "o/r", "description": "A repo", "stargazers_count": 1}})
        res = GithubAdapter().fetch("https://github.com/o/r", get)
        self.assertIsNotNone(res)
        self.assertIn("A repo", res.markdown)

    def test_repo_api_failure_returns_none(self):
        self.assertIsNone(GithubAdapter().fetch("https://github.com/o/r", FakeGetJson({})))


class TestRegistry(unittest.TestCase):
    def test_first_matching_adapter_wins_and_none_when_unmatched(self):
        reg = AdapterRegistry([NpmAdapter(), GithubAdapter()])
        self.assertEqual(reg.match("https://github.com/o/r").name, "github")
        self.assertEqual(reg.match("https://www.npmjs.com/package/x").name, "npm")
        self.assertIsNone(reg.match("https://example.com/"))

    def test_run_returns_result_or_none(self):
        reg = default_registry()
        get = FakeGetJson({"https://registry.npmjs.org/x": {
            "name": "x", "dist-tags": {"latest": "1.0.0"}, "description": "d"}})
        self.assertIsNotNone(reg.run("https://www.npmjs.com/package/x", get))
        self.assertIsNone(reg.run("https://example.com/", get))

    def test_default_fetcher_refuses_non_allowlisted_hosts(self):
        from src.browser_engine.platform_adapters import _safe_api_url
        self.assertIsNone(_safe_api_url("http://registry.npmjs.org/x"))
        self.assertIsNone(_safe_api_url("https://169.254.169.254/latest/meta-data"))
        self.assertIsNone(_safe_api_url("https://evil.example.com/x"))
        self.assertEqual(_safe_api_url("https://api.github.com/repos/o/r"),
                         "https://api.github.com/repos/o/r")


if __name__ == "__main__":
    unittest.main()
