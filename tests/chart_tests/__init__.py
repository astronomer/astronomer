from pathlib import Path

import jmespath
import yaml

from tests.chart_tests.helm_template_generator import render_chart


def get_all_features():
    return yaml.safe_load(
        (Path(__file__).parent.parent / "enable_all_features.yaml").read_text()
    )


def get_chart_containers(k8s_version, chart_values, ignore_kind_list=None) -> dict:
    """Return a dict of pod specs in the form of {k8s_version}_{release_name}-{pod_name}_{container_name}, with some additional metadata."""
    if ignore_kind_list is None:
        ignore_kind_list = []
    docs = render_chart(
        kube_version=k8s_version,
        values=chart_values,
    )

    specs = jmespath.search(
        "[?spec.template.spec.containers].{name: metadata.name, kind: kind, containers: spec.template.spec.containers[*]}",
        docs,
    )

    container_spec = {}
    ignore_kind_list = [ignore_kind.lower() for ignore_kind in ignore_kind_list]
    for spec in specs:
        kind = spec["kind"]
        if kind.lower() not in ignore_kind_list:
            name = spec["name"]
            for container in spec["containers"]:
                key = f"{k8s_version}_{name}_" + container["name"]
                container["key"] = key
                container["kind"] = kind
                container_spec[key] = container

    return container_spec
