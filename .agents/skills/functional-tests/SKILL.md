---
name: functional-tests
description: Use when writing, editing, reviewing, or running functional (end-to-end) tests for the Astronomer APC repository. Covers scenario setup, testinfra patterns, kubeconfig helpers, fixture usage, flaky test handling, and test organization across unified/control/data installation scenarios.
---

# Functional Test Writing Guide

## Overview

Functional tests run against a live Kubernetes cluster (kind) with the Helm chart installed. Unlike chart tests, they verify real runtime behavior: running processes, user identity, network reachability, and configuration values.

---

## Critical Rules

1. **Always run tests with `uv run`** — never `python3 -m pytest` or `python -m pytest`
2. **Always set `TEST_SCENARIO`** before running or the kubeconfig path will be `None`
3. **Always use uppercase kubeconfig constants** from `tests.utils.k8s` — `KUBECONFIG_UNIFIED`, `KUBECONFIG_CONTROL`, `KUBECONFIG_DATA` (not lowercase variants)
4. **Run `bin/reset-local-dev` before the first test run** to set up the cluster

---

## Installation Scenarios

Three scenarios exist, each with its own test directory:

| Scenario | Directory | Description |
|----------|-----------|-------------|
| `unified` | `tests/functional/unified/` | Control plane + data plane in one cluster |
| `control` | `tests/functional/control/` | Control plane components only |
| `data` | `tests/functional/data/` | Data plane components only |

**Cross-scenario tests** (applicable to all planes) belong in `tests/functional/shared/`. This directory does not yet exist — create it (with an `__init__.py`) when adding the first shared test, then add an entry point to each scenario's conftest if needed.

---

## Local Setup Workflow

```bash
# 1. Choose a scenario
export TEST_SCENARIO=unified   # or: control, data

# 2. Set up the cluster (downloads tools, generates certs, launches kind, installs chart)
bin/reset-local-dev

# 3. Run the tests (does NOT tear down the cluster — re-run freely while iterating)
uv run pytest tests/functional/${TEST_SCENARIO}

# 4. See helper file paths (kubeconfig, etc.)
make show-test-helper-files
```

**Makefile shortcuts** run setup + tests in one step:
```bash
make test-functional-unified
make test-functional-control
make test-functional-data
```

**Enable verbose debug output** (`helm install --debug`, `kubectl -v=9`):
```bash
export DEBUG=1
```

**Stored artifacts** (outside the repo, consistent across runs):
- Tools: `~/.local/share/astronomer-software/bin`
- Kubeconfigs: `~/.local/share/astronomer-software/kubeconfig/{unified,control,data}`
- Certs: `~/.local/share/astronomer-software/certs` (auto-renewed if expiring within 4 weeks)

---

## Test Organization

```
tests/functional/
├── conftest.py                        # Shared fixtures (k8s clients, named pod hosts)
├── unified/
│   ├── conftest.py                    # unified-specific fixtures (if any)
│   ├── test_config.py                 # Configuration and behavior assertions
│   ├── test_container_user_is_not_root.py
│   ├── test_network_security.py       # Port-scan test (complex one-off, do not replicate pattern)
│   └── test_container_read_only_root.py
├── control/
│   ├── conftest.py
│   ├── test_control.py
│   ├── test_pod_configs.py
│   └── test_container_user_is_not_root.py
├── data/
│   ├── test_data.py
│   └── test_container_user_is_not_root.py
└── shared/                            # Create when adding first cross-scenario test
    ├── __init__.py
    └── test_<name>.py
```

---

## Kubeconfig Helpers

Always import from `tests.utils.k8s`:

```python
from tests.utils.k8s import KUBECONFIG_UNIFIED, KUBECONFIG_CONTROL, KUBECONFIG_DATA
```

These resolve to `~/.local/share/astronomer-software/kubeconfig/<scenario>`.

> **Known bug**: `tests/functional/control/test_container_user_is_not_root.py` imports
> `kubeconfig_control` (lowercase), which does not exist in `tests.utils.k8s`. Fix this to
> `KUBECONFIG_CONTROL` whenever you touch that file.

---

## Shared Fixtures

`tests/functional/conftest.py` provides these fixtures (all `scope="function"`):

