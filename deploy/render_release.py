"""Deploy only an existing Free Render service using a pinned Docker digest."""
import argparse
import json
import os
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from deploy.remote import validate

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def api(path, token, body=None):
    request = Request("https://api.render.com/v1/" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        # Provider error bodies can contain configuration; do not print them.
        raise RuntimeError("Render API returned HTTP " + str(error.code)) from None

def public_json(url):
    with build_opener(NoRedirect).open(Request(url, headers={"Accept": "application/json"}), timeout=20) as response:
        return json.load(response)

def deploy(environment, image, version, service_id, token, timeout=600):
    validate(image, version, environment)
    if not re.fullmatch(r"srv-[a-z0-9]+", service_id):
        raise ValueError("Invalid Render service ID")
    if not token:
        raise ValueError("Missing RENDER_API_KEY")
    service = api("services/" + service_id, token)
    expected_name = "wecode7-dev" if environment == "development" else "wecode7-prod"
    if service.get("name") != expected_name or service.get("type") != "web_service":
        raise ValueError("Expected a dedicated " + expected_name + " web service; existing legacy site is not a target")
    details = service.get("serviceDetails", {})
    if details.get("plan") != "free":
        raise ValueError("Refusing a service that is not explicitly on the Free plan")
    origin = details.get("url", "").rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Invalid public service URL")
    started = api("services/" + service_id + "/deploys", token, {"imageUrl": image})
    deploy_id = started.get("id", "")
    if not re.fullmatch(r"dep-[a-z0-9]+", deploy_id):
        raise RuntimeError("Render did not return a deployment ID; inspect the provider before retrying")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = api("services/" + service_id + "/deploys/" + deploy_id, token)
        status = current.get("status")
        if status in {"build_failed", "update_failed", "pre_deploy_failed", "canceled", "deactivated"}:
            raise RuntimeError("Render deployment ended with " + status)
        if status == "live":
            resolved = current.get("image", {})
            digest = str(resolved.get("sha", "")).removeprefix("sha256:")
            if resolved.get("ref") != image or digest != image.split("sha256:", 1)[1]:
                raise RuntimeError("Live deployment digest does not match the tested image")
            health = public_json(origin + "/api/health")
            release = public_json(origin + "/api/release")
            if health.get("status") != "ok" or release.get("version") != version or release.get("environment") != environment:
                raise RuntimeError("Live health or release identity did not match")
            print("Verified Free Render deployment:", environment, deploy_id, version)
            return {"deploy_id": deploy_id, "image": image, "version": version, "url": origin}
        time.sleep(5)
    raise TimeoutError("Render deployment did not become live before the time limit")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "production"])
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    deploy(args.environment, args.image, args.version,
           os.environ.get("RENDER_SERVICE_ID", ""), os.environ.get("RENDER_API_KEY", ""))

if __name__ == "__main__":
    main()
