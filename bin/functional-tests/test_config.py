#!/usr/bin/env python3
"""
This file is for system testing the Astronomer Helm chart.

Testinfra is used to create test fixures.

testinfra simplifies and provides syntactic sugar for doing
execs into a running pods.
"""

import json
import os
import docker


def test_default_disabled(kube_client):
    pods = kube_client.list_namespaced_pod('astronomer')
    default_disabled = ['keda', 'prometheus-postgres-exporter']
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
