import unittest
from deploy.image_digest import platform_digest

SOURCE = "sha256:" + "a" * 64
LEAF = "sha256:" + "b" * 64
MANIFEST = "application/vnd.oci.image.manifest.v1+json"
INDEX = "application/vnd.oci.image.index.v1+json"


def descriptor(os="linux", architecture="amd64", digest=LEAF):
    return {"mediaType": MANIFEST, "digest": digest,
            "platform": {"os": os, "architecture": architecture}}


class PlatformDigestTests(unittest.TestCase):
    def test_attestations_and_other_platforms_are_not_deployment_targets(self):
        index = {"mediaType": INDEX, "manifests": [
            descriptor("unknown", "unknown"), descriptor(),
            descriptor(architecture="arm64")]}
        self.assertEqual(platform_digest(index, SOURCE), LEAF)

    def test_a_single_image_manifest_keeps_its_pinned_digest(self):
        self.assertEqual(platform_digest({"mediaType": MANIFEST}, SOURCE), SOURCE)

    def test_missing_ambiguous_or_invalid_platforms_fail_closed(self):
        for entries in ([], [descriptor(), descriptor()],
                        [descriptor(digest="latest")], [descriptor(architecture="arm64")]):
            with self.assertRaises(ValueError):
                platform_digest({"mediaType": INDEX, "manifests": entries}, SOURCE)
        with self.assertRaises(ValueError):
            platform_digest({"mediaType": "unknown"}, SOURCE)


if __name__ == "__main__":
    unittest.main()
