"""Test the complete chart for sweeping requirements"""
import jmespath
import pytest

import tests
from tests.chart_tests.helm_template_generator import render_chart


def validate_liveness_probe(config=None):
    if config is None:
        return False
    elif "httpGet" not in config:
        return False
    else:
        return True


def chart_containers():
    k8s_versions_with_all_features = tests.k8s_versions_with_all_features()

    container_configs = {}
    for k8s_version_with_all_feature in k8s_versions_with_all_features:
        docs = render_chart(
            kube_version=k8s_version_with_all_feature["k8s_version"],
            values=k8s_version_with_all_feature["values"]
        )

        # "[?spec.template.spec.containers && kind=='Deployment'].{name: metadata.name, kind: kind, containers: spec.template.spec.containers[*]}",
        specs = jmespath.search(
            "[?spec.template.spec.containers].{name: metadata.name, kind: kind, containers: spec.template.spec.containers[*]}",
            docs,
        )

        for spec in specs:
            name = spec["name"]
            for container in spec["containers"]:
                key = k8s_version_with_all_feature["k8s_version"] + "_" + name + "_" + container["name"]
                container_configs[key] = container

    return container_configs


## TODO: Find a way to just reduce the contents of the probe to a boolean using jmespath
## TODO: Find a way to parametrize these tests so they show up as individual tests, not just TestIngress.test_container_probes[1.16.0]
# TODO: Find a way to show which template the missing probe came from? Not sure if this is super valuable, just trying to give the user more hints as to where to make a fix
## TODO: Find a way to exclude some containers from probes (EG: cronjobs)

class TestIngress:

    @pytest.mark.parametrize(
        "container",
        chart_containers().values(),
        ids=chart_containers().keys()
    )
    def test_container_probes(self, container):
        """Ensure all containers have liveness and readiness probes"""

        assert "livenessProbe" in container
        assert "readinessProbe" in container

        #assert validate_liveness_probe(chart_liveness_probe_config=container["livenessProbe"])
