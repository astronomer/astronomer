# SPEC.md

## Overview

A Helm chart to install the Astronomer Astro Private Cloud (APC) application. APC is a Kubernetes application that provides Apache Airflow as a service.

**Table of Contents:**
- [Architecture](#architecture)
- [Development Workflow](#development-workflow)
- [Testing Strategy](#testing-strategy)
- [Values Documentation](#values-documentation)
- [Code Standards](#code-standards)
- [Refactoring Guidelines](#refactoring-guidelines)

---

## Architecture

### Umbrella Chart Design

The APC Helm chart is an **umbrella chart** with several sub-charts that are **not intended to be used standalone**. This design allows certain liberties that standalone sub-charts cannot take:

- **Templates live at the umbrella level** (not in individual sub-chart directories)
- Sub-charts can be tightly coupled
- Conditional feature flags control which components are deployed
- A single `values.yaml` controls the entire platform
- Global values are primarily defined in the top-level values.yaml

### Chart Structure

```
charts/
├── astronomer/              # Core APC platform (Commander, Houston API, etc.)
├── nginx/                   # Ingress and reverse proxy
├── alertmanager/            # Monitoring alerts
├── grafana/                 # Metrics visualization
├── prometheus/              # Metrics collection
├── elasticsearch/           # Logging backend
├── vector/                  # Log collection and processing
├── postgresql/              # Database for local development and testing cases (non-prod)
├── pgbouncer/              # Posgres database connection pooling
├── nats/                   # Message queue
├── kube-state/             # Kubernetes state metrics
├── prometheus-postgres-exporter/  # Database metrics
├── external-es-proxy/      # Optional external Elasticsearch proxy
└── airflow-operator/       # (Optional) Airflow custom resource definitions
```

### Dependency Management

Dependencies are defined in the root `Chart.yaml` with:
- **Conditions**: Enable/disable components (e.g., `global.networkPolicy.enabled`)
- **Tags**: Logical grouping (e.g., `monitoring`, `logging`, `platform`)

Example:
```yaml
dependencies:
  - name: prometheus
    condition: global.prometheus.enabled
    tags:
      - monitoring
```

### Template Organization

All Helm templates live at the **umbrella level** (under `templates/` and `charts/<chart>/templates/`):

1. **Umbrella templates** (`templates/`): Cross-cutting concerns, shared resources
2. **Sub-chart templates** (`charts/<chart>/templates/`): Component-specific resources
3. **Helper templates** (`_helpers.tpl`): Reusable template functions per chart

### Design Principles

1. **Single values hierarchy**: All configuration flows through the umbrella chart's `values.yaml`
2. **Conditional deployment**: Use Helm conditions to enable/disable features
3. **No standalone sub-charts**: Never use sub-charts independently
4. **Template reusability**: Share helpers across charts in the umbrella chart's `_helpers.tpl`
5. **Consistent naming**: Follow the conventions described in [Code Standards](#code-standards)

---

## Development Workflow

### Local Setup

Refer to:
- [README.md](README.md) - General setup and deployment
- [docs/cp-dp-k3d-setup-guide.md](docs/cp-dp-k3d-setup-guide.md) - Control Plane / Data Plane K3D setup for local testing.

### Building the Chart

The chart is built using:
- **`bin/build-helm-chart.sh`**: Main build script
- **`helm dep update`**: Updates sub-chart dependencies
- **`helm lint`**: Validates chart structure
- **`helm template`**: Renders manifests for testing

### Quick Manifest Rendering

```bash
helm template astronomer . \
  --values values.yaml \
  --show-only=charts/astronomer/templates/commander/commander-role.yaml \
  --show-only=charts/astronomer/templates/commander/commander-rolebinding.yaml
```

### Validating Changes

#### Running Tests

See [Testing Strategy](#testing-strategy)

#### Pre-Commit Checks with `prek`

All changes must pass pre-commit checks. Use `prek` to run these checks locally before committing:

```bash
# Run all pre-commit checks
prek

# Run pre-commit checks on staged files only
prek run --from-ref origin/main --to-ref HEAD

# Run specific hook
prek run --hook codespell
```

**Important**: Ensure `prek` exits with code 0. These checks are also run in CI/CD and must pass before code can be merged.

**What prek checks for:**
- **Custom validations**: Naming consistency (e.g., `rolebinding` not `role-binding`)
- **Image tags**: Ensures all Docker images have unique, valid tags
- **CircleCI config**: Validates consistency between `config.yml` and `config.yml.j2`
- **Spell checking**: Catches typos and spelling errors (codespell)
- **Formatting**: Removes tabs, enforces consistent formatting
- **Python linting**: Runs ruff checks on Python scripts

If checks fail, fix the issues and run `prek` again until it passes.

---

## Testing Strategy

See the [chart-tests skill](.agents/skills/chart-tests/SKILL.md) for the full testing guide, including:
- Test organization and file structure
- Writing tests: basic pattern, sub-chart values nesting, parametrization
- Test utilities: `render_chart()`, `get_containers_by_name()`, `get_all_features()`
- Running tests with `uv run pytest`
- Kubernetes schema validation

---

## Values Documentation

### Helm-Docs Comment Pattern (to be adopted)
│   ├── test_nginx.py         # One component per test file
│   ├── test_astronomer_commander.py
│   ├── test_*.py             # 60+ integration tests
│   ├── conftest.py           # Shared fixtures and configuration
│   ├── test_data/            # Test data files (feature configs, expected outputs)
│   └── README.md             # Testing documentation
├── functional/               # End-to-end cluster tests
│   ├── control/              # Control plane functional tests
│   ├── data/                 # Data plane functional tests
│   └── unified/              # Unified deployment tests
├── k8s_schema/               # Kubernetes API schemas for validation
└── utils/                    # Test utilities
    ├── chart.py              # render_chart() and helpers
    ├── fixtures.py           # Common test fixtures
    └── __init__.py
```

### Writing Tests

#### Basic Test Pattern

```python
import pytest
from tests.utils.chart import render_chart

def test_some_feature():
    """Brief description of what is being tested."""
    values = {"my_chart": {"enabled": True}}

    docs = render_chart(
        values=values,
        show_only=["charts/my-chart/templates/my-resource.yaml"],
    )

    assert len(docs) == 1
    assert docs[0]["kind"] == "Deployment"
    assert docs[0]["metadata"]["name"] == "my-resource"
```

#### Using `show_only` to Target Specific Templates

```python
# Render only specific templates
docs = render_chart(
    show_only=[
        "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
        "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
    ]
)
```

#### Testing Sub-Chart Values (Critical for Umbrella Chart)

Since the APC chart is an **umbrella chart** with sub-charts, values for sub-charts must be nested under the sub-chart name in the values dict:

```python
# ❌ WRONG: Will not override sub-chart values
values = {"houston": {"replicas": 3}}

# ✅ CORRECT: Properly nests values for the 'astronomer' sub-chart
values = {"astronomer": {"houston": {"replicas": 3}}}

# ✅ EXAMPLE: Testing dp-link with custom configuration
docs = render_chart(
    values={"astronomer": {"dpLink": {"enabled": False}}},
    show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
)
assert len(docs) == 0  # Deployment not rendered when disabled
```

**Important**: When testing templates from a sub-chart (e.g., `charts/astronomer/templates/...`), wrap all values under the sub-chart's top-level key, which is the sub-chart name from the parent chart's dependencies.

#### Parametrized Tests

```python
@pytest.mark.parametrize(
    "service_type,expected_traffic_policy",
    [
        ("ClusterIP", None),
        ("LoadBalancer", "Local"),
        ("NodePort", "Cluster"),
    ],
)
def test_service_types(service_type, expected_traffic_policy):
    """Test various service type configurations."""
    docs = render_chart(
        values={"nginx": {"serviceType": service_type}}
    )
    for doc in docs:
        if doc["kind"] == "Service":
            policy = doc["spec"].get("externalTrafficPolicy")
            assert policy == expected_traffic_policy
```

#### Testing with All Features Enabled

`get_all_features()` is a best effort to enable as many features as possible, but
due to incompatibilities between different features, it is not able to enable all
features simultaneously.

```python
from tests.utils import get_all_features

def test_with_all_features():
    """Test that all components work together."""
    chart_values = get_all_features()
    docs = render_chart(values=chart_values)

    # Verify expected components are present
    kinds = [doc["kind"] for doc in docs]
    assert "Deployment" in kinds
    assert "StatefulSet" in kinds
```

#### Testing Probe Customization (All Components)

Use `tests/chart_tests/test_data/enable_all_probes.yaml` to verify that every component and container supports customizable liveness and readiness probes. This test data file serves two purposes:

1. **Documentation**: Shows how to configure every probe in the system
2. **Validation**: Tests that all probes are actually customizable (not silently ignored)

When adding a new component or container, ensure it supports probe customization by:
1. Adding the component's liveness/readiness probes to `enable_all_probes.yaml`
2. Running tests with `enable_all_probes.yaml` to verify the probes are properly rendered

```yaml
# Example from enable_all_probes.yaml
astronomer:
  dpLink:
    livenessProbe:
      exec:
        command:
        - /bin/true
    readinessProbe:
      exec:
        command:
        - /bin/true
```

### Test Utilities

#### `render_chart(values=None, show_only=None, kube_version=None, validate_objects=True)`

Renders the Helm chart and returns parsed YAML documents.

- **`values`** (dict): Values to pass to `helm template` (merged with defaults)
- **`show_only`** (list): Templates to render (filters output)
- **`kube_version`** (str): Kubernetes version for schema validation
- **`validate_objects`** (bool): Validate manifests against K8s schemas

```python
from tests.utils.chart import render_chart

docs = render_chart(
    values={"nginx": {"enabled": True}},
    show_only=["charts/nginx/templates/controlplane/nginx-cp-service.yaml"],
    kube_version="1.31.0",
    validate_objects=True,
)
```

#### `get_all_features()`

Returns a values dict with most components enabled. Not all components can be enabled,
but this is the best effort to enable as many compatible components as possible.

```python
from tests.utils import get_all_features

all_features = get_all_features()
docs = render_chart(values=all_features)
```

#### `get_containers_by_name(docs, container_name)`

Extracts containers from pods/deployments by name.

```python
from tests.utils import get_containers_by_name

docs = render_chart(values=my_values)
containers = get_containers_by_name(docs, "myapp")
for container in containers:
    assert "MY_ENV_VAR" in container.get("env", [])
```

### Running Tests

```bash
# Run full suite in parallel (fastest — use for full runs)
uv run pytest tests/chart_tests/ -n auto --quiet

# Run all tests (verbose, sequential)
uv run pytest tests/chart_tests/ --verbose

# Run a specific test file
uv run pytest tests/chart_tests/test_nginx.py --verbose

# Run tests matching a pattern
uv run pytest tests/chart_tests/ -k "test_service" --verbose

# Run a single test
uv run pytest tests/chart_tests/test_nginx.py::test_nginx_service_basics --verbose

# Run with increased verbose output and stop on first failure
uv run pytest tests/chart_tests/ --verbose --verbose --capture=no --maxfail=1

# See test collection (without running)
uv run pytest tests/chart_tests/ --collect-only

# Iterate on fixing tests by running this repeatedly after encountering errors
uv run pytest tests/chart_tests/ --maxfail=1 --lf
```

> **Tip**: `-n auto` runs tests across all available CPU cores in parallel. Use it for full suite runs to significantly reduce wall-clock time. Omit it when running a single file or test to avoid subprocess overhead.

### Kubernetes Schema Validation

Tests automatically validate rendered manifests against Kubernetes OpenAPI schemas. These schemas are cached locally in `tests/k8s_schema/v<version>-standalone/`.

Schema validation happens by default unless `validate_objects=False` is passed to `render_chart()`.

#### Writing Schema-Aware Tests

```python
def test_custom_resource():
    """Test a custom K8s resource."""
    docs = render_chart(
        show_only=["charts/airflow-operator/templates/crds/airflow.yaml"],
        validate_objects=True,  # Validate against schema
    )

    for doc in docs:
        assert doc["kind"] == "CustomResourceDefinition"
```

---

## Values Documentation

### Helm-Docs Comment Pattern (to be adopted)

We will adopt the **helm-docs** comment pattern for documenting values. This allows automatic generation of values documentation.

#### Comment Syntax

Use `# --` comments above each value to document it:

```yaml
# -- Enable this component
# @default -- false
enabled: false

# -- Image to use for the component
# @default -- "astronomer/component:latest"
image:
  repository: astronomer/component
  tag: latest

# -- Number of replicas
# @default -- 3
replicaCount: 3

# -- Pod security context
# @default -- See values.yaml for details
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
```

#### Guidelines

1. **Place comments directly above the key**, not inline
2. **Use `# --`** to start documentation
3. **Use `@default --`** to specify the default value (if not obvious from the YAML)
4. **Keep descriptions concise** — one to two sentences max
5. **Reference related values**: e.g., "See `image.repository` for the image name"
6. **Document all top-level keys and important nested keys**

#### Examples

**Simple string value:**
```yaml
# -- The URL of the external database
# @default -- ""
externalDatabaseUrl: ""
```

**Boolean flag:**
```yaml
# -- Enable Prometheus monitoring
# @default -- true
prometheusEnabled: true
```

**Nested object:**
```yaml
# -- PostgreSQL configuration
# @default -- See values.yaml
postgresql:
  # -- Database name
  # @default -- "astronomer"
  dbName: astronomer

  # -- Database port
  # @default -- 5432
  port: 5432
```

**Array value:**
```yaml
# -- List of additional volume mounts for all pods
# @default -- []
extraVolumeMounts: []
```

### Values Schema (to be adopted)

We will add `values.schema.json` to each chart for:
- **IDE autocomplete** in `values.yaml` files
- **Validation** of user-provided values
- **Type safety** and documentation

#### Schema Structure

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "title": "My Chart Values",
  "type": "object",
  "properties": {
    "enabled": {
      "type": "boolean",
      "description": "Enable this component",
      "default": false
    },
    "image": {
      "type": "object",
      "description": "Component image settings",
      "properties": {
        "repository": {
          "type": "string",
          "description": "Container image repository",
          "default": "astronomer/component"
        },
        "tag": {
          "type": "string",
          "description": "Container image tag",
          "default": "latest"
        }
      }
    },
    "replicaCount": {
      "type": "integer",
      "description": "Number of replicas",
      "minimum": 1,
      "maximum": 10,
      "default": 3
    }
  }
}
```

---

## Code Standards

All code changes in this repository must pass automated checks. Before submitting a pull request:

1. **Run tests**: Ensure all pytest tests pass (see [Testing Strategy](#testing-strategy))
2. **Run pre-commit checks**: Use `prek` to validate code quality
3. **Follow naming conventions** and patterns documented below

### Naming Conventions

Follow this pattern for template file names:

```
charts/<component>/templates/<component>[-feature]-<k8s_object>.yaml
```

**Examples:**
- `charts/nginx/templates/controlplane/nginx-cp-deployment.yaml` (control plane specific)
- `charts/postgresql/templates/statefulset.yaml` (main component)
- `charts/prometheus/templates/prometheus-alerts-configmap.yaml` (ConfigMap resource)
- `charts/astronomer/templates/commander/commander-deployment.yaml` (nested feature)

**Conventions:**
- Use **lowercase** with **hyphens** (Helm standard)
- Start with component name
- Include Kubernetes object type if not obvious
- Use subdirectories for logical grouping (`controlplane/`, `dataplane/`, `webhooks/`, etc.)

### Template Best Practices

1. **Follow Helm recommendations**: Refer to the [Helm Chart Best Practices](https://helm.sh/docs/chart_best_practices/) guide
2. **Reuse helpers**: Create functions in `_helpers.tpl` for repeated patterns
3. **Comments**: Document non-obvious template logic
4. **Indentation**: Use 2 spaces consistently
5. **Scope management**: Use `with`, `range` scoping to keep templates readable
6. **Probe Customization**: Every container should support customizable `livenessProbe` and `readinessProbe` to allow operators to tune health checks for their environments

#### Probe Customization Pattern

Always expose `livenessProbe` and `readinessProbe` as overridable values:

```yaml
# In deployment template
{{- if .Values.myComponent.livenessProbe }}
livenessProbe: {{ tpl (toYaml .Values.myComponent.livenessProbe) $ | nindent 12 }}
{{- else }}
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
{{- end }}

# In values.yaml
myComponent:
  # -- Custom liveness probe configuration (overrides default)
  livenessProbe: {}
  # -- Custom readiness probe configuration (overrides default)
  readinessProbe: {}
```

**Why This Matters**: Different deployments have different operational requirements. Some may need longer initial delays due to slow startup, higher failure thresholds, or alternative probe methods (exec vs httpGet). Making probes customizable is a Kubernetes best practice.

#### Common Helpers Pattern

```tpl
{{- define "myapp.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "myapp.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

### Python Script Standards

Scripts in `bin/` should follow:
- **Type hints**: Use type hints for function parameters and returns
- **Error handling**: Always validate inputs and handle errors gracefully
- **Logging**: Use print/logging for clarity, avoid silent failures
- **Documentation**: Include docstrings for public functions
- **Modularity**: Break complex scripts into functions
- **Argument Parsing**: Use stdlib argparse for all argument parsing

Example:
```python
#!/usr/bin/env python3
"""Brief description of what this script does."""

from pathlib import Path
from typing import List, Dict

def process_files(file_paths: List[str]) -> Dict[str, int]:
    """Process a list of files and return results.

    Args:
        file_paths: List of file paths to process

    Returns:
        Dict mapping file path to line count

    Raises:
        FileNotFoundError: If a file does not exist
    """
    results = {}
    for file_path in file_paths:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        results[file_path] = len(p.read_text().splitlines())
    return results

if __name__ == "__main__":
    files = ["file1.txt", "file2.txt"]
    results = process_files(files)
    for file, count in results.items():
        print(f"{file}: {count} lines")
```

### Resource Naming in Manifests

Kubernetes resource names should follow Helm patterns:

```yaml
# Good: Uses release name for uniqueness
metadata:
  name: {{ include "myapp.fullname" . }}-component
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "myapp.labels" . | nindent 4 }}

# Bad: Hard-coded name, may conflict
metadata:
  name: mycomponent
```

---

## Refactoring Guidelines

### Current Goals

This repository will be gradually refactored in the following areas:

#### 1. Template Organization (DRY Principles)

**Current state**: Some template duplication across charts
**Goal**: Extract common patterns into helpers, reduce duplication

Example area for refactoring: Network policies, RBAC, pod disruption budgets

```tpl
# Create a helper for network policy defaults
{{- define "myapp.networkPolicy" -}}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "myapp.fullname" . }}
  {{- include "myapp.labels" . | nindent 2 }}
spec:
  podSelector:
    matchLabels:
      {{- include "myapp.selectorLabels" . | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: {{ .Release.Namespace }}
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: {{ .Release.Namespace }}
{{- end }}
```

#### 2. Values Schema Adoption

**Current state**: No `values.schema.json` files
**Goal**: Add schema.json to all charts for validation and IDE support

Priority charts for schema adoption:
- `charts/astronomer/` (main chart)
- `charts/nginx/` (critical ingress configuration)
- `charts/postgresql/` (database configuration)

#### 3. Python Script Modernization

**Current state**: Some `bin/` scripts may lack type hints, error handling
**Goal**: Standardize on type hints, improve error messages, add logging

Areas to review:
- `bin/build-helm-chart.sh` → consider Python refactoring
- `bin/helm-install.py` → add type hints, improve error handling
- `bin/setup-*.py` scripts → standardize patterns

#### 4. Test Infrastructure Improvements

**Current state**: Robust test suite exists
**Goal**: Improve test organization, add more focused unit tests

- Document test patterns in tests/chart_tests/README.md
- Create fixtures for common values patterns
- Add integration tests for complex feature interactions

---

## References

Additional documentation:
- [README.md](README.md) — General setup and deployment guide
- [docs/cp-dp-k3d-setup-guide.md](docs/cp-dp-k3d-setup-guide.md) — Local Kubernetes setup
- [tests/chart_tests/README.md](tests/chart_tests/README.md) — Test-specific details
- [tests/functional/README.md](tests/functional/README.md) — Functional test guide
- [Helm Chart Best Practices](https://helm.sh/docs/chart_best_practices/)
- [Kubernetes JSON Schema](https://json-schema.org/)
