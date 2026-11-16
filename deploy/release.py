"""Select the configured deployment provider; Render Free is the default."""
import argparse
import os
import subprocess
import sys
from deploy.remote import validate

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    validate(args.image, args.version, args.environment)
    target = os.environ.get("WECODE_DEPLOY_TARGET", "render")
    if target not in {"render", "ssh"}:
        raise SystemExit("WECODE_DEPLOY_TARGET must be render or ssh")
    subprocess.run([sys.executable, "-m", "deploy.render_release" if target == "render" else "deploy.remote",
                    "--environment", args.environment, "--image", args.image, "--version", args.version], check=True)

if __name__ == "__main__":
    main()
