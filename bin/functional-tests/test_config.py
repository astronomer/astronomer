#!/usr/bin/env python3
"""
This file is for system testing the Astronomer Helm chart.

Testinfra is used to create test fixtures.

testinfra simplifies and provides syntactic sugar for doing
execs into a running pods.
"""

import json
import os
import time
import yaml
import testinfra
from subprocess import check_output
from kubernetes.client.rest import ApiException


def test_default_disabled(kube_client):
    pods = kube_client.list_namespaced_pod("astronomer")
    default_disabled = ["keda", "prometheus-postgres-exporter"]
    for pod in pods.items:
        for feature in default_disabled:
            if feature in pod.metadata.name:
                raise Exception(f"Expected '{feature}' to be disabled")


def test_prometheus_user(prometheus):
    """Ensure user is 'nobody'"""
    user = prometheus.check_output("whoami")
    assert (
        user == "nobody"
    ), f"Expected prometheus to be running as 'nobody', not '{user}'"


def test_houston_config(houston_api):
    """Make assertions about Houston's configuration"""
    data = houston_api.check_output(
        "echo \"config = require('config'); console.log(JSON.stringify(config))\" | node -"
    )
    houston_config = json.loads(data)
    assert (
        "url" not in houston_config["nats"].keys()
    ), f"Did not expect to find 'url' configured for 'nats'. Found:\n\n{houston_config['nats']}"
    assert len(
        houston_config["nats"]["servers"]
    ), f"Expected to find 'servers' configured for 'nats'. Found:\n\n{houston_config['nats']}"
    for server in houston_config["nats"]:
        assert (
            "localhost" not in server
        ), f"Expected not to find 'localhost' in the 'servers' configuration. Found:\n\n{houston_config['nats']}"


def test_houston_can_reach_prometheus(houston_api):
    houston_api.check_output(
        "wget -qO- --timeout=1 http://astronomer-prometheus.astronomer.svc.cluster.local:9090/targets"
    )


def test_nginx_can_reach_default_backend(nginx):
    nginx.check_output(
        "curl -s --max-time 1 http://astronomer-nginx-default-backend:8080"
    )


def test_prometheus_targets(prometheus):
    """Ensure all Prometheus targets are healthy"""
    data = prometheus.check_output("wget -qO- http://localhost:9090/api/v1/targets")
    targets = json.loads(data)["data"]["activeTargets"]
    for target in targets:
        assert target["health"] == "up", (
            "Expected all prometheus targets to be up. "
            + 'Please check the "targets" view in the Prometheus UI'
            + f" Target data from the one that is not up:\n\n{target}"
        )


def test_core_dns_metrics_are_collected(prometheus):
    """Ensure CoreDNS metrics are collected.

    This test should work in CI and locally because Kind uses CoreDNS
    """
    data = prometheus.check_output(
        "wget -qO- http://localhost:9090/api/v1/query?query=coredns_dns_request_count_total"
    )
    parsed = json.loads(data)
    assert (
        len(parsed["data"]["result"]) > 0
    ), f"Expected to find a metric coredns_dns_request_count_total, but we got this response:\n\n{parsed}"


def test_houston_metrics_are_collected(prometheus):
    """Ensure Houston metrics are collected and prefixed with 'houston_'"""
    data = prometheus.check_output(
        "wget -qO- http://localhost:9090/api/v1/query?query=houston_up"
    )
    parsed = json.loads(data)
    assert (
        len(parsed["data"]["result"]) > 0
    ), f"Expected to find a metric houston_up, but we got this response:\n\n{parsed}"


def test_prometheus_config_reloader_works(prometheus, kube_client):
    """
    Ensure that Prometheus reloads its config when the cofigMap is updated
    and the reloader sidecar triggers the reload
    """
    # define new value we'll use for the config change
    new_scrape_interval = "31s"

    # get the current configmap
    orig_cm = kube_client.read_namespaced_config_map(
        "astronomer-prometheus-config", "astronomer"
    )

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
        kube_client.patch_namespaced_config_map(
            name="astronomer-prometheus-config", namespace="astronomer", body=new_body
        )
    except ApiException as e:
        print(f"Exception when calling CoreV1Api->patch_namespaced_config_map: {e}\n")

    # This can take more than a minute.
    i = 0
    while i < 12:
        data = prometheus.check_output(
            "wget -qO- http://localhost:9090/api/v1/status/config"
        )
        j_parsed = json.loads(data)
        # print(parsed['data']['yaml']['config']['global'])
        y_parsed = yaml.safe_load(j_parsed["data"]["yaml"])
        if y_parsed["global"]["scrape_interval"] != "30s":
            print(y_parsed["global"]["scrape_interval"])
            break
        else:
            time.sleep(10)
        i += 1

    # set the config back to it's original settings
    prom_config["global"]["scrape_interval"] = "30s"
    new_body = {
        "apiversion": "v1",
        "kind": "ConfigMap",
        "data": {"config": yaml.dump(prom_config)},
    }

    try:
        # update the configmap
        kube_client.patch_namespaced_config_map(
            name="astronomer-prometheus-config", namespace="astronomer", body=new_body
        )
    except ApiException as e:
        print(f"Exception when calling CoreV1Api->patch_namespaced_config_map: {e}\n")

    assert (
        y_parsed["global"]["scrape_interval"] != "30s"
    ), "Expected the prometheus config file to change"


def test_houston_backend_secret_present_after_helm_upgrade_and_container_restart(
    houston_api, kube_client
):
    """
    Test when helm upgrade occurs without Houston pods restarting that a
    Houston container restart will not miss the Houston connection backend secret

    Regression test for: https://github.com/astronomer/issues/issues/2251
    """
    helm_chart_path = os.environ.get("HELM_CHART_PATH")
    if not helm_chart_path:
        raise Exception(
            "This test only works with HELM_CHART_PATH set to the path of the chart to be tested"
        )
    namespace = os.environ.get("NAMESPACE")
    release_name = os.environ.get("RELEASE_NAME")
    if not namespace:
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = "astronomer"
    if not release_name:
        print(
            "RELEASE_NAME env var is not present, assuming 'astronomer' is the release name"
        )
        release_name = "astronomer"
    # attempt downgrade with the documented procedure
    print("Performing a Helm upgrade without hooks twice:\n")
    command = (
        "helm3 upgrade --reuse-values "
        + "--no-hooks "
        + f"-n {namespace} "
        + f"{release_name} "
        + helm_chart_path
    )
    print(command)
    print(check_output(command, shell=True))
    # Run the command twice to ensure the most
    # recent change is a no-operation change
    print(check_output(command, shell=True))
    print("")
    result = houston_api.check_output("env | grep DATABASE_URL")
    # check that the connection is not reset
    assert (
        "postgres" in result
    ), "Expected to find DB connection string before Houston restart"
    # Kill houston in this pod so the container restarts
    houston_api.check_output("kill 1")
    # give time for container to restart
    time.sleep(100)
    # we can use kube_client instead of fixture, because we restarted pod so houston_api still ref to old pod id.
    pods = kube_client.list_namespaced_pod(
        namespace, label_selector="component=houston"
    )
    pod = pods.items[0]
    houston_api_new = testinfra.get_host(
        f"kubectl://{pod.metadata.name}?container=houston&namespace={namespace}"
    )
    result = houston_api_new.check_output("env | grep DATABASE_URL")
    # check that the connection is not reset
    assert (
        "postgres" in result
    ), "Expected to find DB connection string after Houston restart"
