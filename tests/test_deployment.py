import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy.remote import main, validate, REMOTE

IMAGE = "ghcr.io/theali7/wecode7@sha256:" + "a" * 64
VERSION = "b" * 40

class DeploymentValidationTests(unittest.TestCase):
    def test_digest_only_and_known_environments(self):
        validate(IMAGE, VERSION, "production")
        for image, version, environment in (
            ("ghcr.io/theali7/wecode7:latest", VERSION, "production"),
            ("ghcr.io/other/project@sha256:" + "a" * 64, VERSION, "production"),
            (IMAGE, "main", "production"),
            (IMAGE, VERSION, "../../production"),
        ):
            with self.subTest(image=image, version=version, environment=environment):
                with self.assertRaises(ValueError):
                    validate(image, version, environment)

    def test_remote_script_compiles(self):
        compile(REMOTE.replace("PAYLOAD", repr({"environment": "development"}), 1), "<remote>", "exec")

    def test_no_ssh_when_host_is_invalid(self):
        with patch.dict(os.environ, {"DEPLOY_HOST": "-oProxyCommand=invalid", "DEPLOY_USER": "wecode"}):
            with patch("sys.argv", ["remote.py", "--environment", "production", "--image", IMAGE, "--version", VERSION]):
                with patch("deploy.remote.subprocess.run") as run:
                    with self.assertRaises(SystemExit):
                        main()
                    run.assert_not_called()

    def test_ssh_pins_host_and_does_not_send_secrets(self):
        environment = {"DEPLOY_HOST": "deploy.example.test", "DEPLOY_USER": "wecode",
                       "DEPLOY_SSH_KEY": "disposable-key", "DEPLOY_KNOWN_HOSTS": "pinned-host"}
        def inspect(command, **kwargs):
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertIn("BatchMode=yes", command)
            self.assertEqual(command[-2:], ["wecode@deploy.example.test", "python3 -"])
            self.assertNotIn("disposable-key", kwargs["input"])
            key = Path(command[command.index("-i") + 1])
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(key.read_text(), "disposable-key\n")
            compile(kwargs["input"], "<ssh-stdin>", "exec")
            return subprocess.CompletedProcess(command, 0)
        with patch.dict(os.environ, environment):
            with patch("sys.argv", ["remote.py", "--environment", "production", "--image", IMAGE, "--version", VERSION]):
                with patch("deploy.remote.subprocess.run", side_effect=inspect) as run:
                    main()
                    run.assert_called_once()

if __name__ == "__main__":
    unittest.main()
