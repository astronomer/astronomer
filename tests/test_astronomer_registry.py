from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath


statefulsets = [
    {
        "show_only": "charts/alertmanager/templates/alertmanager-statefulset.yaml",
        "name": "alertmanager",
        "docker_images": ["quay.io/astronomer/ap-alertmanager:"],
    },
    {
        "show_only": "charts/astronomer/templates/registry/registry-statefulset.yaml",
        "name": "registry",
        "docker_images": ["quay.io/astronomer/ap-registry:"],
    },
    {
        "show_only": "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
        "name": "elasticsearch-data",
        "docker_images": ["quay.io/astronomer/ap-elasticsearch:"],
    },
    {
        "show_only": "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
        "name": "elasticsearch-master",
        "docker_images": ["quay.io/astronomer/ap-elasticsearch:"],
    },
    {
        "show_only": "charts/nats/templates/statefulset.yaml",
        "name": "nats",
        "docker_images": [
            "quay.io/astronomer/ap-nats-server:",
            "quay.io/astronomer/ap-nats-exporter:",
        ],
        "values": {"postgres": {"replication": {"enabled": True}}},
    },
    {
        "show_only": "charts/postgresql/templates/statefulset-slaves.yaml",
        "name": "postgresql",
        "docker_images": ["quay.io/astronomer/ap-postgresql:"],
    },
    {
        "show_only": "charts/postgresql/templates/statefulset.yaml",
        "name": "postgresql",
        "docker_images": ["quay.io/astronomer/ap-postgresql:"],
    },
    {
        "show_only": "charts/prometheus/templates/prometheus-statefulset.yaml",
        "name": "prometheus",
        "docker_images": ["quay.io/astronomer/ap-prometheus:"],
    },
    {
        "show_only": "charts/stan/templates/statefulset.yaml",
        "name": "stan",
        "docker_images": ["quay.io/astronomer/ap-stan:"],
    },
]
sts_ids = [x["name"] for x in statefulsets]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
@pytest.mark.parametrize("template", statefulsets, ids=sts_ids)
def test_all_statefulsets(kube_version, template):
    """Test that all statefulsets have correct common values."""

    docs = render_chart(
        kube_version=kube_version,
        show_only=[template["show_only"]],
        values=template.get("values"),
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == f"RELEASE-NAME-{template['name']}"
    # if "quay.io/astronomer/ap-nats:" in template["docker_images"]:
    #     # breakpoint()
    assert any(
        image in item
        for item in jmespath.search("spec.template.spec.containers[*].image", doc)
        for image in template["docker_images"]
    )


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_registry_statefulset(kube_version):
    """Test that helm renders a good statefulset template for astronomer registry."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-registry"
    assert any(
        "quay.io/astronomer/ap-registry:" in item
        for item in jmespath.search("spec.template.spec.containers[*].image", doc)
    )
