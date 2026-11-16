"""Interactive Cloud responder launcher. Tokens stay in process memory."""
import argparse
import getpass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .worker import cloud_configuration, fetch, poll, run_agent


def find_codex():
    installed = shutil.which("codex")
    bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")
    if installed:
        return installed
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    raise ValueError("Codex CLI was not found; install it from the official OpenAI source")


def choose_source(sources, kind, requested=None):
    candidates = [item for item in sources if item.get("type") == kind]
    if requested:
        candidates = [item for item in candidates if item.get("uid") == requested]
    if len(candidates) != 1:
        raise ValueError("Specify the " + kind + " data-source UID; found " + str(len(candidates)) + " matches")
    return candidates[0]["uid"]


def select_source(sources, kind, requested=None):
    candidates = [item for item in sources if item.get("type") == kind]
    if not requested and len(candidates) > 1:
        print("Available " + kind + " sources:")
        for item in candidates:
            print("  " + item["uid"] + "  " + item.get("name", ""))
        requested = input("WeCode " + kind + " source UID: ").strip()
    return choose_source(sources, kind, requested)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", required=True)
    parser.add_argument("--prometheus-uid")
    parser.add_argument("--loki-uid")
    parser.add_argument("--check", action="store_true", help="Verify live API access and a real Codex response, then exit")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if not (repo / ".git").exists():
        raise ValueError("Run this from a Git checkout of the project")
    executable = find_codex()
    command = [executable, "exec", "--ignore-user-config", "--ephemeral", "--sandbox", "read-only", "-"]
    subprocess.run([executable, "login", "status"], check=True)
    print("The responder sends selected WeCode alerts and telemetry to OpenAI Codex for read-only investigation.")
    token = getpass.getpass("Grafana Viewer token (hidden; not saved): ").strip()
    config = {"ONCALL_GRAFANA_URL": args.grafana_url, "ONCALL_GRAFANA_TOKEN": token,
              "ONCALL_GRAFANA_PROXY": "1", "ONCALL_PROMETHEUS_DATASOURCE_UID": "pending",
              "ONCALL_LOKI_DATASOURCE_UID": "pending"}
    # Validate the destination before sending a credential to it.
    cloud, _, _ = cloud_configuration(config)
    sources = fetch(args.grafana_url.rstrip("/") + "/api/datasources", cloud["alerts"])
    config["ONCALL_PROMETHEUS_DATASOURCE_UID"] = select_source(sources, "prometheus", args.prometheus_uid)
    config["ONCALL_LOKI_DATASOURCE_UID"] = select_source(sources, "loki", args.loki_uid)
    cloud, prometheus, loki = cloud_configuration(config)
    alerts = fetch(cloud["alerts_url"], cloud["alerts"])
    if not isinstance(alerts, list):
        raise ValueError("Unexpected alerts response")
    for endpoint, authorization in (
        (prometheus + "/api/v1/query?query=vector%281%29", cloud["metrics"]),
        (loki + '/loki/api/v1/labels', cloud["logs"]),
    ):
        if fetch(endpoint, authorization).get("status") != "success":
            raise ValueError("A telemetry access check failed")
    print("Grafana alerts, metrics and logs access verified.")
    with tempfile.TemporaryDirectory(prefix="wecode-agent-check-") as temporary:
        output = Path(temporary) / "final.txt"
        run_agent(command[:-1] + ["--output-last-message", str(output), "-"],
                  "Reply with exactly READY. Do not use tools.", repo,
                  Path(temporary) / "stdout", Path(temporary) / "stderr", 120)
        if not output.exists() or output.read_text().strip() != "READY":
            raise ValueError("Codex did not pass the live response check")
    print("Real Codex response verified.")
    if args.check:
        return
    state = Path.home() / ".local/state/wecode-oncall"
    print("Polling every 60 seconds. Reports: " + str(state) + ". Ctrl+C stops.")
    while True:
        result = poll(prometheus, loki, repo, state, command, cloud=cloud)
        print(result, flush=True)
        if args.once:
            if result.get("failed"):
                raise SystemExit(1)
            return
        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nResponder stopped.")
    except Exception as error:
        # Exception text may contain URLs or request details; do not print credentials.
        raise SystemExit("Startup/poll failed: " + type(error).__name__ + ". Check API permissions, CLI login and network access.")
