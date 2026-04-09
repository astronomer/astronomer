---
name: chart-tests
description: Use when writing, editing, reviewing, or running Helm chart tests for the Astronomer APC repository. Covers pytest patterns, render_chart() usage, sub-chart value nesting, parametrized tests, uv run commands, schema validation, and test organization.
---

# Chart Test Writing Guide

## Critical Rules

1. **Always run tests with `uv run`** — never `python3 -m pytest` or `python bin/...`
2. **Sub-chart values MUST be nested** under the sub-chart name (see [Values Nesting](#sub-chart-values-nesting--critical))
3. **No `helm unittest` plugin** — all tests are pytest-based using `render_chart()`

---

## Test Organization

```
tests/
├── chart_tests/              # Helm template rendering tests (main focus)
│   ├── test_<component>.py   # One file per component
│   ├── conftest.py           # Shared fixtures
│   └── test_data/            # Feature configs, expected outputs
├── functional/               # End-to-end cluster tests
├── k8s_schema/               # Cached Kubernetes API schemas
└── utils/
    ├── chart.py              # render_chart() and helpers
    ├── fixtures.py           # Common fixtures
    └── __init__.py           # get_containers_by_name(), get_all_features(), etc.
```

---

## Writing Tests

### Basic Pattern

```python
import pytest
from tests import supported_k8s_versions
from tests.utils.chart import render_chart

DEPLOYMENT_FILE = "charts/grafana/templates/grafana-deployment.yaml"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_some_feature(kube_version):
    """Brief description of what is being tested."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=[DEPLOYMENT_FILE],
        values={"grafana": {"enabled": True}},
    )
    assert len(docs) == 1
    assert docs[0]["kind"] == "Deployment"
```

### Sub-Chart Values Nesting — CRITICAL

Templates in `charts/<subchart>/templates/` belong to a sub-chart. Values for those templates **must** be nested under the sub-chart's top-level key:

```python
# ❌ WRONG — will not override sub-chart values
values = {"houston": {"replicas": 3}}

# ✅ CORRECT — nest under the sub-chart name
values = {"astronomer": {"houston": {"replicas": 3}}}

# ✅ EXAMPLE — disable a feature in the astronomer sub-chart
docs = render_chart(
    values={"astronomer": {"dpLink": {"enabled": False}}},
    show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
)
assert len(docs) == 0
```

Top-level charts (e.g. `nginx`, `grafana`, `prometheus`) use their chart name directly:
```python
values = {"nginx": {"serviceType": "LoadBalancer"}}
values = {"grafana": {"extraEnvVars": [...]}}
```

### Using `show_only`

Always use `show_only` to target the specific template being tested:

```python
docs = render_chart(
    show_only=[
        "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
        "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
    ]
)
```

### Parametrized Tests

Always parametrize over `supported_k8s_versions` and over relevant values axes:

```python
@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("plane_mode,docs_count", [("control", 1), ("unified", 1), ("data", 0)])
def test_deployment_should_render(kube_version, plane_mode, docs_count):
    docs = render_chart(
        kube_version=kube_version,
        show_only=[DEPLOYMENT_FILE],
        values={"global": {"plane": {"mode": plane_mode}}},
    )
    assert len(docs) == docs_count
```

### Testing with All Features Enabled

`get_all_features()` enables as many compatible features as possible. Not all features can be enabled simultaneously due to incompatibilities.

```python
from tests.utils import get_all_features

def test_with_all_features():
    docs = render_chart(values=get_all_features())
    kinds = [doc["kind"] for doc in docs]
    assert "Deployment" in kinds
```

### Testing Probe Customization

Every container must support customizable `livenessProbe` and `readinessProbe`. When adding a new component:

1. Add its probes to `tests/chart_tests/test_data/enable_all_probes.yaml`
2. Run tests with that file to verify probes are rendered correctly

---

## ConfigMap Scripts

Scripts embedded in ConfigMaps must follow these conventions:

1. **Static content only** — scripts must not use Helm templating to conditionally modify their content based on chart values. The rendered output must be identical regardless of what values are passed.

2. **Environment variable inputs** — all runtime configuration must be passed as environment variables defined in the container spec (via `env` or `envFrom`), not baked into the script at render time.

3. **Stored as files on disk** — scripts must be committed as real files in the repository (e.g. under `charts/<subchart>/files/`) so they can be linted and reviewed like any other source file.

4. **Included via `.Files.Get`** — scripts must be included in ConfigMap templates using `.Files.Get`, not inline Helm template blocks:

   ```yaml
   # ✅ CORRECT
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: {{ include "chart.fullname" . }}-scripts
   data:
     my-script.sh: {{ .Files.Get "files/my-script.sh" | quote }}
   ```

   ```yaml
   # ❌ WRONG — inline script with template logic
   data:
     my-script.sh: |
       #!/bin/sh
       {{- if .Values.someFlag }}
       do_something
       {{- end }}
   ```

---

## Test Utilities

### `render_chart(values, show_only, kube_version, validate_objects)`

Renders the chart via `helm template` and returns parsed YAML documents.

| Parameter | Type | Description |
|---|---|---|
| `values` | `dict` | Values merged with chart defaults |
| `show_only` | `list[str]` | Templates to render (filters output) |
| `kube_version` | `str` | K8s version for schema validation |
| `validate_objects` | `bool` | Validate against K8s schemas (default `True`) |

```python
from tests.utils.chart import render_chart

docs = render_chart(
    values={"nginx": {"enabled": True}},
    show_only=["charts/nginx/templates/controlplane/nginx-cp-service.yaml"],
    kube_version="1.31.0",
)
```

### `get_containers_by_name(doc, *, include_init_containers=False)`

Returns `{name: container_dict}` for all containers in a pod manager doc (Deployment, StatefulSet, DaemonSet, Job, CronJob). Pass `include_init_containers=True` to also include init containers.

```python
from tests.utils import get_containers_by_name

c_by_name = get_containers_by_name(doc, include_init_containers=True)
assert c_by_name["grafana"]["securityContext"] == {"readOnlyRootFilesystem": True}
assert c_by_name["bootstrapper"]["securityContext"] == {"readOnlyRootFilesystem": True}
```

### `get_all_features()`

Returns a values dict with most components enabled.

```python
from tests.utils import get_all_features
```

### Other utilities in `tests/utils/__init__.py`

- `get_env_vars_dict(container_env)` — converts env list to `{name: value}` dict
- `get_service_ports_by_name(doc)` — returns service ports keyed by name
- `get_pod_template(doc)` — extracts pod template from any pod manager
- `get_service_account_name_from_doc(doc)` — returns the `serviceAccountName`
- `dot_notation_to_dict(dotted_string, default_value)` — builds nested dict from dot notation

---

## Running Tests

```bash
# Full suite in parallel (fastest — use for full runs)
uv run pytest tests/chart_tests/ -n auto --quiet

# Full suite, verbose
uv run pytest tests/chart_tests/ --verbose

# Single file
uv run pytest tests/chart_tests/test_grafana.py --verbose

# Tests matching a pattern
uv run pytest tests/chart_tests/ -k "test_service" --verbose

# Single test
uv run pytest tests/chart_tests/test_grafana.py::test_deployment_should_render --verbose

# Verbose output, stop on first failure
uv run pytest tests/chart_tests/ -vv --capture=no --maxfail=1

# Iterate on failures: re-run only last-failed tests
uv run pytest tests/chart_tests/ --maxfail=1 --lf
```

> **Tip**: `-n auto` uses all CPU cores. Omit it when running a single file to avoid subprocess overhead.

---

## Kubernetes Schema Validation

Tests validate rendered manifests against cached K8s OpenAPI schemas in `tests/k8s_schema/v<version>-standalone/`. Validation runs by default; disable with `validate_objects=False`.

```python
def test_custom_resource():
    docs = render_chart(
        show_only=["charts/airflow-operator/templates/crds/airflow.yaml"],
        validate_objects=True,
    )
    for doc in docs:
        assert doc["kind"] == "CustomResourceDefinition"
```
