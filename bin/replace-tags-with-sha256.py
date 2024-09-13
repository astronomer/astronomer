#!/usr/bin/env python3

# USAGE:
# use another script to collect all the values you want to shaify
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart > all-values.yaml
# run this script to replace the tags with sha256 hashes
# cat all-values.yaml | ./replace-tags-with-sha256.py 1 > sha-values.yaml
# check for tags without sha256
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart -f ./sha-values.yaml --as-path|grep '\.tag='
# check for images without sha256
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart -f ./sha-values.yaml --as-path|grep '\.image='|grep -v "sha256"
#!/usr/bin/env python3

import sys
import requests
from ruamel.yaml import YAML

# Docker Hub API URL for public repositories
DOCKER_HUB_API_URL = "https://hub.docker.com/v2/repositories/library"


def parse_image(image, explicit_repository_host=None):
    """
    Parse the image into repository_host, repository, and tag.
    Args:
        image (str): The image in the format [repository_host/]namespace/repo[:tag]
    Returns:
        tuple: (repository_host, repository, tag)
    """
    if ":" in image:
        repository, tag = image.rsplit(":", 1)
    else:
        repository, tag = image, "latest"

    # Check if the repository specifies a host (contains a dot in the first segment)
    if explicit_repository_host:
        repository_host = explicit_repository_host
    elif "/" in repository and "." in repository.split("/")[0]:
        repository_host, repository = repository.split("/", 1)
    else:
        repository_host = "docker.io"  # No host means fallback to Docker Hub

    return repository_host, repository, tag


def lookup_digest_dockerhub(repository, tag):
    """
    Look up the SHA hash for a given repository and tag using Docker Hub's public API.
    Args:
        repository (str): The repository name (e.g., "postgres")
        tag (str): The tag for which to retrieve the digest hash
    Returns:
        str: The corresponding SHA digest
    """
    if tag is None:
        return None

    # Set the Docker Hub API URL for retrieving tag information
    repo_url = f"{DOCKER_HUB_API_URL}/{repository}/tags/{tag}/"

    # Send a GET request to the Docker Hub API
    response = requests.get(repo_url)

    # Log the URL on failure
    if response.status_code != 200:
        print(f"Error fetching SHA for {repository}:{tag} from Docker Hub", file=sys.stderr)
        print(f"Attempted URL: {repo_url}", file=sys.stderr)
        print(f"Status code: {response.status_code}", file=sys.stderr)
        print(f"Response body: {response.text}", file=sys.stderr)
        return None

    # Parse the response JSON to extract the SHA digest
    data = response.json()
    raw_digest = data["images"][0]["digest"]
    digest_version, digest_value = raw_digest.split(":", 1)

    return digest_version, digest_value


def lookup_digest_v2(repository_host, repository, tag):
    """
    Look up the SHA hash for a given repository and tag using the Docker Registry V2 API.
    Args:
        repository_host (str): The registry host (e.g., "quay.io", "registry-1.docker.io")
        repository (str): The repository name (e.g., "namespace/repo")
        tag (str): The tag for which to retrieve the SHA hash
    Returns:
        str: The corresponding SHA digest
    """
    if tag is None:
        return None

    # Set the V2 API URL for manifest lookup
    repo_url = f"https://{repository_host}/v2/{repository}/manifests/{tag}"

    # Send a GET request to the V2 API
    headers = {
        "Accept": "application/vnd.docker.distribution.manifest.v2+json",  # Request V2 manifest
    }
    response = requests.get(repo_url, headers=headers)

    # Log the URL on failure
    if response.status_code != 200:
        print(f"Error fetching SHA for {repository}:{tag} from {repository_host}", file=sys.stderr)
        print(f"Attempted URL: {repo_url}", file=sys.stderr)
        print(f"Status code: {response.status_code}", file=sys.stderr)
        print(f"Response body: {response.text}", file=sys.stderr)
        return None

    # Parse the Docker-Content-Digest from the response headers
    raw_digest = response.headers.get("Docker-Content-Digest")

    if not raw_digest:
        return None, None

    digest_version, digest_value = raw_digest.split(":", 1)

    return digest_version, digest_value


