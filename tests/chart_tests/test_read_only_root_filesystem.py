import re

import pytest
import yaml
from deepmerge import always_merger

from tests import git_root_dir
from tests.utils import get_all_features, get_containers_by_name, get_pod_template
from tests.utils.chart import render_chart

annotation_validator = re.compile("^([^/]+/)?(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])$")
pod_managers = ["Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job"]


class TestAllContainersReadOnlyRoot:
    """Set up a test scenario that ensures all containers have a custom configuration with readOnlyRootFilesystem: False, but the
    result is that readOnlyRootFilesystem is still true.

    Some containers do not allow overriding securityContext, so we exclude those explicitly.
    """

    containers_without_security_context_overrides = [
        "CronJob/release-name-elasticsearch-curator",
        "DaemonSet/release-name-containerd-ca-update",
        "DaemonSet/release-name-private-ca",
        "Deployment/release-name-elasticsearch-client",
        "Deployment/release-name-elasticsearch-exporter",
        "Deployment/release-name-elasticsearch-nginx",
        "StatefulSet/release-name-elasticsearch-data",
        "StatefulSet/release-name-elasticsearch-master",
        "StatefulSet/release-name-postgresql-master",
        "StatefulSet/release-name-postgresql-slave",
        "StatefulSet/release-name-prometheus",
    ]

    overrides = yaml.safe_load(
        ((git_root_dir) / "tests" / "chart_tests" / "test_data" / "secrity_context_overrides.yaml").read_text()
    )

    chart_values = always_merger.merge(get_all_features(), overrides)

    default_docs = render_chart(values=chart_values)
    pod_manager_docs = [doc for doc in default_docs if doc["kind"] in pod_managers]

    @pytest.mark.parametrize(
        "doc",
        pod_manager_docs,
        ids=[f"{x['kind']}/{x['metadata']['name']}" for x in pod_manager_docs],
    )
    def test_all_containers_have_read_only_root(self, doc, request):
        """Test that every container matches our expected configs for ticket https://github.com/astronomer/issues/issues/7394."""
        param_id = request.node.callspec.id
        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        for container in c_by_name.values():
            assert container.get("securityContext", {}).get("readOnlyRootFilesystem"), (
                f"{container['name']} {param_id} does not have RORFS"
            )

            if f"{doc['kind']}/{doc['metadata']['name']}" not in self.containers_without_security_context_overrides:
                assert container.get("securityContext").get("dummy_key") == "dummy_value"


class TestHoustonPodManagers:
    chart_values = get_all_features()
    templates = [str(x.relative_to(git_root_dir)) for x in (git_root_dir / "charts/astronomer/templates/houston").rglob("*.yaml")]
    docs = render_chart(values=chart_values, show_only=templates)
    pod_manager_docs = [x for x in docs if x["kind"] in pod_managers]

    @pytest.mark.parametrize(
        "pod_manager_doc",
        pod_manager_docs,
        ids=[f"{x.get('kind', '')}/{x['metadata']['name']}" for x in pod_manager_docs],
    )
    def test_houston_pods_read_only_root_filesysystem_settings(self, pod_manager_doc):
        """Test that Houston pod manager docs have the correct read-only root filesystem settings."""
        pod_name = pod_manager_doc["metadata"]["name"].removeprefix("release-name-")
        pod_template = get_pod_template(pod_manager_doc, include_init_containers=True)
        assert {"emptyDir": {}, "name": "etc-ssl-certs"} in pod_template["spec"]["volumes"]
        assert {"emptyDir": {}, "name": "tmp"} in pod_template["spec"]["volumes"]
        for container in pod_template["spec"]["containers"] + pod_template["spec"]["initContainers"]:
            assert container["securityContext"].get("readOnlyRootFilesystem"), (
                f"{pod_name}/{container['name']} missing readOnlyRootFilesystem"
            )
            match container["name"]:
                case "etc-ssl-certs-copier":
                    assert container["volumeMounts"] == [{"name": "etc-ssl-certs", "mountPath": "/etc/ssl/certs_copy"}], (
                        f"{pod_name}/{container['name']} etc-ssl-certs-copier mounts are wrong"
                    )
                case "wait-for-db":
                    assert {"mountPath": "/etc/ssl/certs", "name": "etc-ssl-certs"} in container["volumeMounts"], (
                        f"{pod_name}/{container['name']} missing mount: /etc/ssl/certs"
                    )
                    assert {"mountPath": "/tmp", "name": "tmp"} not in container["volumeMounts"], (
                        f"{pod_name}/{container['name']} unnecessary mount: /tmp"
                    )
                    assert {"mountPath": "/houston/node_modules/.cache", "name": "tmp"} not in container["volumeMounts"], (
                        f"{pod_name}/{container['name']} unnecessary mount: /houston/node_modules/.cache"
                    )
                case _:
                    assert {"mountPath": "/tmp", "name": "tmp"} in container["volumeMounts"], (
                        f"{pod_name}/{container['name']} missing mount: /tmp"
                    )
                    assert {"mountPath": "/houston/node_modules/.cache", "name": "tmp"} in container["volumeMounts"], (
                        f"{pod_name}/{container['name']} missing mount: /houston/node_modules/.cache"
                    )
                    assert {"mountPath": "/etc/ssl/certs", "name": "etc-ssl-certs"} in container["volumeMounts"], (
                        f"{pod_name}/{container['name']} missing mount: /etc/ssl/certs"
                    )
