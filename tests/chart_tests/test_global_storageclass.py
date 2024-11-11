from tests.chart_tests.helm_template_generator import render_chart
import pytest
import jmespath

chart_files = [
    "charts/alertmanager/templates/alertmanager-statefulset.yaml",
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
    "charts/prometheus/templates/prometheus-statefulset.yaml",
    "charts/astronomer/templates/registry/registry-statefulset.yaml",
]

supported_types = [("-", ""), ("astrosc", "astrosc")]


@pytest.mark.parametrize(
    "supported_types, expected_output",
    supported_types,
    ids=[x[0] for x in supported_types],
)
def test_global_storageclass(supported_types, expected_output):
    """Test globalstorageclass feature of alertmanager statefulset template."""
    docs = render_chart(
        values={"global": {"storageClass": supported_types}},
        show_only=chart_files,
    )
    assert len(docs) == 5

    assert all(
        expected_output in storageClassNames
        for storageClassNames in jmespath.search("[*].spec.volumeClaimTemplates[*].spec.storageClassName", docs)
    )

def test_component_storageclass_precendence():
    """Test component storageclass takes priority over global storageclass"""
    values = {
        "global"        : {"storageClass": "gp1"},
        "alertmanager"  : {"persistence" : {"storageClassName": "gp2"}},
        "elasticsearch" : {"common"      : {"persistence":{"storageClassName": "gp2"}}},
        "prometheus"    : {"persistence" : {"storageClassName": "gp2"}},
        "astronomer"    :  {"registry"   : {"persistence":{"storageClassName": "gp2"}}}
    }
    docs = render_chart(
        values=values,
        show_only=chart_files,
    )

    assert len(docs) == 5
    assert all("gp2" in storageClassNames
    for storageClassNames in jmespath.search("[].spec.volumeClaimTemplates[].spec.storageClassName", docs))
