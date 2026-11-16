"""Cause a reversible database outage in CI and verify alert-to-worker dispatch."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import urlopen
from on_call.worker import poll
from observability.verify_stack import get, wait_for

def main():
    if os.environ.get("WECODE_DISPOSABLE_MONITORING") != "yes":
        raise SystemExit("This test stops a database; disposable CI environments only.")
    configuration = Path(os.environ["RUNNER_TEMP"]) / "development.env"
    command = ["docker", "compose", "--env-file", str(configuration), "-p", "wecode-monitoring-dev",
               "-f", "deploy/compose.yaml", "-f", "deploy/telemetry.compose.yaml"]
    # Confirm the exact disposable target exists before issuing stop.
    ids = subprocess.check_output(command + ["ps", "-q", "db"], text=True).split()
    assert len(ids) == 1, "Expected one disposable development database"
    inspected = json.loads(subprocess.check_output(["docker", "inspect", ids[0]]))[0]
    assert inspected["Config"]["Labels"]["com.docker.compose.project"] == "wecode-monitoring-dev"
    subprocess.run(command + ["stop", "db"], check=True)
    try:
        def firing():
            try:
                with urlopen("http://127.0.0.1:8081/api/health", timeout=10) as response:
                    pass
            except HTTPError as error:
                assert error.code == 503
            alerts = get("http://127.0.0.1:9090/api/v1/alerts")["data"]["alerts"]
            return [item for item in alerts if item["state"] == "firing"
                    and item["labels"].get("alertname") == "WeCodeReadinessFailures"
                    and item["labels"].get("deployment_environment_name") == "development"]
        incidents = wait_for("real readiness alert firing after reversible database outage", firing, timeout=240)
        required = {"service_name", "deployment_environment_name", "service_version", "owner"}
        assert required.issubset(incidents[0]["labels"])
        assert incidents[0]["annotations"]["dashboard_url"]
        # Test fixture proves dispatch, not a real AI investigation.
        driver = [sys.executable, "-c",
                  "import sys; p=sys.stdin.read(); assert 'WeCodeReadinessFailures' in p; print('TEST FIXTURE: alert received; no LLM was called')"]
        with tempfile.TemporaryDirectory() as root:
            first = poll("http://127.0.0.1:9090", "http://127.0.0.1:3100", Path.cwd(), root, driver)
            second = poll("http://127.0.0.1:9090", "http://127.0.0.1:3100", Path.cwd(), root, driver)
            assert first["handled"] == 1 and second["handled"] == 0
            Path("oncall-evidence.json").write_text(json.dumps({
                "alertname": incidents[0]["labels"]["alertname"],
                "real_alert_fired": True, "fixture_dispatches": first["handled"],
                "duplicate_dispatches": second["handled"], "real_ai_invoked": False
            }, indent=2) + "\n")
        print("PASS: real Prometheus alert -> worker -> fixture subprocess; duplicate suppressed")
    finally:
        subprocess.run(command + ["up", "-d", "--wait", "--wait-timeout", "120", "db"], check=True)
        wait_for("database readiness recovered", lambda: get("http://127.0.0.1:8081/api/health").get("status") == "ok")

if __name__ == "__main__":
    main()
