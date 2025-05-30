"""
Tests for the unified cluster scenario.
In this scenario, all components (control plane and data plane) are installed in a single cluster.
"""


def test_dummy(unified):
    assert True


# def test_unified_cluster_health(unified, health_check):
#     """Verify that all components are healthy in the unified cluster."""
#     is_healthy, message = health_check()
#     assert is_healthy, message


# def test_unified_components_present(unified):
#     """Verify that both control plane and data plane components are present."""
#     config.load_kube_config(config_file=unified)
#     v1 = client.CoreV1Api()

#     # Get all deployments in astronomer namespace
#     deployments = v1.list_namespaced_deployment(namespace="astronomer")
#     deployment_names = [d.metadata.name for d in deployments.items]

#     # Control plane components that should be present
#     control_components = ["houston", "commander", "registry"]
#     for component in control_components:
#         assert any(component in d for d in deployment_names), f"Control component {component} not found"

#     # Data plane components that should be present
#     data_components = ["scheduler", "webserver", "triggerer"]
#     for component in data_components:
#         assert any(component in d for d in deployment_names), f"Data component {component} not found"


# def test_unified_networking(unified):
#     """Verify that networking is properly configured in unified mode."""
#     config.load_kube_config(config_file=unified)
#     v1 = client.CoreV1Api()

#     # Check that services exist and have endpoints
#     services = v1.list_namespaced_service(namespace="astronomer")
#     endpoints = v1.list_namespaced_endpoints(namespace="astronomer")

#     service_names = [s.metadata.name for s in services.items]
#     endpoint_names = [e.metadata.name for e in endpoints.items]

#     # Required services
#     required_services = ["houston", "registry", "webserver"]
#     for service in required_services:
#         assert any(service in s for s in service_names), f"Service {service} not found"
#         assert any(service in e for e in endpoint_names), f"Endpoint for {service} not found"


# def test_unified_storage(unified):
#     """Verify that storage is properly configured."""
#     config.load_kube_config(config_file=unified)
#     v1 = client.CoreV1Api()

#     # Check PVCs
#     pvcs = v1.list_namespaced_persistent_volume_claim(namespace="astronomer")
#     pvc_names = [p.metadata.name for p in pvcs.items]

#     # Required PVCs
#     required_pvcs = ["registry", "logs"]
#     for pvc in required_pvcs:
#         assert any(pvc in p for p in pvc_names), f"PVC {pvc} not found"

#     # Check that PVCs are bound
#     for pvc in pvcs.items:
#         assert pvc.status.phase == "Bound", f"PVC {pvc.metadata.name} is not bound"
