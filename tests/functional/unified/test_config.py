import json
import time
from os import getenv
from subprocess import check_output

import pytest
import testinfra
import yaml
from kubernetes.client.rest import ApiException


def test_ensure_not_running(k8s_core_v1_client):
    """Ensure that the listed pods are not running."""
    pods = k8s_core_v1_client.list_namespaced_pod("astronomer")
    should_not_be_running = ["prometheus-postgres-exporter"]
    for pod in pods.items:
        for feature in should_not_be_running:
            if feature in pod.metadata.name:
                raise ValueError(f"Expected '{feature}' to be disabled")


def test_prometheus_user(prometheus):
    """Ensure user is 'nobody'."""
    user = prometheus.check_output("whoami")
    assert user == "nobody", f"Expected prometheus to be running as 'nobody', not '{user}'"


def test_houston_config(houston_api):
    """Make assertions about Houston's configuration."""
    data = houston_api.check_output("echo \"config = require('config'); console.log(JSON.stringify(config))\" | node -")
    houston_config = json.loads(data)
    assert "url" not in houston_config["nats"].keys(), (
        f"Did not expect to find 'url' configured for 'nats'. Found:\n\n{houston_config['nats']}"
    )
    assert len(houston_config["nats"]["servers"]), (
        f"Expected to find 'servers' configured for 'nats'. Found:\n\n{houston_config['nats']}"
    )
    for server in houston_config["nats"]:
        assert "localhost" not in server, (
            f"Expected not to find 'localhost' in the 'servers' configuration. Found:\n\n{houston_config['nats']}"
        )


def test_houston_check_db_info(houston_api):
    """Make assertions about Houston's configuration."""
    if not (release_name := getenv("RELEASE_NAME")):
        print("No release_name env var, using release_name=astronomer")
        release_name = "astronomer"

    houston_db_info = houston_api.check_output("env | grep DATABASE_URL")
    assert f"{release_name}_houston" in houston_db_info


def test_grafana_check_db_info(grafana):
    """Make assertions about Houston's configuration."""
    if not (release_name := getenv("RELEASE_NAME")):
        print("No release_name env var, using release_name=astronomer")
        release_name = "astronomer"

    grafana_db_info = grafana.check_output("env | grep GF_DATABASE_URL")
    assert f"{release_name}_grafana" in grafana_db_info


@pytest.mark.flaky(reruns=20, reruns_delay=10)
def test_houston_can_reach_prometheus(houston_api):
    assert houston_api.check_output("wget --timeout=5 -qO- http://astronomer-prometheus.astronomer.svc.cluster.local:9090/targets")


# def test_nginx_can_reach_default_backend(cp_nginx):
#     assert cp_nginx.check_output("curl -s --max-time 1 http://astronomer-nginx-default-backend:8080")


def test_nginx_ssl_cache(cp_nginx):
    """Ensure nginx default ssl cache size is 10m."""
    assert "ssl_session_cache shared:SSL:10m;" == cp_nginx.check_output("grep ssl_session_cache nginx.conf").replace("\t", "")

# Commenting only for RC1, will be adding this back: https://github.com/astronomer/ap-vendor/pull/1145
# def test_nginx_capabilities(cp_nginx):
#     """Ensure nginx has no getcap capabilities"""
#     assert cp_nginx.check_output("getcap /nginx-ingress-controller").replace("\t", "") == "/nginx-ingress-controller ="
#     assert cp_nginx.check_output("getcap /usr/local/nginx/sbin/nginx").replace("\t", "") == "/usr/local/nginx/sbin/nginx ="
#     assert cp_nginx.check_output("getcap /usr/bin/dumb-init").replace("\t", "") == "/usr/bin/dumb-init ="


@pytest.mark.flaky(reruns=20, reruns_delay=10)
def test_prometheus_targets(prometheus):
    """Ensure all Prometheus targets are healthy."""
    data = prometheus.check_output("wget --timeout=5 -qO- http://localhost:9090/api/v1/targets")
    targets = json.loads(data)["data"]["activeTargets"]
    for target in targets:
        assert target["health"] == "up", (
            "Expected all prometheus targets to be up. "
            + 'Please check the "targets" view in the Prometheus UI'
            + f" Target data from the one that is not up:\n\n{target}"
        )


