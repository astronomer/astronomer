#!/usr/bin/env -S uv run --script
"""Generate a mermaid flowchart from a Vector configuration file.

Example:
    grep -v '{{' charts/vector/templates/vector-configmap.yaml | yq -r '.data.["vector-config.yaml"]' > vector-config-sample.yaml
    bin/graph-vector-config.py vector-config-sample.yaml
"""

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pyyaml>=6.0.3",
# ]
# ///
import sys
from pathlib import Path


def load_yaml(filename):
    import yaml

    with open(filename) as f:
        return yaml.safe_load(f)


def load_toml(filename):
    import tomllib

    with open(filename, "rb") as f:
        return tomllib.load(f)


def load_config(filename):
    ext = Path(filename).suffix.lower()
    if ext in [".yaml", ".yml"]:
        return load_yaml(filename)
    if ext == ".toml":
        return load_toml(filename)
    sys.exit("File type not supported. Use a .yaml, .yml, or .toml file.")


def parse_nodes(config):
    nodes = []
    edges = []
    for kind in ("sources", "transforms", "sinks"):
        comps = config.get(kind) or {}
        for name, details in comps.items():
            node_id = f"{name}"
            node_label = f"{kind[:-1].capitalize()}: {details.get('type', '?')} {node_id}"
            nodes.append((node_id, node_label))
            if kind in ("transforms", "sinks"):
                edges.extend((input_name, name) for input_name in details.get("inputs", []))
    return nodes, edges


def generate_mermaid(nodes, edges):
    lines = ["flowchart TD"]
    lines.extend(f'    {node_id}("{label}")' for node_id, label in nodes)
    lines.extend(f"    {src} --> {dst}" for src, dst in edges)
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <vector_config.yaml|yml|toml>")
        sys.exit(1)
    config = load_config(sys.argv[1])
    nodes, edges = parse_nodes(config)
    print(generate_mermaid(nodes, edges))
