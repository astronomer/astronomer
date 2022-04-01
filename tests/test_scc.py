# These tests do not cover templates/scc/astronomer-scc-anyuid.yaml because the
# contents of that file are not included in the k8s schema we use for validating
# k8s manifests. See https://github.com/astronomer/issues/issues/3887

from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import yaml


show_only = [
    "charts/astronomer/templates/commander/commander-role.yaml",
    "charts/astronomer/templates/houston/houston-configmap.yaml",
]


commander_expected_result = {
    "apiGroups": ["security.openshift.io"],
    "resources": ["securitycontextconstraints"],
    "verbs": ["create", "delete", "list", "watch"],
}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_scc_disabled(kube_version):
    """
    Test all things scc related when scc is disabled.
    """
    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "sccEnabled": False,
                "features": {"namespacePools": {"enabled": False}},
            }
        },
        show_only=show_only,
    )
    houston_values = yaml.safe_load(docs[1]["data"]["production.yaml"])

    assert len(docs) == 2
    assert commander_expected_result not in docs[0]["rules"]
    assert houston_values["deployments"]["helm"].get("sccEnabled") is None


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_scc_enabled(kube_version):
    """
    Test all things scc related when scc is disabled.
    """

    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "sccEnabled": True,
                "clusterRoles": True,
                "features": {
                    "namespacePools": {"enabled": False},
                },
            }
        },
        show_only=show_only,
    )
    houston_values = yaml.safe_load(docs[1]["data"]["production.yaml"])

    assert len(docs) == 2
    assert commander_expected_result in docs[0]["rules"]
    assert houston_values["deployments"]["helm"]["sccEnabled"] is True
