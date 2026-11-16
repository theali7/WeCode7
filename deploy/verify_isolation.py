"""Verify account and token isolation on disposable local deployments only."""
import json
import os
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen

def request(port, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode()
    req = Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)

def main():
    if os.environ.get("WECODE_DISPOSABLE_ISOLATION") != "yes":
        raise SystemExit("This test creates accounts; use disposable CI environments only.")
    ports = (8081, 8082)
    accounts = []
    for port in ports:
        status, health = request(port, "/api/health")
        assert status == 200 and health["database"] == "postgresql", (port, status)
        account = {"email": secrets.token_hex(16) + "@example.test",
                   "password": secrets.token_urlsafe(24)}
        status, session = request(port, "/api/auth/v1/signup", account)
        assert status == 200 and session.get("access_token"), (port, status)
        accounts.append((account, session))
    for source, target in ((0, 1), (1, 0)):
        account, session = accounts[source]
        status, _ = request(ports[source], "/api/auth/v1/token?grant_type=password", account)
        assert status == 200, ("own account rejected", status)
        status, _ = request(ports[target], "/api/auth/v1/token?grant_type=password", account)
        assert status == 400, ("account crossed environment boundary", status)
        status, _ = request(ports[source], "/api/auth/v1/user", token=session["access_token"])
        assert status == 200, ("own token rejected", status)
        status, _ = request(ports[target], "/api/auth/v1/user", token=session["access_token"])
        assert status == 401, ("token crossed environment boundary", status)
    print("PASS: both environments healthy; account and token isolation verified in both directions.")

if __name__ == "__main__":
    main()
