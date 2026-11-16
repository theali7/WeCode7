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
