import unittest
from on_call.cloud import choose_source


class CloudLauncherTests(unittest.TestCase):
    def test_network_diagnostics_do_not_echo_secrets(self):
        import socket
        import ssl
        from urllib.error import URLError, HTTPError
        from on_call.cloud import safe_error
        self.assertIn("DNS", safe_error(URLError(socket.gaierror(-2, "secret"))))
        self.assertIn("TLS", safe_error(URLError(ssl.SSLCertVerificationError(1, "secret"))))
        self.assertIn("timed out", safe_error(URLError(TimeoutError("secret"))))
        self.assertIn("403", safe_error(HTTPError("https://secret", 403, "secret", {}, None)))
        for error in (URLError("secret"), ValueError("secret")):
            self.assertNotIn("secret", safe_error(error))

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
