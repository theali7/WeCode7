import unittest
from unittest.mock import patch
from deploy.render_release import deploy, NoRedirect
IMAGE = "ghcr.io/theali7/wecode7@sha256:" + "a" * 64
VERSION = "b" * 40
SERVICE = "srv-disposable"
def service(plan="free", name="wecode7-dev"):
    return {"id": SERVICE, "name": name, "type": "web_service",
            "serviceDetails": {"plan": plan, "url": "https://wecode7-dev.onrender.com"}}

class RenderReleaseTests(unittest.TestCase):
    def test_paid_or_unknown_plan_never_triggers_deployment(self):
        for plan in ("starter", None):
            with self.subTest(plan=plan), patch("deploy.render_release.api", return_value=service(plan)) as api:
                with self.assertRaises(ValueError):
                    deploy("development", IMAGE, VERSION, SERVICE, "fixture-token")
                self.assertEqual(api.call_count, 1)

    def test_legacy_service_is_not_a_target(self):
        with patch("deploy.render_release.api", return_value=service(name="wecode-assignment2")) as api:
            with self.assertRaises(ValueError):
                deploy("development", IMAGE, VERSION, SERVICE, "fixture-token")
            self.assertEqual(api.call_count, 1)

    def test_pinned_image_and_live_release_are_verified(self):
        live = {"status": "live", "image": {"ref": IMAGE, "sha": "sha256:" + "a" * 64}}
        with patch("deploy.render_release.api", side_effect=[service(), {"id": "dep-fixture"}, live]) as api:
            with patch("deploy.render_release.public_json", side_effect=[
                {"status": "ok"}, {"version": VERSION, "environment": "development"}]):
                result = deploy("development", IMAGE, VERSION, SERVICE, "fixture-token")
                self.assertEqual(result["image"], IMAGE)
                self.assertEqual(api.call_args_list[1].args[2], {"imageUrl": IMAGE})

    def test_wrong_digest_or_wrong_live_version_fails(self):
        for digest, version in (("c" * 64, VERSION), ("a" * 64, "wrong-version")):
            live = {"status": "live", "image": {"ref": IMAGE, "sha": digest}}
            with patch("deploy.render_release.api", side_effect=[service(), {"id": "dep-fixture"}, live]):
                with patch("deploy.render_release.public_json", side_effect=[
                    {"status": "ok"}, {"version": version, "environment": "development"}]):
                    with self.assertRaises(RuntimeError):
                        deploy("development", IMAGE, VERSION, SERVICE, "fixture-token")

    def test_failed_provider_status_is_not_success(self):
        with patch("deploy.render_release.api", side_effect=[
            service(), {"id": "dep-fixture"}, {"status": "update_failed"}]):
            with self.assertRaises(RuntimeError):
                deploy("development", IMAGE, VERSION, SERVICE, "fixture-token")

    def test_invalid_image_and_missing_configuration_do_not_call_provider(self):
        with patch("deploy.render_release.api") as api:
            with self.assertRaises(ValueError):
                deploy("development", "ghcr.io/theali7/wecode7:latest", VERSION, SERVICE, "fixture-token")
            with self.assertRaises(ValueError):
                deploy("development", IMAGE, VERSION, SERVICE, "")
            api.assert_not_called()

    def test_timeout_is_not_success(self):
        with patch("deploy.render_release.api", side_effect=[service(), {"id": "dep-fixture"}]):
            with patch("deploy.render_release.time.monotonic", side_effect=[0, 2]):
                with self.assertRaises(TimeoutError):
                    deploy("development", IMAGE, VERSION, SERVICE, "fixture-token", timeout=1)

    def test_redirects_do_not_forward_credentials(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

if __name__ == "__main__":
    unittest.main()
