from pathlib import Path

import yaml

from tests.chart_tests.helm_template_generator import render_chart


def get_all_features():
    return yaml.safe_load((Path(__file__).parent.parent / "enable_all_features.yaml").read_text())


def get_chart_containers(k8s_version, chart_values, ignore_kind_list=None) -> dict:
    """Return a dict of pod specs in the form of {k8s_version}_{release_name}-{pod_name}_{container_name}, with some additional metadata."""
    if ignore_kind_list is None:
        ignore_kind_list = []

    docs = render_chart(
        kube_version=k8s_version,
        values=chart_values,
    )

    specs = [
        {
            "name": doc.get("metadata", {}).get("name"),
            "kind": doc.get("kind"),
            "containers": doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []),
        }
        for doc in docs
        if "spec" in doc
        and "template" in doc["spec"]
        and "spec" in doc["spec"]["template"]
        and "containers" in doc["spec"]["template"]["spec"]
    ]

    ignore_kind_list = [ignore_kind.lower() for ignore_kind in ignore_kind_list]

    return {
        f"{k8s_version}_{spec['name']}_{container['name']}": {
            **container,
            "key": f"{k8s_version}_{spec['name']}_{container['name']}",
            "kind": spec["kind"],
        }
        for spec in specs
        if spec["kind"].lower() not in ignore_kind_list
        for container in spec["containers"]
    }
