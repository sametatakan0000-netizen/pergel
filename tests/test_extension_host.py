"""B series: safe extension-attachment surface (isolation + stable contract).

The worry this pins down: attaching extensions/tools later must NOT tangle the
core modules. So extensions never touch the core directly — they connect to a
single stable seam (``ExtensionHost``), each in its own isolated capsule. One
extension crashing/disabling must not disturb the core or the others.

These tests are the contract proof:
- extensions connect through the host only (no core reach-in),
- one failing extension cannot take down the host or its siblings,
- enabling/disabling/attaching/detaching is side-effect-free for the rest.
"""
import unittest

from src.browser_engine.extension_host import Extension, ExtensionHost, ExtensionError


def _block_rule(rule_id, host):
    return [{
        "id": rule_id, "priority": 1,
        "action": {"type": "block"},
        "condition": {"urlFilter": f"||{host}^", "resourceTypes": ["main_frame"]},
    }]


class HostContractTests(unittest.TestCase):
    def test_attach_extension_and_decide(self):
        host = ExtensionHost()
        host.attach(Extension(name="blocker", dnr_rules=_block_rule(1, "ads.example")))
        self.assertEqual(host.check("https://ads.example/x", "main_frame").action, "block")

    def test_host_allows_when_no_extension_matches(self):
        host = ExtensionHost()
        host.attach(Extension(name="blocker", dnr_rules=_block_rule(1, "ads.example")))
        self.assertEqual(host.check("https://work.example/", "main_frame").action, "allow")

    def test_extensions_are_isolated_from_each_other(self):
        host = ExtensionHost()
        host.attach(Extension(name="a", dnr_rules=_block_rule(1, "a.example")))
        host.attach(Extension(name="b", dnr_rules=_block_rule(2, "b.example")))
        # both independently enforced
        self.assertEqual(host.check("https://a.example/", "main_frame").action, "block")
        self.assertEqual(host.check("https://b.example/", "main_frame").action, "block")

    def test_one_failing_extension_does_not_break_host_or_siblings(self):
        host = ExtensionHost()
        host.attach(Extension(name="good", dnr_rules=_block_rule(1, "good.example")))

        class Boom(Extension):
            def __init__(self):
                super().__init__(name="boom", dnr_rules=[])

            def engine(self):
                raise RuntimeError("extension exploded")

        host.attach(Boom())
        host.attach(Extension(name="also-good", dnr_rules=_block_rule(2, "also.example")))
        # host still healthy; the good siblings still enforced
        self.assertEqual(host.check("https://good.example/", "main_frame").action, "block")
        self.assertEqual(host.check("https://also.example/", "main_frame").action, "block")

    def test_detach_removes_only_that_extension(self):
        host = ExtensionHost()
        host.attach(Extension(name="a", dnr_rules=_block_rule(1, "a.example")))
        host.attach(Extension(name="b", dnr_rules=_block_rule(2, "b.example")))
        host.detach("a")
        self.assertEqual(host.check("https://a.example/", "main_frame").action, "allow")
        self.assertEqual(host.check("https://b.example/", "main_frame").action, "block")

    def test_disable_re_enables_single_extension(self):
        host = ExtensionHost()
        host.attach(Extension(name="a", dnr_rules=_block_rule(1, "a.example")))
        host.set_enabled("a", False)
        self.assertEqual(host.check("https://a.example/", "main_frame").action, "allow")
        host.set_enabled("a", True)
        self.assertEqual(host.check("https://a.example/", "main_frame").action, "block")

    def test_duplicate_names_rejected(self):
        host = ExtensionHost()
        host.attach(Extension(name="a", dnr_rules=[]))
        with self.assertRaises(ExtensionError):
            host.attach(Extension(name="a", dnr_rules=[]))

    def test_attach_is_idempotent_per_name_listing(self):
        host = ExtensionHost()
        host.attach(Extension(name="a", dnr_rules=[]))
        host.attach(Extension(name="b", dnr_rules=[]))
        self.assertEqual(sorted(host.list_extensions()), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
