from pathlib import Path

import jmespath
import yaml

from tests.chart_tests.helm_template_generator import render_chart


def get_all_features():
    return yaml.safe_load(
        (Path(__file__).parent.parent / "enable_all_features.yaml").read_text()
    )


def get_chart_containers(k8s_version, chart_values, ignore_kind_list=[]):
    docs = render_chart(
        kube_version=k8s_version,
        values=chart_values,
    )

    specs = jmespath.search(
        "[?spec.template.spec.containers].{name: metadata.name, kind: kind, containers: spec.template.spec.containers[*]}",
        docs,
    )

    container_configs = {}
    ignore_kind_list = [ignore_kind.lower() for ignore_kind in ignore_kind_list]
    for spec in specs:
        if spec["kind"].lower() not in ignore_kind_list:
            name = spec["name"]
            for container in spec["containers"]:
                key = k8s_version + "_" + name + "_" + container["name"]
                container_configs[key] = container

    return container_configs
