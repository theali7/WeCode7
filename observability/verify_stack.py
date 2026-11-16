"""End-to-end verification against disposable local Compose deployments."""
import base64
import json
import os
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def get(url, body=None, token=None, auth=None, trace_id=None):
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(auth.encode()).decode()
    if trace_id:
        headers["traceparent"] = "00-" + trace_id + "-1234567890abcdef-01"
    request = Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers)
    with urlopen(request, timeout=8) as response:
        data = response.read()
        return json.loads(data) if data else {}

def wait_for(description, function, timeout=180):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            result = function()
            if result:
                print("PASS:", description, flush=True)
                return result
        except (HTTPError, URLError, OSError, ValueError, KeyError) as error:
            last = type(error).__name__
        time.sleep(2)
    raise AssertionError(description + " did not become ready; last error: " + str(last))

def main():
    if os.environ.get("WECODE_DISPOSABLE_MONITORING") != "yes":
        raise SystemExit("Creates accounts: disposable CI deployments only.")
    password = os.environ["GRAFANA_ADMIN_PASSWORD"]
    wait_for("Grafana health", lambda: get("http://127.0.0.1:3000/api/health").get("database") == "ok")
    for port in (8081, 8082):
        wait_for("application health " + str(port), lambda: get(f"http://127.0.0.1:{port}/api/health").get("status") == "ok")
    evidence = {}
    for environment, port in (("development", 8081), ("production", 8082)):
        base = f"http://127.0.0.1:{port}"
        trace_id = secrets.token_hex(16)
        account = {"email": secrets.token_hex(16) + "@example.test", "password": secrets.token_urlsafe(24)}
        session = get(base + "/api/auth/v1/signup", body=account, trace_id=trace_id)
        get(base + "/api/auth/v1/token?grant_type=password", body=account)
        get(base + "/api/rest/v1/learning_way_progress", body={
            "user_id": session["user"]["id"], "item_id": "monitoring:disposable-check"
        }, token=session["access_token"])
        labels = '{service_name="wecode-api",deployment_environment_name="' + environment + '"}'
        def metric(name):
            query = urlencode({"query": "sum(" + name + labels + ")"})
            result = get("http://127.0.0.1:9090/api/v1/query?" + query)
            values = result.get("data", {}).get("result", [])
            return values and float(values[0]["value"][1]) >= 1
        for name in ("wecode_http_requests", "wecode_registrations", "wecode_progress_writes", "wecode_auth_attempts"):
            wait_for(environment + " metric " + name, lambda name=name: metric(name))
        query = '{service_name="wecode-api",deployment_environment_name="' + environment + '"}'
        logs = wait_for(environment + " logs in Loki", lambda: get(
            "http://127.0.0.1:3100/loki/api/v1/query_range?" + urlencode({"query": query, "limit": 5})
        ).get("data", {}).get("result"))
        trace = wait_for(environment + " trace in Tempo", lambda: get(
            "http://127.0.0.1:3200/api/traces/" + trace_id))
        evidence[environment] = {"trace_id": trace_id, "log_streams": len(logs), "trace_received": bool(trace)}
    dashboard = wait_for("provisioned Grafana dashboard", lambda: get(
        "http://127.0.0.1:3000/api/dashboards/uid/wecode-overview", auth="admin:" + password))
    assert dashboard["dashboard"]["uid"] == "wecode-overview"
    assert len(dashboard["dashboard"]["panels"]) == 7
    for uid in ("prometheus", "loki", "tempo"):
        wait_for("Grafana datasource " + uid, lambda uid=uid: get(
            "http://127.0.0.1:3000/api/datasources/uid/" + uid, auth="admin:" + password).get("uid") == uid)
    proxy = wait_for("metrics through Grafana proxy", lambda: get(
        "http://127.0.0.1:3000/api/datasources/proxy/uid/prometheus/api/v1/query?" +
        urlencode({"query": 'sum(wecode_registrations{service_name="wecode-api"})'}), auth="admin:" + password
    ).get("data", {}).get("result"))
    assert float(proxy[0]["value"][1]) >= 2
    # Verify every provisioned PromQL expression is accepted by the real query engine.
    for panel in dashboard["dashboard"]["panels"]:
        if panel["type"] != "timeseries":
            continue
        query = panel["targets"][0]["expr"].replace("$__rate_interval", "1m").replace("$__range", "5m")
        query = query.replace("$environment", ".*").replace("$version", ".*")
        response = get("http://127.0.0.1:9090/api/v1/query?" + urlencode({"query": query}))
        assert response["status"] == "success", panel["title"]
    Path("monitoring-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("PASS: both environments -> Collector -> Prometheus/Loki/Tempo -> provisioned Grafana")

if __name__ == "__main__":
    main()
