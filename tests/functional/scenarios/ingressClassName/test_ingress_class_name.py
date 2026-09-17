"""SWAT-59: validates the bring-your-own ingress controller scenario.

When global.ingressClassName is set to a non-default value, the chart must:
- Set spec.ingressClassName on every Ingress to the configured value
- NOT deploy the bundled nginx controller (Deployment, Service, etc.)
- NOT create its own IngressClass resource
- NOT add the kubernetes.io/ingress.class annotation to Ingress resources
- Still install cleanly (Houston pods reach Ready without ingress)
"""

import pytest
from kubernetes import client, config

from tests.utils.k8s import KUBECONFIG_UNIFIED

NAMESPACE = "astronomer"
EXPECTED_INGRESS_CLASS_NAME = "custom-nginx"


@pytest.fixture(scope="module")
def k8s_networking_v1_client() -> client.NetworkingV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.NetworkingV1Api()


@pytest.fixture(scope="module")
def k8s_apps_v1_client_module() -> client.AppsV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def k8s_core_v1_client_module() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


def test_all_ingresses_have_ingress_class_name(k8s_networking_v1_client):
    """Every Ingress in the platform namespace must have spec.ingressClassName set to the configured value."""
    ingresses = k8s_networking_v1_client.list_namespaced_ingress(NAMESPACE).items
    assert ingresses, f"Expected at least one Ingress in namespace {NAMESPACE!r}"

    mismatched = []
    for ingress in ingresses:
        actual = ingress.spec.ingress_class_name
        if actual != EXPECTED_INGRESS_CLASS_NAME:
            mismatched.append(f"  {ingress.metadata.name}: got {actual!r}")

    assert not mismatched, f"Ingresses with incorrect ingressClassName (expected {EXPECTED_INGRESS_CLASS_NAME!r}):\n" + "\n".join(
        mismatched
    )


def test_no_ingress_class_annotation(k8s_networking_v1_client):
    """The deprecated kubernetes.io/ingress.class annotation must not be present on any Ingress."""
    ingresses = k8s_networking_v1_client.list_namespaced_ingress(NAMESPACE).items
    assert ingresses

    annotated = []
    for ingress in ingresses:
        annotations = ingress.metadata.annotations or {}
        if "kubernetes.io/ingress.class" in annotations:
            annotated.append(f"  {ingress.metadata.name}: {annotations['kubernetes.io/ingress.class']!r}")

    assert not annotated, (
        "Ingresses should not have the kubernetes.io/ingress.class annotation "
        "when global.ingressClassName is set:\n" + "\n".join(annotated)
    )


def test_no_ingress_class_resource_created(k8s_networking_v1_client):
    """No chart-created IngressClass resource should exist."""
    ingress_classes = k8s_networking_v1_client.list_ingress_class().items

    chart_created = [ic for ic in ingress_classes if (ic.metadata.labels or {}).get("release") == "astronomer"]
    assert not chart_created, (
        "Found chart-created IngressClass resource(s) -- "
        "global.ingressClassName should suppress IngressClass creation: "
        f"{[ic.metadata.name for ic in chart_created]}"
    )


def test_bundled_nginx_controller_not_deployed(k8s_apps_v1_client_module):
    """The bundled nginx controller Deployment must not exist."""
    deployments = k8s_apps_v1_client_module.list_namespaced_deployment(NAMESPACE).items
    nginx_deployments = [d for d in deployments if "nginx" in d.metadata.name and "elasticsearch" not in d.metadata.name]
    assert not nginx_deployments, (
        "Bundled nginx controller should not be deployed when global.ingressClassName "
        f"is set to a custom value, found: {[d.metadata.name for d in nginx_deployments]}"
    )


def test_houston_pods_are_ready(k8s_core_v1_client_module):
    """Houston pods reach Ready -- the platform installs cleanly without its own ingress controller."""
    pods = k8s_core_v1_client_module.list_namespaced_pod(NAMESPACE, label_selector="component=houston").items
    assert pods, "Expected at least one houston pod"
    ready_pods = [
        p
        for p in pods
        if p.status.phase == "Running" and any(c.ready for c in (p.status.container_statuses or []) if c.name == "houston")
    ]
    assert ready_pods, "Expected at least one houston pod in Running+Ready state"
