from tests.helm_template_generator import render_chart
import pytest

chart_files = [
    "charts/alertmanager/templates/alertmanager-statefulset.yaml",
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
    "charts/prometheus/templates/prometheus-statefulset.yaml",
    "charts/astronomer/templates/registry/registry-statefulset.yaml",
]
doc_ids = [x.split("/")[-1] for x in chart_files]


@pytest.mark.parametrize(
    "supported_types, expected_output", [("-", ""), ("astrosc", "astrosc")]
)
@pytest.mark.parametrize("chart", chart_files, ids=doc_ids)
def test_global_storageclass(supported_types, expected_output, chart):
    """Test globalstorageclass feature of alertmanager statefulset template"""
    docs = render_chart(
        values={"global": {"storageClass": supported_types}},
        show_only=[chart],
    )
    assert len(docs) == 1

    doc = docs[0]
    assert (
        doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"]
        == expected_output
    )
