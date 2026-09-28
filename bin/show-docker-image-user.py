#!/usr/bin/env python3
"""Show the user (USER directive) that a docker image runs as.

Queries the Docker Registry v2 API for an image's config blob and reports its
`config.User` value, without pulling image layers. This is useful for verifying
that a securityContext `runAsUser` matches the UID an image was actually built
for (see PINF-713).

A USER value of "" means the image runs as root (UID 0).

Examples:
    bin/show-docker-image-user.py quay.io/astronomer/ap-commander:2.0.15
    bin/show-docker-images.py --with-houston | awk '{print $2}' | bin/show-docker-image-user.py
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

# Accept headers covering both Docker and OCI manifest and index media types.
MANIFEST_ACCEPT = "application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json"

DEFAULT_REGISTRY = "registry-1.docker.io"


def parse_image_ref(image):
    """Split an image reference into (registry, repository, reference).

    Handles docker.io shorthand (e.g. "nginx" -> "library/nginx" on registry-1.docker.io)
    and explicit registries (e.g. "quay.io/astronomer/ap-commander:2.0.15").
    """
    remainder = image
    # A leading component with a "." or ":" (or "localhost") is a registry host.
    first, _, rest = remainder.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry = first
        remainder = rest
    else:
        registry = DEFAULT_REGISTRY

    # Separate the reference (tag or digest) from the repository path.
    if "@" in remainder:
        repository, _, reference = remainder.partition("@")
    elif ":" in remainder.rsplit("/", 1)[-1]:
        repository, _, reference = remainder.rpartition(":")
    else:
        repository, reference = remainder, "latest"

    if registry == DEFAULT_REGISTRY and "/" not in repository:
        repository = f"library/{repository}"

    return registry, repository, reference


def _registry_get(url, token, accept):
    """Perform a registry GET, returning (status, headers, body_bytes)."""
    headers = {"Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read()


def _parse_www_authenticate(header):
    """Parse a Bearer challenge header into a dict of its key="value" params."""
    params = {}
    scheme, _, rest = header.partition(" ")
    if scheme.lower() != "bearer":
        return params
    for part in rest.split(","):
        key, _, value = part.strip().partition("=")
        params[key] = value.strip('"')
    return params


def get_token(challenge_header):
    """Fetch an anonymous bearer token for the realm named in the challenge header."""
    params = _parse_www_authenticate(challenge_header)
    realm = params.get("realm")
    if not realm:
        return None
    query = []
    if params.get("service"):
        query.append(f"service={urllib.parse.quote(params['service'])}")
    if params.get("scope"):
        query.append(f"scope={urllib.parse.quote(params['scope'])}")
    url = realm + ("?" + "&".join(query) if query else "")
    with urllib.request.urlopen(url) as response:  # noqa: S310
        return json.load(response).get("token")


def fetch_json(registry, path, token, accept):
    """GET a registry path, transparently acquiring a bearer token on 401."""
    url = f"https://{registry}/v2/{path}"
    status, headers, body = _registry_get(url, token, accept)
    if status == 401 and not token:
        token = get_token(headers.get("Www-Authenticate", ""))
        status, headers, body = _registry_get(url, token, accept)
    if status != 200:
        raise RuntimeError(f"{url} returned HTTP {status}: {body[:200].decode(errors='replace')}")
    return json.loads(body), token


def get_image_user(image, platform="linux/amd64"):
    """Return the config.User value for the given image reference."""
    registry, repository, reference = parse_image_ref(image)

    manifest, token = fetch_json(registry, f"{repository}/manifests/{reference}", None, MANIFEST_ACCEPT)

    # If this is a multi-arch index, select the manifest for the requested platform.
    if "manifests" in manifest:
        want_os, _, want_arch = platform.partition("/")
        digest = None
        for entry in manifest["manifests"]:
            entry_platform = entry.get("platform", {})
            if entry_platform.get("os") == want_os and entry_platform.get("architecture") == want_arch:
                digest = entry["digest"]
                break
        if digest is None:
            raise RuntimeError(f"{image}: no {platform} manifest in image index")
        manifest, token = fetch_json(registry, f"{repository}/manifests/{digest}", token, MANIFEST_ACCEPT)

    config_digest = manifest["config"]["digest"]
    config, _ = fetch_json(registry, f"{repository}/blobs/{config_digest}", token, "application/json")
    return config.get("config", {}).get("User", "")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "images",
        nargs="*",
        help="image reference(s), e.g. quay.io/astronomer/ap-commander:2.0.15. If omitted, read one per line from stdin.",
    )
    parser.add_argument("--platform", default="linux/amd64", help="platform to inspect for multi-arch images")
    args = parser.parse_args()

    images = args.images or [line.strip() for line in sys.stdin if line.strip()]
    if not images:
        parser.error("no images provided on the command line or stdin")

    width = max(len(image) for image in images)
    exit_code = 0
    for image in images:
        try:
            user = get_image_user(image, platform=args.platform)
        except Exception as err:  # noqa: BLE001 - report and continue across images
            print(f"{image:{width}}  ERROR: {err}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"{image:{width}}  USER={user!r}{'  (root)' if user in ('', '0', 'root') else ''}")

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
