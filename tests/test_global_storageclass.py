from tests.helm_template_generator import render_chart
import pytest

chart_files = [
    "charts/alertmanager/templates/alertmanager-statefulset.yaml",
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
    "charts/prometheus/templates/prometheus-statefulset.yaml",
    "charts/astronomer/templates/registry/registry-statefulset.yaml",
]


@pytest.mark.parametrize(
    "supported_types, expected_output", [("-", ""), ("vishnure", "vishnure")]
)
def test_global_storageclass(supported_types, expected_output):
    """Test globalstorageclass feature of alertmanager statefulset template"""
    docs = render_chart(
        values={"global": {"storageClass": supported_types}},
        show_only=chart_files,
    )
    assert len(docs) == 5
    doc = docs[0]
    assert (
        doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"]
        == expected_output
    )