| Fixture | Type | Description |
|---------|------|-------------|
| `k8s_core_v1_client` | `CoreV1Api` | Kubernetes core/v1 API client |
| `k8s_apps_v1_client` | `AppsV1Api` | Kubernetes apps/v1 API client |
| `cp_nginx` | `testinfra.Host` | cp-ingress-controller nginx container |
| `dp_nginx` | `testinfra.Host` | dp-ingress-controller nginx container |
| `grafana` | `testinfra.Host` | grafana container |
| `houston_api` | `testinfra.Host` | houston container |
| `prometheus` | `testinfra.Host` | prometheus-0 container |
| `es_master` | `testinfra.Host` | elasticsearch-master-0 container |
| `es_data` | `testinfra.Host` | elasticsearch-data-0 container |
| `all_containers` | `list[testinfra.Host]` | Every container in the `astronomer` namespace |

---

## Writing Tests

### Assert command output in a container

```python
def test_prometheus_user(prometheus):
    user = prometheus.check_output("whoami")
    assert user == "nobody", f"Expected 'nobody', got '{user}'"
```

### Assert a file exists and has expected content

```python
def test_dashboard_config_mounted(grafana):
    f = grafana.file("/etc/grafana/provisioning/dashboards/dashboard.yaml")
    assert f.exists
    assert f.is_file
    content = grafana.check_output("cat /etc/grafana/provisioning/dashboards/dashboard.yaml")
    assert "apiVersion: 1" in content
    assert "providers:" in content
```

### Assert containers do not run as root

```python
import pytest
import testinfra
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_running_containers

container_ignore_list = ["kube-state", "houston", "astro-ui"]

def test_container_user_is_not_root():
    containers = get_pod_running_containers(kubeconfig=KUBECONFIG_UNIFIED, namespace="astronomer")
    for container in containers.values():
        if container["_name"] in container_ignore_list:
            pytest.skip(f"Unsupported container: {container['_name']}")
        host = testinfra.get_host(
            f"kubectl://{container['pod_name']}?container={container['_name']}&namespace={container['namespace']}",
            kubeconfig=KUBECONFIG_UNIFIED,
        )
        user = host.user()
        assert user.name != "root"
        assert user.uid != 0
        assert user.gid != 0
```

### Use the Kubernetes API directly

```python
def test_ensure_feature_disabled(k8s_core_v1_client):
    pods = k8s_core_v1_client.list_namespaced_pod("astronomer")
    should_not_run = ["prometheus-postgres-exporter"]
    for pod in pods.items:
        for feature in should_not_run:
            if feature in pod.metadata.name:
                raise ValueError(f"Expected '{feature}' to be disabled")
```

### Parse JSON config from a container process

```python
import json

def test_houston_config(houston_api):
    data = houston_api.check_output(
        "echo \"config = require('config'); console.log(JSON.stringify(config))\" | node -"
    )
    config = json.loads(data)
    assert "url" not in config["nats"]
    assert len(config["nats"]["servers"]) > 0
```

---

## Flaky Tests

Use `@pytest.mark.flaky` for tests that depend on eventually-consistent cluster state (e.g. network reachability, pod readiness):

```python
@pytest.mark.flaky(reruns=20, reruns_delay=10)
def test_houston_can_reach_prometheus(houston_api):
    assert houston_api.check_output(
        "wget --timeout=5 -qO- http://astronomer-prometheus.astronomer.svc.cluster.local:9090/targets"
    )
```

- `reruns`: max retry attempts on failure
- `reruns_delay`: seconds between retries
- Use sparingly — only when the cluster genuinely needs time to converge

---

## Utility Functions

From `tests.utils.k8s`:

**`get_pod_running_containers(namespace, kubeconfig=None) -> dict`**
Returns `{pod_name_container_name: container_info}` for all **ready** containers. Each value includes `pod_name`, `namespace`, and `_name` (container name).

**`get_pod_by_label_selector(namespace, label_selector, kubeconfig) -> str`**
Returns the name of the first pod matching the given label selector. Asserts at least one pod is found.

---

## What NOT to Do

- Do **not** hardcode kubeconfig paths — always use the constants from `tests.utils.k8s`
- Do **not** run with `python -m pytest` — always use `uv run pytest`
- Do **not** replicate the class-based structure of `test_network_security.py` for ordinary tests — that file is a one-off for a specialized port-scan workflow
- Do **not** add tests directly to `tests/functional/` root — tests belong in a scenario subdirectory or `shared/`
