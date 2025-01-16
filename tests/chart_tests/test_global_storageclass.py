from tests.chart_tests.helm_template_generator import render_chart
import pytest

# Test data structure with chart files and expected storage class names
parametrization_data = (
    ("charts/alertmanager/templates/alertmanager-statefulset.yaml", "astrosc"),
    ("charts/elasticsearch/templates/master/es-master-statefulset.yaml", "astrosc"),
    ("charts/elasticsearch/templates/data/es-data-statefulset.yaml", "astrosc"),
    ("charts/prometheus/templates/prometheus-statefulset.yaml", "astrosc"),
    ("charts/astronomer/templates/registry/registry-statefulset.yaml", None),  # Registry should use direct access
)


@pytest.mark.parametrize("chart_file, expected_sc_name", parametrization_data, ids=[x[0] for x in parametrization_data])
def test_global_storageclass(chart_file, expected_sc_name):
    """Test global storageclass feature of alertmanager statefulset template."""
    docs = render_chart(
        values={"global": {"storageClass": expected_sc_name}},
        show_only=[chart_file],
    )

    # Assert that one document is rendered
    assert len(docs) == 1  # Expecting one document per chart file

    # Since docs[0] is already a dictionary, we can directly access the fields
    statefulset_doc = docs[0]

    # Determine if we're dealing with the registry chart or another chart
    if chart_file == "charts/astronomer/templates/registry/registry-statefulset.yaml":
        # Registry chart has the storageClassName directly in the statefulset
        storage_class_name = statefulset_doc["storageClassName"]
    else:
        # Other charts have the storageClassName inside volumeClaimTemplates
        storage_class_name = statefulset_doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"]

    # Assert that the storageClassName matches the expected one
    assert storage_class_name == expected_sc_name


def test_component_storageclass_precendence():
    """Test component storageclass takes priority over global storageclass"""
    values = {
        "global": {"storageClass": "gp1"},
        "alertmanager": {"persistence": {"storageClassName": "gp2"}},
        "elasticsearch": {"common": {"persistence": {"storageClassName": "gp2"}}},
        "prometheus": {"persistence": {"storageClassName": "gp2"}},
        "astronomer": {"registry": {"persistence": {"storageClassName": "gp2"}}},
    }

    docs = render_chart(
        values=values,
        show_only=[chart_file for chart_file, _ in parametrization_data],
    )
    assert len(docs) == 5

    for chart_file, doc in zip([x[0] for x in parametrization_data], docs):
        doc = doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"]
        assert "gp2" in doc
