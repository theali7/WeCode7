"""Select one immutable linux/amd64 image from a registry manifest or index."""
import json
import re
import sys


def platform_digest(document, source_digest):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", source_digest):
        raise ValueError("Invalid source digest")
    media_type = document.get("mediaType")
    if media_type in {
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    }:
        return source_digest
    if media_type not in {
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    }:
        raise ValueError("Unsupported registry manifest type")
    candidates = [item for item in document.get("manifests", [])
                  if item.get("platform", {}).get("os") == "linux"
                  and item.get("platform", {}).get("architecture") == "amd64"
                  and item.get("mediaType") in {
                      "application/vnd.oci.image.manifest.v1+json",
                      "application/vnd.docker.distribution.manifest.v2+json"}]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one linux/amd64 image manifest")
    digest = candidates[0].get("digest", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("Invalid platform digest")
    return digest


if __name__ == "__main__":
    print("digest=" + platform_digest(json.load(sys.stdin), sys.argv[1]))
