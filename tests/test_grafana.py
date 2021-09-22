from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath
import yaml


def yd(thing):
    """Dump a python object as yaml. Useful for debugging."""
    print(yaml.safe_dump(thing))


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_grafana_dashboard_velero_disabled(kube_version):
    """Test that the velero dashboard shows up when velero is enabled."""
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"veleroEnabled": False}},
        show_only=[
            "charts/grafana/templates/grafana-configmap.yaml",
            "charts/grafana/templates/grafana-deployment.yaml",
        ],
    )

    assert len(docs) == 2
    assert len(jmespath.search('[*].data."velero.json"', docs)) == 0
    assert (
        len(
            jmespath.search(
                "[].spec.template.spec.containers[].volumeMounts[?subPath=='velero.json']",
                docs,
            )[0]
        )
        == 0
    )


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_grafana_dashboard_velero_enabled(kube_version):
    """Test that the velero dashboard shows up when velero is enabled."""
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"veleroEnabled": True}},
        show_only=[
            "charts/grafana/templates/grafana-configmap.yaml",
            "charts/grafana/templates/grafana-deployment.yaml",
        ],
    )

    assert len(docs) == 3
    assert len(jmespath.search('[*].data."velero.json"', docs)) == 1
    assert (
        len(
            jmespath.search(
                "[].spec.template.spec.containers[].volumeMounts[?subPath=='velero.json']",
                docs,
            )[0]
        )
        == 1
    )
