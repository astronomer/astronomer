#!/usr/bin/env python3
"""
This file is for system testing the Astronomer Helm chart.

Many of these tests use pytest fixtures that use testinfra to exec
into running pods so we can inspect the run-time environment.
"""

import json
from os import getenv
import time
import yaml
import testinfra
from subprocess import check_output
from kubernetes.client.rest import ApiException
import pytest


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


def test_houston_can_reach_prometheus(houston_api):
    houston_api.check_output(
        "wget -qO- --timeout=1 http://astronomer-prometheus.astronomer.svc.cluster.local:9090/targets"
    )


def test_nginx_can_reach_default_backend(nginx):
    nginx.check_output(
        "curl -s --max-time 1 http://astronomer-nginx-default-backend:8080"
    )


@pytest.mark.flaky(reruns=10, reruns_delay=10)
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

    # coredns 1.7.0 changed a bunch of fields, so we have to act differently on >= 1.7.0
    # https://coredns.io/2020/06/15/coredns-1.7.0-release/
    data = prometheus.check_output(
        "wget -qO- http://localhost:9090/api/v1/query?query=coredns_build_info"
    )
    parsed = json.loads(data)
    coredns_version_string = parsed["data"]["result"][0]["metric"]["version"]
    coredns_version_list = [int(x) for x in coredns_version_string.split(".")[:3]]

    if coredns_version_list[0] != 1:
        raise Exception(f"Cannot determine CoreDNS version from {parsed}")

    if coredns_version_list[1] >= 7:
        metric = "coredns_dns_requests_total"
    elif coredns_version_list[1] < 7:
        metric = "coredns_dns_request_count_total"
    else:
        raise Exception(f"Cannot determine CoreDNS version from {parsed}")

    data = prometheus.check_output(
        f"wget -qO- http://localhost:9090/api/v1/query?query={metric}"
    )
    parsed = json.loads(data)
    assert (
        len(parsed["data"]["result"]) > 0
    ), f"Expected to find a metric {metric} in CoreDNS version {coredns_version_string}, but we got this response:\n\n{parsed}"


def test_houston_metrics_are_collected(prometheus):
    """Ensure Houston metrics are collected and prefixed with 'houston_'"""
    data = prometheus.check_output(
        "wget -qO- http://localhost:9090/api/v1/query?query=houston_up"
    )
    parsed = json.loads(data)
    assert (
        len(parsed["data"]["result"]) > 0
    ), f"Expected to find a metric houston_up, but we got this response:\n\n{parsed}"


def test_cve_2021_44228_es_client(es_client):
    """Ensure the running es process has -Dlog4j2.formatMsgNoLookups=true configured."""
    assert (
        es_client.check_output(
            "/usr/share/elasticsearch/jdk/bin/jps -lv | grep -o '[^ ]*MsgNoLookups[^ ]*'"
        )
        == "-Dlog4j2.formatMsgNoLookups=true"
    )


def test_cve_2021_44228_es_data(es_data):
    """Ensure the running es process has -Dlog4j2.formatMsgNoLookups=true configured."""
    assert (
        es_data.check_output(
            "/usr/share/elasticsearch/jdk/bin/jps -lv | grep -o '[^ ]*MsgNoLookups[^ ]*'"
        )
        == "-Dlog4j2.formatMsgNoLookups=true"
    )


def test_cve_2021_44228_es_master(es_master):
    """Ensure the running es process has -Dlog4j2.formatMsgNoLookups=true configured."""
    assert (
        es_master.check_output(
            "/usr/share/elasticsearch/jdk/bin/jps -lv | grep -o '[^ ]*MsgNoLookups[^ ]*'"
        )
        == "-Dlog4j2.formatMsgNoLookups=true"
    )