def process_yaml(data, new_data):
    """
    Recursively process the YAML structure, replacing image tags with SHA hashes,
    and populating the new_data object with only the tag/image changes and minimal scaffolding.
    Args:
        data (dict or list): The original YAML content to process
        new_data (dict or list): The object where changes will be stored
    """
    for key, value in data.items():
        if isinstance(value, dict):
            temp_data = {}
            process_yaml(value, temp_data)  # Recurse into nested dictionaries
            if temp_data:
                new_data[key] = temp_data
        elif isinstance(value, list):
            temp_list = []
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    temp_item = {}
                    process_yaml(item, temp_item)
                    if temp_item:
                        temp_list.append(temp_item)
            if temp_list:
                new_data[key] = temp_list
        elif key == "image":
            # Parse the image into repository_host, repository, and tag
            explicit_repository_host = data.get("registry")
            repository_host, repository, tag = parse_image(value)

            try:
                sha_hash = None
                if repository_host == "docker.io":
                    # Use Docker Hub public API
                    print(f"Looking up Docker Hub for {repository}:{tag}", file=sys.stderr)
                    digest_version, sha_hash = lookup_digest_dockerhub(repository, tag)
                else:
                    # Use Docker Registry V2 API for other registries (like Quay.io)
                    print(f"Looking up {repository_host} for {repository}:{tag}", file=sys.stderr)
                    digest_version, sha_hash = lookup_digest_v2(repository_host, repository, tag)

                if sha_hash:
                    new_data[key] = f"{repository_host}/{repository}@{digest_version}:{sha_hash}"
            except Exception as e:
                print(f"Failed to process image {repository}:{tag} - {e}", file=sys.stderr)
                continue
        elif key == "defaultAirflowTag":
            if value is None:
                continue  # Leave tags with value None unchanged
            repository_and_host = data["defaultAirflowRepository"]
            repository = data["defaultAirflowRepository"]
            repository_host, repository, _ = parse_image(data["defaultAirflowRepository"])

            try:
                sha_hash = None
                if repository_host == "docker.io":
                    # Use Docker Hub public API
                    print(f"Looking up Docker Hub for {repository}:{value}", file=sys.stderr)
                    digest_version, sha_hash = lookup_digest_dockerhub(repository, value)

                else:
                    # Use Docker Registry V2 API for other registries (like Quay.io)
                    print(f"Looking up {repository_host} for {repository}:{value}", file=sys.stderr)
                    digest_version, sha_hash = lookup_digest_v2(repository_host, repository, value)

                if sha_hash:
                    new_data["defaultAirflowRepository"] = f"{repository_and_host}@{digest_version}"
                    new_data["defaultAirflowTag"] = sha_hash
                    if "defaultAirflowDigest" in data and data["defaultAirflowDigest"] is not None:
                        new_data["defaultAirflowDigest"] = sha_hash
            except Exception as e:
                print(f"Failed to process tag {value} for {repository} - {e}", file=sys.stderr)
                continue
        elif key == "tag":
            if value is None:
                continue  # Leave tags with value None unchanged

            # For `tag`, find the sibling `image` or `repository`
            sibling_repo_key = None
            for sibling_key in ["image", "repository"]:
                if sibling_key in data:
                    sibling_repo_key = sibling_key
                    break

            if sibling_repo_key:
                # Parse the sibling repository and combine with the tag
                # if there is a registry host prepend it to the repository
                explicit_registry = data["registry"] if "registry" in data else None
                repository_host, repository, _ = parse_image(data["repository"], explicit_registry)
                try:
                    sha_hash = None
                    if repository_host == "docker.io":
                        # Use Docker Hub public API
                        print(f"Looking up Docker Hub for {repository}:{value}", file=sys.stderr)
                        digest_version, sha_hash = lookup_digest_dockerhub(repository, value)

                    else:
                        # Use Docker Registry V2 API for other registries (like Quay.io)
                        print(f"Looking up {repository_host} for {repository}:{value}", file=sys.stderr)
                        digest_version, sha_hash = lookup_digest_v2(repository_host, repository, value)

                    if sha_hash:
                        # tag gets the sha256 hash
                        new_data[key] = sha_hash
                        # repository gets the image with the sha256 hash
                        if "registry" in data:
                            new_data["repository"] = f"{repository}@{digest_version}"
                        else:
                            new_data["repository"] = f"{repository_host}/{repository}@{digest_version}"
                except Exception as e:
                    print(f"Failed to process tag {value} for {repository} - {e}", file=sys.stderr)
                    continue


def main():
    yaml = YAML()

    # Read YAML content from stdin (you can also use a file)
    yaml_content = yaml.load(sys.stdin)

    # Create a new object to store the changes
    new_yaml_content = {}

    # Process the YAML content and populate the new object with tag/image changes
    process_yaml(yaml_content, new_yaml_content)

    # Output the new YAML object containing only the tag/image changes
    yaml.dump(new_yaml_content, sys.stdout)


if __name__ == "__main__":
    main()
