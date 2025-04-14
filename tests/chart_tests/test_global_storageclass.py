from tests.chart_tests.helm_template_generator import render_chart

# Test data structure with chart files and expected storage class names
parametrization_data = (
    ("charts/elasticsearch/templates/master/es-master-statefulset.yaml", "astrosc"),
    ("charts/elasticsearch/templates/data/es-data-statefulset.yaml", "astrosc"),
    ("charts/prometheus/templates/prometheus-statefulset.yaml", "astrosc"),
    ("charts/astronomer/templates/registry/registry-statefulset.yaml", None),  # Registry should use direct access
)


def test_component_storageclass_precendence():
    """Test component storageclass takes priority over global storageclass"""
    values = {
        "global": {"storageClass": "gp1"},
        "elasticsearch": {"common": {"persistence": {"storageClassName": "gp2"}}},
        "prometheus": {"persistence": {"storageClassName": "gp2"}},
        "astronomer": {"registry": {"persistence": {"storageClassName": "gp2"}}},
    }

    docs = render_chart(
        values=values,
        show_only=[chart_file for chart_file, _ in parametrization_data],
    )
    assert len(docs) == 4

    for chart_file, doc in zip([x[0] for x in parametrization_data], docs):
        doc = doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"]
        assert "gp2" in doc
