import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from on_call.worker import eligible, identity, poll, run_agent

def alert():
    return {"state": "firing", "activeAt": "2026-11-16T00:00:00Z",
            "labels": {"alertname": "WeCodeReadinessFailures", "service_name": "wecode-api",
                       "deployment_environment_name": "development", "service_version": "test"},
            "annotations": {"summary": "Database not ready"}}

class OnCallTests(unittest.TestCase):
    def test_single_read_only_grafana_token_proxy_configuration(self):
        from on_call.worker import cloud_configuration
        env = {"ONCALL_GRAFANA_URL": "https://stack.grafana.net",
               "ONCALL_GRAFANA_TOKEN": "fixture", "ONCALL_GRAFANA_PROXY": "1",
               "ONCALL_PROMETHEUS_DATASOURCE_UID": "prom-uid",
               "ONCALL_LOKI_DATASOURCE_UID": "loki-uid"}
        cloud, metrics, logs = cloud_configuration(env)
        self.assertEqual(metrics, "https://stack.grafana.net/api/datasources/proxy/uid/prom-uid")
        self.assertTrue(logs.endswith("/loki-uid"))
        self.assertEqual(cloud["alerts"], cloud["metrics"])
        self.assertEqual(cloud["alerts"], cloud["logs"])
        for invalid in ("https://user:secret@stack.grafana.net", "http://stack.grafana.net"):
            with self.assertRaises(ValueError):
                cloud_configuration({**env, "ONCALL_GRAFANA_URL": invalid})
        with self.assertRaises(ValueError):
            cloud_configuration({**env, "ONCALL_LOKI_DATASOURCE_UID": "../secret"})
        self.assertEqual(cloud_configuration({}), (None, None, None))

    def test_cloud_alert_dispatch_and_credentials_are_separate(self):
        from on_call.worker import fetch
        with self.assertRaises(ValueError):
            fetch("http://example.invalid", "Bearer secret")
        cloud = {"alerts_url": "https://grafana/api/alertmanager/grafana/api/v2/alerts",
                 "alerts": "Bearer alert-token", "metrics": "Basic metric-token", "logs": "Basic log-token"}
        source = alert()
        source["labels"]["alertname"] = "WeCodeAuthenticationRejections"
        item = {**source, "startsAt": source["activeAt"], "status": {"state": "active"}}
        seen = []
        def response(url, authorization=None):
            seen.append((url, authorization))
            if url == cloud["alerts_url"]:
                return [item, {**item, "status": {"state": "suppressed"}}]
            return {"status": "success", "data": {"result": []}}
        with tempfile.TemporaryDirectory() as root, patch("on_call.worker.fetch", side_effect=response):
            with patch("on_call.worker.run_agent") as run:
                self.assertEqual(poll("https://metrics", "https://logs", root, root, ["fixture"], cloud=cloud)["handled"], 1)
                self.assertEqual(poll("https://metrics", "https://logs", root, root, ["fixture"], cloud=cloud)["handled"], 0)
                run.assert_called_once()
                self.assertNotIn("metric-token", run.call_args.args[1])
        self.assertEqual(seen[0][1], cloud["alerts"])
        self.assertEqual(seen[1][1], cloud["metrics"])
        self.assertIn("wecode_http_requests_total", seen[1][0])
        self.assertEqual(seen[2][1], cloud["logs"])

    def test_redirects_are_rejected(self):
        from on_call.worker import NoRedirect
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid")

    def test_only_recognized_firing_alerts_are_dispatched(self):
        self.assertTrue(eligible(alert()))
        for key, value in (("state", "pending"),):
            self.assertFalse(eligible({**alert(), key: value}))
        value = alert()
        value["labels"]["alertname"] = "UnknownAlert"
        self.assertFalse(eligible(value))

    def test_incident_identity_changes_on_new_occurrence(self):
        self.assertNotEqual(identity(alert()), identity({**alert(), "activeAt": "later"}))

    def test_real_subprocess_dispatch_and_persistent_deduplication(self):
        def response(url):
            if url.endswith("/api/v1/alerts"):
                return {"status": "success", "data": {"alerts": [alert()]}}
            return {"status": "success", "data": {"result": []}}
        # Deliberately a deterministic fixture, not an LLM.
        command = [sys.executable, "-c",
                   "import sys; p=sys.stdin.read(); assert 'WeCodeReadinessFailures' in p; print('TEST FIXTURE: incident received')"]
        with tempfile.TemporaryDirectory() as root, patch("on_call.worker.fetch", side_effect=response):
            self.assertEqual(poll("http://prometheus", "http://loki", root, root, command)["handled"], 1)
            self.assertEqual(poll("http://prometheus", "http://loki", root, root, command)["handled"], 0)
            report = Path(root) / identity(alert()) / "report.txt"
            self.assertIn("TEST FIXTURE", report.read_text())

    def test_failed_agent_is_retried_without_claiming_completion(self):
        response = {"status": "success", "data": {"alerts": [alert()]}}
        with tempfile.TemporaryDirectory() as root, patch("on_call.worker.fetch", return_value=response):
            with patch("on_call.worker.run_agent", side_effect=RuntimeError("fixture failure")):
                result = poll("http://prometheus", "http://loki", root, root, ["unused"], retry_seconds=0)
            self.assertEqual(result["failed"], 1)
            state = json.loads((Path(root) / "state.json").read_text())
            self.assertEqual(state[identity(alert())]["status"], "failed")
            with patch("on_call.worker.run_agent") as run:
                self.assertEqual(poll("http://prometheus", "http://loki", root, root, ["unused"])["handled"], 1)
                run.assert_called_once()

    def test_empty_report_and_timeout_are_failures(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            with self.assertRaises(RuntimeError):
                run_agent([sys.executable, "-c", "pass"], "input", root, directory / "out", directory / "err", 5)
            with self.assertRaises(TimeoutError):
                run_agent([sys.executable, "-c", "import time; time.sleep(30)"], "input",
                          root, directory / "out", directory / "err", 0.1)

if __name__ == "__main__":
    unittest.main()
