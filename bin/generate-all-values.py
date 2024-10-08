#!/usr/bin/env python

# use another script to collect all the values you want to shaify

# generate a file of all values
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart > all-values.yaml
# see all values as a path like you would pass into via --set on helm
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart --as-path
# or just the ones that end in tag=
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart --as-path|grep 'tag='
# or pass in some values to override from a candidate values.yaml you intend to use to make sure you got all the values you wanted to change
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart -f ./my-values.yaml
# ./generate-all-values.py ~/astronomer --mount astronomer.houston.config.deployments.helm=~/airflow-chart -f ./my-values.yaml --as-path

import yaml
import tempfile
import argparse
import shutil
import requests
from deepmerge import always_merger
from pathlib import Path


# Function to load YAML file
def load_yaml(file_path):
    file_path = Path(file_path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"No such file or file is a directory: {file_path}")

    with file_path.open("r") as f:
        return yaml.safe_load(f)


# Function to deep merge two dictionaries
def deep_merge(dict1, dict2):
    return always_merger.merge(dict1, dict2)


# Function to download a chart using requests
def download_chart(chart_name, version=None, repository=None, destination_dir=None):
    if repository:
        url = f"{repository}/{chart_name}-{version}.tgz" if version else f"{repository}/{chart_name}.tgz"
    else:
        url = (
            f"https://charts.helm.sh/stable/{chart_name}-{version}.tgz"
            if version
            else f"https://charts.helm.sh/stable/{chart_name}.tgz"
        )

    destination_dir = Path(destination_dir or tempfile.mkdtemp())

    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()

    chart_tgz_path = destination_dir / f"{chart_name}.tgz"
    with chart_tgz_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    # Extract the chart
    shutil.unpack_archive(str(chart_tgz_path), str(destination_dir))
    chart_tgz_path.unlink()  # Remove the .tgz file after extraction

    return destination_dir / chart_name


# Recursively nest values based on dotted path
def set_nested_value(obj, path, value):
    keys = path.split(".")
    for key in keys[:-1]:
        obj = obj.setdefault(key, {})
    obj[keys[-1]] = value


# Fetch all the charts from mounts in a single pass and store them in an object structure
def fetch_mounts(mounts):
    fetched_mounts = {}

    for mount_key, mount_value in mounts.items():
        if isinstance(mount_value, dict):
            # Recursively process nested mounts
            fetched_mounts[mount_key] = fetch_mounts(mount_value)
        else:
            # Fetch the chart and load the values
            mount_path = Path(mount_value).expanduser().resolve()
            if mount_path.is_dir():
                _, chart_values = load_chart(mount_path)
            else:
                chart_values = load_yaml(mount_path)
            # Nest the values using the dotted path
            set_nested_value(fetched_mounts, mount_key, chart_values)

    return fetched_mounts


# Recursively load and merge charts
def load_chart(chart_path, values=None):
    values = values or {}

    chart_path = Path(chart_path).expanduser().resolve()

    # Ensure that chart_path is a directory
    if not chart_path.is_dir():
        raise FileNotFoundError(f"Expected a directory for the chart path, but found: {chart_path}")

    # Load the chart.yaml and values.yaml
    chart_yaml_path = chart_path / "Chart.yaml"
    values_yaml_path = chart_path / "values.yaml"

    chart = load_yaml(chart_yaml_path)
    chart_values = load_yaml(values_yaml_path) if values_yaml_path.exists() and values_yaml_path.is_file() else {}
    chart_name = chart["name"]

    # merge the values into chart_values
    values = deep_merge(chart_values, values)

    # Process dependencies (subcharts)
    if "dependencies" in chart:
        for dep in chart["dependencies"]:
            dep_name = dep["name"]
            dep_version = dep.get("version", None)
            dep_repository = dep.get("repository", None)  # Handle repository field

            # Check if subchart is local or needs to be downloaded
            subchart_path = chart_path / "charts" / dep_name
            if not subchart_path.exists():
                subchart_path = download_chart(dep_name, dep_version, dep_repository)

            # Recursively load and merge the subchart values
            subchart_name, subchart_values = load_chart(subchart_path, values.get(dep_name, {}))
            if dep_name in values:
                values[dep_name] = deep_merge(subchart_values, values[dep_name])
            else:
                values[dep_name] = subchart_values

    return chart_name, values


# Parse the mount arguments and split by dots to form nested structure
def parse_mounts(mount_args):
    mounts = {}
    for mount_arg in mount_args:
        path_key, path_value = mount_arg.split("=", 1)
        keys = path_key.split(".")
        current = mounts
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        current[keys[-1]] = Path(path_value).expanduser().resolve()
    return mounts


# Convert dictionary to foo.bar=value format
def as_path_format(data, parent_key=""):
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(as_path_format(v, new_key))
        else:
            items.append(f"{new_key}={v}")
    return items


# Main function to handle argparse and program flow
def main():
    parser = argparse.ArgumentParser(description="Recursively load and merge Helm chart values.")
    parser.add_argument("chart", help="Path to the Helm chart")
    parser.add_argument("-f", "--values-file", help="Path to an external values file", default=None)
    parser.add_argument("--mount", help="Mount additional files or directories as subcharts", action="append", default=[])
    parser.add_argument("--as-path", help="Output values in foo.bar=value format", action="store_true")

    args = parser.parse_args()

    # Parse values.yaml once and pass relevant subsets
    user_values = load_yaml(args.values_file) if args.values_file else {}
    mounts = parse_mounts(args.mount)

    # First pass: Fetch all the mounted charts and store in an object structure
    fetched_mounts = fetch_mounts(mounts)

    # Deep merge fetched mounts with user values (user values take priority)
    merged_values = deep_merge(fetched_mounts, user_values)

    # Load the chart and merge the result with merged values
    chart_path = Path(args.chart).expanduser().resolve()

    if not chart_path.exists() or not chart_path.is_dir():
        raise FileNotFoundError(f"No such directory: {chart_path}")

    _, merged_values = load_chart(chart_path, merged_values)

    if args.as_path:
        path_values = as_path_format(merged_values)
        for item in path_values:
            print(item)
    else:
        print(yaml.dump(merged_values, default_flow_style=False))


if __name__ == "__main__":
    main()
