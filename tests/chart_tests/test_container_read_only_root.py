import re

import pytest

from tests.utils import get_all_features, get_containers_by_name
from tests.utils.chart import render_chart

annotation_validator = re.compile("^([^/]+/)?(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])$")
pod_managers = ["Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job"]

# This should contain a list of pod name substrings that have been completed in ticket
# https://github.com/astronomer/issues/issues/7394
# This should match tests/functional/unified/test_container_read_only_root.py
read_only_root_pods = [
    "alertmanager",
    "commander",
    "configmap-reloader",
    "cp-nginx",
    "default-backend",
    "dp-nginx",
    "elasticsearch-client",
    "elasticsearch-exporter",
    "jetstream",
    "kibana",
    "kube-state",
    "nats",
    "prometheus",
    "registry",
]


class TestAllContainersReadOnlyRoot:
    chart_values = get_all_features()
    # We disable authSidecar during development of #7394 until that feature is supported
    chart_values["global"]["authSidecar"] = {"enabled": False}
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
            if any(x in param_id for x in read_only_root_pods):
                assert container["securityContext"].get("readOnlyRootFilesystem")
            else:
                # This assertion ensures that this test is updated whenever we change this property
                assert not container.get("securityContext", {}).get("readOnlyRootFilesystem")
