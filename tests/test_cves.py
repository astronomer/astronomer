from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_log4shell(kube_version):
    """Ensure remediation settings are in place for log4j log4shell CVE-2021-44228"""
    docs = render_chart(
        kube_version=kube_version,
        show_only=[
            "charts/elasticsearch/templates/client/es-client-deployment.yaml",
            "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
            "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
        ],
    )
    # Assert that all containers have an env var ES_JAVA_OPTS that includes the string -Dlog4j2.formatMsgNoLookups=true
    assert all(
        "-Dlog4j2.formatMsgNoLookups=true" in env_var["value"]
        for doc in docs
        for c in doc["spec"]["template"]["spec"]["containers"]
        for env_var in c["env"]
        if env_var["name"] == "ES_JAVA_OPTS"
    )
