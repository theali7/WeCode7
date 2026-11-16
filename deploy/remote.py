"""Deploy a digest-pinned image over SSH without copying application secrets."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REMOTE = r'''
import json, os, pathlib, subprocess
from urllib.request import urlopen
payload = PAYLOAD
name = payload["environment"]
root = pathlib.Path("/srv/wecode")
config = root / "config" / (name + ".env")
if not config.is_file():
    raise SystemExit("Missing server configuration: " + str(config))
if config.stat().st_mode & 0o077:
    raise SystemExit("Server environment file must have mode 0600")
directory = root / "deployments" / name
directory.mkdir(parents=True, exist_ok=True)
compose = directory / "compose.yaml"
compose.write_text(payload["compose"])
env = dict(os.environ, WECODE_IMAGE=payload["image"], APP_VERSION=payload["version"],
           APP_ENV=name, APP_PORT="8081" if name == "development" else "8082")
command = ["docker", "compose", "--env-file", str(config), "-p",
           "wecode-dev" if name == "development" else "wecode-prod", "-f", str(compose)]
subprocess.run(command + ["config", "--quiet"], env=env, check=True)
subprocess.run(command + ["pull"], env=env, check=True)
subprocess.run(command + ["up", "-d", "--wait", "--wait-timeout", "180"], env=env, check=True)
port = env["APP_PORT"]
with urlopen("http://127.0.0.1:" + port + "/api/health", timeout=10) as response:
    if response.status != 200 or json.load(response).get("status") != "ok":
        raise SystemExit("Application health check failed")
release = {"image": payload["image"], "version": payload["version"], "environment": name}
temporary = directory / "release.json.tmp"
temporary.write_text(json.dumps(release) + "\n")
temporary.replace(directory / "release.json")
print("Healthy release deployed:", name, payload["version"])
'''

def validate(image, version, environment):
    if not re.fullmatch(r"ghcr\.io/theali7/wecode7@sha256:[a-f0-9]{64}", image):
        raise ValueError("Only a digest-pinned WeCode7 registry image is accepted")
    if not re.fullmatch(r"[a-f0-9]{40}", version):
        raise ValueError("Version must be a full commit SHA")
    if environment not in ("development", "production"):
        raise ValueError("Unknown deployment environment")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    validate(args.image, args.version, args.environment)
    host, user = os.environ.get("DEPLOY_HOST", ""), os.environ.get("DEPLOY_USER", "")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]*", host):
        raise SystemExit("DEPLOY_HOST must be a hostname or IPv4 address")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
        raise SystemExit("DEPLOY_USER must be a Unix username")
    key, known = os.environ.get("DEPLOY_SSH_KEY", ""), os.environ.get("DEPLOY_KNOWN_HOSTS", "")
    if not key.strip() or not known.strip():
        raise SystemExit("Missing deployment SSH key or pinned known-hosts entry")
    payload = vars(args) | {"compose": Path(__file__).with_name("compose.yaml").read_text()}
    program = REMOTE.replace("PAYLOAD", repr(payload), 1)
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        private, hosts = directory / "key", directory / "known_hosts"
        for path, content in ((private, key), (hosts, known)):
            with path.open("x") as stream:
                path.chmod(0o600)
                stream.write(content.rstrip() + "\n")
        subprocess.run(["ssh", "-i", str(private), "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15", "-o", "UserKnownHostsFile=" + str(hosts),
            user + "@" + host, "python3 -"], input=program, text=True, check=True)

if __name__ == "__main__":
    main()
