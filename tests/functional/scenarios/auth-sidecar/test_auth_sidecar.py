"""PINF-1031: catches the class of regression in PINF-1033 (a PSS-Restricted hardening
change broke global.authSidecar, not caught until QA). See test_profile.yaml for why
this scenario combines authSidecar with a PSS-Restricted-enforcing namespace rather
than testing them separately.
"""

GRAFANA_DEPLOYMENT_NAME = "astronomer-grafana"
NAMESPACE = "astronomer"


def test_grafana_deployment_reaches_ready(k8s_apps_v1_client):
    """
    A pod Pod Security Admission rejects is never created -- it never becomes an
    unhealthy Pod object, it surfaces as a FailedCreate event on the Deployment's
    ReplicaSet. Asserting readyReplicas == spec.replicas (rather than "every visible
    pod is healthy") is what actually catches a rejected auth-proxy container.
    """
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    desired = deployment.spec.replicas
    ready = deployment.status.ready_replicas or 0
    assert ready == desired, (
        f"{GRAFANA_DEPLOYMENT_NAME} has {ready}/{desired} ready replicas. Check for "
        "FailedCreate events on its ReplicaSet -- a pod rejected by Pod Security "
        "Admission never becomes a Pod object, so it shows up as missing, not unhealthy."
    )


def test_grafana_has_auth_proxy_container(k8s_apps_v1_client):
    """Confirms global.authSidecar.enabled actually wired the auth-proxy container into the pod spec."""
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    container_names = [c.name for c in deployment.spec.template.spec.containers]
    assert "auth-proxy" in container_names, f"Expected an auth-proxy container, got: {container_names}"