@pytest.mark.flaky(reruns=20, reruns_delay=10)
def test_houston_metrics_are_collected(prometheus):
    """Ensure Houston metrics are collected and prefixed with 'houston_'."""
    data = prometheus.check_output("wget --timeout=5 -qO- http://localhost:9090/api/v1/query?query=houston_up")
    parsed = json.loads(data)
    assert len(parsed["data"]["result"]) > 0, f"Expected to find a metric houston_up, but we got this response:\n\n{parsed}"


def test_prometheus_config_reloader_works(prometheus, k8s_core_v1_client):
    """Ensure that Prometheus reloads its config when the cofigMap is updated
    and the reloader sidecar triggers the reload."""
    # define new value we'll use for the config change
    new_scrape_interval = "31s"

    # get the current configmap
    orig_cm = k8s_core_v1_client.read_namespaced_config_map("astronomer-prometheus-config", "astronomer")

    prom_config = yaml.safe_load(orig_cm.data["config"])
    # modify the configmap
    prom_config["global"]["scrape_interval"] = new_scrape_interval
    new_body = {
        "apiversion": "v1",
        "kind": "ConfigMap",
        "data": {"config": yaml.dump(prom_config)},
    }

    try:
        # update the configmap
        k8s_core_v1_client.patch_namespaced_config_map(name="astronomer-prometheus-config", namespace="astronomer", body=new_body)
    except ApiException as e:
        print(f"Exception when calling CoreV1Api->patch_namespaced_config_map: {e}\n")

    # This can take more than a minute.
    for _ in range(12):
        data = prometheus.check_output("wget --timeout=5 -qO- http://localhost:9090/api/v1/status/config")
        j_parsed = json.loads(data)
        y_parsed = yaml.safe_load(j_parsed["data"]["yaml"])
        if y_parsed["global"]["scrape_interval"] != "30s":
            break
        time.sleep(10)

    # set the config back to it's original settings
    prom_config["global"]["scrape_interval"] = "30s"
    new_body = {
        "apiversion": "v1",
        "kind": "ConfigMap",
        "data": {"config": yaml.dump(prom_config)},
    }

    try:
        # update the configmap
        k8s_core_v1_client.patch_namespaced_config_map(name="astronomer-prometheus-config", namespace="astronomer", body=new_body)
    except ApiException as e:
        print(f"Exception when calling CoreV1Api->patch_namespaced_config_map: {e}\n")

    assert y_parsed["global"]["scrape_interval"] != "30s", "Expected the prometheus config file to change"


@pytest.mark.skipif(
    not getenv("HELM_CHART_PATH"),
    reason="This test only works with HELM_CHART_PATH set to the path of the chart to be tested",
)
def test_houston_backend_secret_present_after_helm_upgrade_and_container_restart(houston_api, k8s_core_v1_client):
    """Test when helm upgrade occurs without Houston pods restarting that a
    Houston container restart will not miss the Houston connection backend
    secret.

    Regression test for:
    https://github.com/astronomer/issues/issues/2251
    """
    helm_chart_path = getenv("HELM_CHART_PATH")

    if not (namespace := getenv("NAMESPACE")):
        print("No NAMESPACE env var, using NAMESPACE=astronomer")
        namespace = "astronomer"

    if not (release_name := getenv("RELEASE_NAME")):
        print("No release_name env var, using release_name=astronomer")
        release_name = "astronomer"

    # Attempt downgrade with the documented procedure.
    # Run the command twice to ensure the most recent change is a no-operation change
    command = f"helm upgrade --reuse-values --no-hooks -n '{namespace}' '{release_name}' {helm_chart_path}"
    for i in range(2):
        print(f"Iteration {i + 1}/2: {command}\n")
        print(check_output(command, shell=True).decode("utf8"))

    result = houston_api.check_output("env | grep DATABASE_URL")
    # check that the connection is not reset
    assert "postgres" in result, "Expected to find DB connection string before Houston restart"

    # Kill houston in this pod so the container restarts
    houston_api.check_output("kill 1")

    # give time for container to restart
    time.sleep(100)

    # we can use k8s_core_v1_client instead of fixture, because we restarted pod so houston_api still ref to old pod id.
    pod = k8s_core_v1_client.list_namespaced_pod(namespace, label_selector="component=houston").items[0]
    houston_api_new = testinfra.get_host(f"kubectl://{pod.metadata.name}?container=houston&namespace={namespace}")
    result = houston_api_new.check_output("env | grep DATABASE_URL")

    # check that the connection is not reset
    assert "postgres" in result, "Expected to find DB connection string after Houston restart"
