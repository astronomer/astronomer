import yaml

from tests.chart_tests.helm_template_generator import render_chart
from tests import git_root_dir


def get_all_features():
    return yaml.safe_load((git_root_dir / "tests" / "enable_all_features.yaml").read_text())


def get_chart_containers(
    k8s_version: str,
    chart_values: dict,
    *,  # force the remaining arguments to be keyword-only
    exclude_kinds: list[str] | None = None,
    include_kinds: list[str] | None = None,
) -> dict:
    """Return a dict of pod container and initContainer specs in the form of
    {k8s_version}_{release_name}-{pod_name}_{container_name}, with some additional metadata."""

    docs = render_chart(
        kube_version=k8s_version,
        values=chart_values,
    )

    specs = [
        {
            "name": doc.get("metadata", {}).get("name"),
            "kind": doc.get("kind"),
            "containers": doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []),
            "initContainers": doc.get("spec", {}).get("template", {}).get("spec", {}).get("initContainers", []),
        }
        for doc in docs
        if "spec" in doc
        and "template" in doc["spec"]
        and "spec" in doc["spec"]["template"]
        and ("containers" in doc["spec"]["template"]["spec"] or "initContainers" in doc["spec"]["template"]["spec"])
    ]

    if exclude_kinds:
        exclude_kinds = [kind.lower() for kind in exclude_kinds]
        specs = [spec for spec in specs if spec["kind"].lower() not in exclude_kinds]

    if include_kinds:
        include_kinds = [kind.lower() for kind in include_kinds]
        specs = [spec for spec in specs if spec["kind"].lower() in include_kinds]

    return {
        f"{k8s_version}_{spec['name']}_{container['name']}": {
            **container,
            "key": f"{k8s_version}_{spec['name']}_{container['name']}",
            "kind": spec["kind"],
        }
        for spec in specs
        for container in [*spec["containers"], *spec["initContainers"]]
    }
