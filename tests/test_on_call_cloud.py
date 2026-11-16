import unittest
from on_call.cloud import choose_source


class CloudLauncherTests(unittest.TestCase):
    def test_unique_sources_are_discovered_by_type(self):
        sources = [{"type": "prometheus", "uid": "metrics"},
                   {"type": "loki", "uid": "logs"}]
        self.assertEqual(choose_source(sources, "loki"), "logs")

    def test_multiple_sources_require_explicit_choice(self):
        sources = [{"type": "prometheus", "uid": "a"},
                   {"type": "prometheus", "uid": "b"}]
        with self.assertRaises(ValueError):
            choose_source(sources, "prometheus")
        self.assertEqual(choose_source(sources, "prometheus", "b"), "b")
        with self.assertRaises(ValueError):
            choose_source(sources, "prometheus", "unknown")


if __name__ == "__main__":
    unittest.main()
