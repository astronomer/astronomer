#!/usr/bin/env python3
"""
Reconcile k3d (CP/DP) cross-cluster DNS + node-level hosts after OrbStack restarts.

Why this exists:
- For local CP/DP, we often pin cross-cluster hostnames (houston/app/grafana, dp01.*) to
  *current* k3d-assigned IPs (Service LoadBalancer IPs + node container IPs).
- After an OrbStack restart, k3d node container IPs and/or k3s service LoadBalancer IPs
  can change, and Docker may regenerate container /etc/hosts.
- Result: "network breaks" symptoms (404s for Houston endpoints, registry auth failures,
  prometheus proxy failures), even though the clusters are otherwise healthy.

This script re-writes:
- CoreDNS ConfigMap `data.NodeHosts` in each cluster to contain the correct IP -> hostname pins.
- The DP node container's /etc/hosts to pin `houston.<baseDomain>` to the CP ingress LB IP
  (needed for node-level image pulls: kubelet/containerd do NOT use CoreDNS).

Safe to run repeatedly (idempotent).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass


def _run(cmd: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _kubectl_get_json(context: str, namespace: str, kind: str, name: str) -> dict:
    proc = _run(
        ["kubectl", "--context", context, "-n", namespace, "get", kind, name, "-o", "json"],
    )
    return json.loads(proc.stdout)


def _kubectl_apply_json(context: str, obj: dict) -> None:
    raise NotImplementedError("Use _kubectl_apply_json_via_stdin()")


def _kubectl_apply_json_via_stdin(context: str, obj: dict) -> None:
    minimal = {
        "apiVersion": obj.get("apiVersion", "v1"),
        "kind": obj.get("kind", "ConfigMap"),
        "metadata": {
            "name": obj["metadata"]["name"],
            "namespace": obj["metadata"]["namespace"],
            "labels": obj["metadata"].get("labels", {}),
        },
        "data": obj.get("data", {}),
    }
    proc = subprocess.run(
        ["kubectl", "--context", context, "apply", "-f", "-"],
        input=json.dumps(minimal),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"kubectl apply failed (context={context}): {proc.stderr.strip()}")


def _kubectl_delete_coredns_pods(context: str) -> None:
    _run(["kubectl", "--context", context, "-n", "kube-system", "delete", "pod", "-l", "k8s-app=kube-dns"])
    _run(
        ["kubectl", "--context", context, "-n", "kube-system", "wait", "--for=condition=ready", "pod", "-l", "k8s-app=kube-dns", "--timeout=120s"]
    )


def _docker_inspect_ip(container: str) -> str:
    proc = _run(
        ["docker", "inspect", container, "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Could not determine IP for container {container}")
    return ip


def _kubectl_get_service_lb_ip(context: str, namespace: str, service: str) -> str:
    proc = _run(
        [
            "kubectl",
            "--context",
            context,
            "-n",
            namespace,
            "get",
            "svc",
            service,
            "-o",
            "jsonpath={.status.loadBalancer.ingress[0].ip}",
        ]
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Service {namespace}/{service} has no LoadBalancer ingress IP (context={context})")
    return ip


def _ensure_container_hosts_mapping(container: str, ip: str, hostname: str) -> None:
    # /etc/hosts is often regenerated on container restart; we append if missing.
    sh = (
        f"set -eu; "
        f"grep -qE '^[[:space:]]*{ip}[[:space:]]+.*\\b{hostname}\\b' /etc/hosts "
        f"|| echo '{ip} {hostname}' >> /etc/hosts"
    )
    _run(["docker", "exec", container, "sh", "-c", sh])


def _render_nodehosts(existing_nodehosts: str, *, ip: str, hostnames: list[str], marker: str) -> str:
    """
    Replace/append a single managed line under a marker comment.

    We avoid rewriting the rest of NodeHosts, since k3d manages some of it.
    """
    lines = existing_nodehosts.splitlines()
    # NodeHosts behaves like a hosts file: comment-only lines are ignored.
    # So the managed entry must be an active hosts mapping line (no leading '#').
    managed_suffix = f"# {marker}"
    wanted = f"{ip} " + " ".join(hostnames) + f"  {managed_suffix}"

    host_set = set(hostnames)

    out: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()

        # Backwards-compat cleanup: older versions wrote a commented marker line like:
        #   "# astronomer-cp: <ip> host1 host2"
        # That is ignored by CoreDNS, so remove it.
        if line.startswith(f"# {marker}:"):
            continue

        # If we see an existing managed line (active mapping with marker suffix), replace it.
        if managed_suffix in line:
            out.append(wanted)
            replaced = True
            continue

        if stripped and not stripped.startswith("#"):
            # NodeHosts format is: "<ip> host1 host2 ..."
            # If a line contains any hostname we manage, drop it to avoid stale entries winning.
            parts = stripped.split()
            for token in parts[1:]:
                if token in host_set:
                    line = ""
                    break
            if not line:
                continue

        out.append(line)
    if not replaced:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(wanted)
    # Ensure trailing newline for nice diffs.
    return "\n".join(out).rstrip("\n") + "\n"


@dataclass(frozen=True)
class Settings:
    cp_context: str
    dp_context: str
    platform_namespace: str
    base_domain: str
    dp_domain_prefix: str
    dp_node_container: str
    cp_ingress_service: str


def _settings_from_env() -> Settings:
    return Settings(
        cp_context=os.environ.get("CP_CONTEXT", "k3d-control"),
        dp_context=os.environ.get("DP_CONTEXT", "k3d-data"),
        platform_namespace=os.environ.get("PLATFORM_NAMESPACE", "astronomer"),
        base_domain=os.environ.get("BASE_DOMAIN", "localtest.me"),
        dp_domain_prefix=os.environ.get("DP_DOMAIN_PREFIX", "dp01"),
        dp_node_container=os.environ.get("DP_NODE_CONTAINER", "k3d-data-server-0"),
        cp_ingress_service=os.environ.get("CP_INGRESS_SERVICE", "astronomer-cp-nginx"),
    )


def main() -> int:
    s = _settings_from_env()

    cp_ingress_ip = _kubectl_get_service_lb_ip(s.cp_context, s.platform_namespace, s.cp_ingress_service)
    dp_node_ip = _docker_inspect_ip(s.dp_node_container)

    cp_hostnames = [
        s.base_domain,
        f"houston.{s.base_domain}",
        f"app.{s.base_domain}",
        f"grafana.{s.base_domain}",
    ]
    dp_hostnames = [
        f"{s.dp_domain_prefix}.{s.base_domain}",
        f"deployments.{s.dp_domain_prefix}.{s.base_domain}",
        f"registry.{s.dp_domain_prefix}.{s.base_domain}",
        f"commander.{s.dp_domain_prefix}.{s.base_domain}",
        f"elasticsearch.{s.dp_domain_prefix}.{s.base_domain}",
        f"prom-proxy.{s.dp_domain_prefix}.{s.base_domain}",
        f"prometheus.{s.dp_domain_prefix}.{s.base_domain}",
    ]

    # 1) DP CoreDNS pins CP hostnames -> CP ingress IP (pods calling CP)
    dp_coredns = _kubectl_get_json(s.dp_context, "kube-system", "configmap", "coredns")
    dp_nodehosts = dp_coredns.get("data", {}).get("NodeHosts", "")
    dp_coredns.setdefault("data", {})
    dp_coredns["data"]["NodeHosts"] = _render_nodehosts(
        dp_nodehosts, ip=cp_ingress_ip, hostnames=cp_hostnames, marker="astronomer-cp"
    )
    _kubectl_apply_json_via_stdin(s.dp_context, dp_coredns)
    _kubectl_delete_coredns_pods(s.dp_context)

    # 2) CP CoreDNS pins DP hostnames -> DP node IP (pods calling DP)
    cp_coredns = _kubectl_get_json(s.cp_context, "kube-system", "configmap", "coredns")
    cp_nodehosts = cp_coredns.get("data", {}).get("NodeHosts", "")
    cp_coredns.setdefault("data", {})
    cp_coredns["data"]["NodeHosts"] = _render_nodehosts(
        cp_nodehosts, ip=dp_node_ip, hostnames=dp_hostnames, marker="astronomer-dp"
    )
    _kubectl_apply_json_via_stdin(s.cp_context, cp_coredns)
    _kubectl_delete_coredns_pods(s.cp_context)

    # 3) Node-level DNS (kubelet/containerd) on the DP node for registry OAuth token calls
    _ensure_container_hosts_mapping(s.dp_node_container, cp_ingress_ip, f"houston.{s.base_domain}")

    print("Reconciled k3d/OrbStack CP/DP networking:")
    print(f"- CP ingress LB IP: {cp_ingress_ip}")
    print(f"- DP node IP:      {dp_node_ip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

