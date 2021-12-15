from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
from . import git_root_dir

show_only = [
    str(path.relative_to(git_root_dir))
    for path in git_root_dir.rglob("charts/**/*")
    if "pod-disruption-budget" in str(path)
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_pod_disruption_budgets_default(kube_version):
    """Validate that default PodDisruptionBudget configs use latest available API version."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=show_only,
        values={"global": {"prometheusPostgresExporterEnabled": True}},
    )
    _, minor, _ = (int(x) for x in kube_version.split("."))

    if minor < 21:
        assert all(x["apiVersion"] == "policy/v1beta1" for x in docs)
    else:
        assert all(x["apiVersion"] == "policy/v1" for x in docs)


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_pod_disruption_budgets_use_legacy(kube_version):
    """Allow global.useLegacyPodDisruptionBudget to use policy/v1beta1 until k8s 1.25.0"""
    docs = render_chart(
        kube_version=kube_version,
        show_only=show_only,
        values={
            "global": {
                "prometheusPostgresExporterEnabled": True,
                "useLegacyPodDisruptionBudget": True,
            }
        },
    )
    _, minor, _ = (int(x) for x in kube_version.split("."))

    if minor < 25:
        assert all(x["apiVersion"] == "policy/v1beta1" for x in docs)
    else:
        assert ValueError("policy/v1beta1 is not supported in k8s 1.25+")
