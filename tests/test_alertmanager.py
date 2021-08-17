from tests.helm_template_generator import render_chart
import jmespath
import pytest


def test_alertmanager_defaults():
    """Test that alertmanager chart looks sane with defaults"""
    docs = render_chart(
        show_only=["charts/alertmanager/templates/alertmanager-statefulset.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]

    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-alertmanager"
    assert doc["spec"]["template"]["spec"]["securityContext"]["fsGroup"] == 65534

    # rfc1918 configs should be absent from default settings
    assert (
        any(
            "--cluster.advertise-address=" in arg
            for args in jmespath.search("spec.template.spec.containers[*].args", doc)
            for arg in args
        )
        is False
    )
    assert [
        value
        for item in jmespath.search(
            "spec.template.spec.containers[*].env[?name == 'POD_IP'].valueFrom.fieldRef.fieldPath",
            doc,
        )
        for value in item
    ] == []


def test_alertmanager_rfc1918():
    """Test rfc1918 features of alertmanager template"""
    docs = render_chart(
        values={"alertmanager": {"enableNonRFC1918": True}},
        show_only=["charts/alertmanager/templates/alertmanager-statefulset.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]

    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-alertmanager"
    assert doc["spec"]["template"]["spec"]["securityContext"]["fsGroup"] == 65534

    assert any(
        "--cluster.advertise-address=" in arg
        for args in jmespath.search("spec.template.spec.containers[*].args", doc)
        for arg in args
    )
    assert all(
        value
        for item in jmespath.search(
            "spec.template.spec.containers[*].env[?name == 'POD_IP'].valueFrom.fieldRef.fieldPath",
            doc,
        )
        for value in item
    )


supported_global_storage_options = ["-", "astrosc"]


@pytest.mark.parametrize(
    "supported_types",
    supported_global_storage_options,
)
def test_alertmanager_global_storageclass(supported_types):
    """Test globalstorageclass feature of alertmanager statefulset template"""
    docs = render_chart(
        values={"global": {"storageClass": supported_types}},
        show_only=["charts/alertmanager/templates/alertmanager-statefulset.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    print(supported_types)
    if supported_types == "-":
        assert doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"] == ""

    if supported_types == "astrosc":
        assert (
            doc["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"]
            == "astrosc"
        )
