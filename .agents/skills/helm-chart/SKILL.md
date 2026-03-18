---
name: helm-chart
description: Use for Helm chart work - creating charts, modifying existing charts, values design, testing. For the Astronomer APC repository, see SPEC.md for repository-specific guidance.
---

# Helm Chart Work Guide

## Working on the Astronomer APC Chart

**See SPEC.md in the repository root for all APC-specific guidance:**

- **Architecture**: Umbrella chart design, sub-chart organization, design principles
- **Template Best Practices**: See "Probe Customization Pattern" section
  - **Critical**: Every container must support customizable livenessProbe and readinessProbe
- **Testing Strategy**: Pytest patterns, `render_chart()` utilities, test organization, running tests
  - **Critical**: Read the "Testing Sub-Chart Values" section in SPEC.md for proper values nesting in tests
  - **Critical**: Read "Testing Probe Customization" section - must add probes to `enable_all_probes.yaml` test data
- **Code Standards**: Naming conventions, template best practices, Python script standards
- **Values Documentation**: Helm-docs adoption plan, JSON schema structure
- **Refactoring Guidelines**: Modernization roadmap and improvement areas
- **Development Workflow**: Setup, building, validating changes

## Working on Other Helm Charts

General Helm chart best practices and reference material follows below.

## Keywords

helm, chart, development, testing, values, schema, kubernetes, templates, versioning

## Working on Other Helm Charts

### Quick Reference

| Task | Command |
|------|---------|
| Create chart | `helm create mychart` |
| Lint chart | `helm lint mychart/ --strict` |
| Template dry-run | `helm template myrelease mychart` |
| Update dependencies | `helm dependency update mychart/` |
| Validate K8s API versions | `helm template myrelease mychart/ \| pluto detect -` |
| Security audit | `helm template myrelease mychart/ \| kubescape scan framework nsa -` |

### Values Documentation

Use helm-docs comment pattern:

```yaml
# -- Brief description of what this value does
# @default -- value
myKey: value

myObject:
  # -- Nested key description
  nestedKey: value
```

### Template Helpers

Define common patterns in `_helpers.tpl`:

```tpl
{{- define "myapp.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

### Schema Validation

Create `values.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "replicaCount": {
      "type": "integer",
      "minimum": 1,
      "description": "Number of replicas"
    }
  }
}
```

### Best Practices

1. Reference [Helm Chart Best Practices](https://helm.sh/docs/chart_best_practices/)
2. Use helpers for reusable patterns
3. Provide sensible security defaults
4. Include comprehensive values documentation
5. Add values.schema.json for IDE support

---

**For the Astronomer APC repository, SPEC.md is the authoritative source.**
image: {{ required "image.repository is required" .Values.image.repository }}

# ❌ BAD: Silent failures
image: {{ .Values.image.repository }}  # Empty if not set
```

### Labels & Annotations

```yaml
# ✓ GOOD: Standard Kubernetes labels
metadata:
  labels:
    app.kubernetes.io/name: {{ include "myapp.name" . }}
    app.kubernetes.io/instance: {{ .Release.Name }}
    app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
    app.kubernetes.io/managed-by: {{ .Release.Service }}
    helm.sh/chart: {{ include "myapp.chart" . }}

# ❌ BAD: Non-standard labels
metadata:
  labels:
    app: myapp
    version: v1
```

---

## Versioning Strategy

### Semantic Versioning for Charts

```
MAJOR.MINOR.PATCH

MAJOR: Breaking changes (incompatible values schema changes)
MINOR: New features (backward compatible)
PATCH: Bug fixes (backward compatible)
```

### Version Bump Guidelines

| Change Type               | Version Bump | Example                           |
| ------------------------- | ------------ | --------------------------------- |
| Breaking values change    | MAJOR        | `image.name` → `image.repository` |
| Remove deprecated field   | MAJOR        | Remove `legacyMode`               |
| New optional feature      | MINOR        | Add `metrics.enabled`             |
| New template              | MINOR        | Add `servicemonitor.yaml`         |
| Bug fix                   | PATCH        | Fix label selector                |
| Documentation             | PATCH        | Update README                     |
| Dependency update (minor) | PATCH        | PostgreSQL 12.1.0 → 12.1.5        |
| Dependency update (major) | MINOR+       | PostgreSQL 11.x → 12.x            |

### Chart.yaml Version Management

```yaml
# Chart version (your release)
version: 2.1.0

# App version (upstream application)
appVersion: "3.5.2"
```

---

## Dependency Management

### Adding Dependencies

```yaml
# Chart.yaml
dependencies:
  - name: postgresql
    version: "12.x.x" # Use range for flexibility
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled
```

### Dependency Commands

```bash
# Update dependencies
helm dependency update mychart/

# Build dependencies (download to charts/)
helm dependency build mychart/

# List dependencies
helm dependency list mychart/
```

### Chart.lock Management

```yaml
# Chart.lock (auto-generated, commit to git)
dependencies:
  - name: postgresql
    repository: https://charts.bitnami.com/bitnami
    version: 12.1.6
digest: sha256:abc123...
generated: "2024-01-15T10:30:00Z"
```

### Dependency Version Ranges

```yaml
# Exact version
version: "12.1.6"

# Patch range (12.1.x)
version: "~12.1.0"

# Minor range (12.x.x)
version: "^12.0.0"

# Greater than
version: ">=12.0.0"

# Range
version: ">=12.0.0 <13.0.0"
```

### Import Values from Dependencies

```yaml
dependencies:
  - name: postgresql
    version: "12.x.x"
    repository: https://charts.bitnami.com/bitnami
    import-values:
      - child: primary.service
        parent: database
      # Or import all
      - child: null
        parent: postgresql
```

---

## Upgrade Strategies

### Non-Breaking Upgrades

```yaml
# Add new fields with defaults
newFeature:
  enabled: false # Default to off for existing users
```

### Breaking Changes

```yaml
# 1. Deprecate in MINOR release
# values.yaml
legacyField: ""  # @deprecated Use newField instead

# 2. Add migration helper
{{- if .Values.legacyField }}
{{- fail "legacyField is deprecated, please use newField" }}
{{- end }}

# 3. Remove in MAJOR release
```

### Upgrade Testing

```bash
# Test upgrade from previous version
helm upgrade myrelease mychart/ \
  --dry-run \
  --debug \
  -f old-values.yaml

# Diff changes
helm diff upgrade myrelease mychart/ -f values.yaml
```

---

## Testing

### How Helm Tests Work

1. Define test pods in `templates/` with `helm.sh/hook: test` annotation
2. Install chart with `helm install` or `helm upgrade`
3. Run tests with `helm test RELEASE_NAME`
4. Helm creates pods, executes them, reports results

**Test passes:** Pod exits with code 0
**Test fails:** Pod exits with non-zero code

### Test Annotations

| Annotation                    | Purpose                                       |
| ----------------------------- | -------------------------------------------- |
| `helm.sh/hook: test`          | Marks pod as a test (runs during `helm test`) |
| `helm.sh/hook: test-success`  | Runs after successful release                 |
| `helm.sh/hook: test-failure`  | Runs after failed release                     |
| `helm.sh/hook-weight:`        | Controls execution order (lower = first)      |
| `helm.sh/hook-delete-policy:` | Controls cleanup (`hook-succeeded`, `never`)  |

### Test Analysis: What to Test

| Resource Type            | Test Considerations                          |
| ------------------------ | -------------------------------------------- |
| Services                 | Endpoint reachability, DNS, correct ports    |
| Deployments/StatefulSets | Pod readiness, replica count, rollout status |
| Ingress                  | Route reachability, TLS certificates         |
| ConfigMaps/Secrets       | Values present, mounted correctly            |
| PVCs                     | Volume mounted, read/write access            |
| CRDs                     | Custom resource creation, reconciliation     |

### Test Categories

| Category        | Purpose                      | Examples                                 |
| --------------- | ---------------------------- | ---------------------------------------- |
| Smoke           | Quick "is it alive"          | Service health, pod readiness            |
| Functional      | Verify specific behavior     | API responses, database connectivity     |
| Integration     | Verify external interactions | Upstream services, third-party APIs      |
| Data Validation | Verify deployed state        | ConfigMap content, environment variables |

### Basic Test Pod Structure

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-test-connectivity"
  annotations:
    helm.sh/hook: test-success
    helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded
spec:
  containers:
    - name: test
      image: curlimages/curl:8.7.1
      command:
        - sh
        - -c
        - |
          set -e
          curl -f http://myapp-service:8080/health
  restartPolicy: Never
```

**Best practices:**

- Use `restartPolicy: Never`
- Use lightweight images (curlimages/curl, busybox, alpine)
- One test pod tests one thing well
- Exit code 0 = pass, non-zero = fail
- Pin images to specific versions, never use `latest`

**Common test images:**

- `curlimages/curl:8.7.1` - HTTP endpoint checks
- `busybox:1.36` - Basic shell utilities
- `bitnami/kubectl:1.29` - Kubernetes API queries
- `postgres:16-alpine` - Database connectivity

### Test Examples

#### Service Connectivity Test

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-api-test"
  annotations:
    helm.sh/hook: test-success
    helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded
spec:
  containers:
    - name: api-test
      image: curlimages/curl:8.7.1
      command:
        - sh
        - -c
        - |
          set -e
          # Test main endpoint
          curl -f http://{{ .Release.Name }}-service:8080/health || exit 1
          # Verify response content
          curl -s http://{{ .Release.Name }}-service:8080/health | grep -q "status.*ok" || exit 1
          {{- if .Values.auth.enabled }}
          # Test authenticated endpoint
          curl -f http://{{ .Release.Name }}-service:8080/secure \
            -H "Authorization: Bearer {{ .Values.auth.testToken }}" || exit 1
          {{- end }}
  restartPolicy: Never
```

#### Configuration Validation Test

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-config-test"
  annotations:
    helm.sh/hook: test-success
spec:
  containers:
  - name: config-test
    image: busybox:1.36
    command:
    - sh
    - -c
    - |
      set -e
      test -f /app/config.yaml || exit 1
      grep -q "logLevel: {{ .Values.logLevel }}" /app/config.yaml || exit 1
      grep -q "database:" /app/config.yaml || exit 1
  volumeMounts:
  - name: config
    mountPath: /app/config.yaml
    subPath: config.yaml
  volumes:
  - name: config
    configMap:
      name: {{ include "myapp.fullname" . }}-config
  restartPolicy: Never
```

#### Deployment Readiness Test

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-readiness-test"
  annotations:
    helm.sh/hook: test-success
spec:
  serviceAccountName: {{ include "myapp.fullname" . }}-test-sa
  containers:
  - name: kubectl-test
    image: bitnami/kubectl:1.29
    command:
    - sh
    - -c
    - |
      set -e
      kubectl get deployment {{ .Release.Name }} -n {{ .Release.Namespace }} -o json | \
        jq -e '.status.readyReplicas == {{ .Values.replicaCount }}' || exit 1
  restartPolicy: Never
```

#### Database Connection Test

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-db-test"
  annotations:
    helm.sh/hook: test-success
spec:
  containers:
    - name: db-test
      image: postgres:16-alpine
      command:
        - sh
        - -c
        - |
          set -e
          nc -zv {{ .Values.database.host }} {{ .Values.database.port }} || exit 1
          PGPASSWORD={{ .Values.database.password }} \
          psql -h {{ .Values.database.host }} -p {{ .Values.database.port }} \
                -U {{ .Values.database.user }} -d {{ .Values.database.name }} \
                -c "SELECT 1;" || exit 1
  restartPolicy: Never
```

### Test Organization

```
mychart/
├── templates/
│   ├── tests/
│   │   ├── test-service-connectivity.yaml
│   │   ├── test-config-validation.yaml
│   │   └── test-readiness.yaml
│   ├── deployment.yaml
│   └── service.yaml
```

### Conditional Testing

Enable/disable tests globally:

```yaml
{{- if .Values.tests.enabled }}
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-test"
  annotations:
    helm.sh/hook: test-success
spec:
  # ...
{{- end }}
```

In `values.yaml`:

```yaml
tests:
  enabled: true
```

Test specific configurations:

```yaml
{{- if .Values.metrics.enabled }}
# metrics test
{{- end }}
```

### Test Execution Order

Use `helm.sh/hook-weight` (lower runs first):

```yaml
# Test 1: Run first
metadata:
  annotations:
    helm.sh/hook-weight: "-5"

---
# Test 2: Run second
metadata:
  annotations:
    helm.sh/hook-weight: "0"
```

### Running and Debugging

```bash
# Run tests
helm test my-release
helm test my-release --logs
helm test my-release --timeout 10m
helm test my-release -n my-namespace

# Debugging
kubectl get pods -n namespace -l helm.sh/hook=test
kubectl logs my-release-test-connectivity -n namespace
kubectl describe pod my-release-test-connectivity -n namespace
```

### Test Design Considerations

#### Test Independence

Each test should verify one thing well:

```yaml
# Good: Single focused test
metadata:
  name: "{{ .Release.Name }}-test-health"

# Avoid: Tests multiple unrelated things
metadata:
  name: "{{ .Release.Name }}-test-everything"
```

#### Resource Management

Set limits to prevent exhaustion:

```yaml
spec:
  containers:
    - name: test
      image: curlimages/curl:8.7.1
      resources:
        requests:
          cpu: 100m
          memory: 64Mi
        limits:
          cpu: 200m
          memory: 128Mi
```

#### Cleanup Policies

| Policy           | Behavior             | Use Case         |
| ---------------- | -------------------- | ---------------- |
| `hook-succeeded` | Delete after passing | Normal operation |
| `never`          | Never delete         | Debugging        |

For debugging:

```yaml
metadata:
  annotations:
    helm.sh/hook-delete-policy: never
```

#### Error Handling

Provide clear failure messages:

```yaml
command:
  - sh
  - -c
  - |
    set -e
    if ! curl -f http://service:8080/health; then
      echo "ERROR: Service health check failed"
      echo "Troubleshooting: kubectl get svc, kubectl logs -l app=myapp"
      exit 1
    fi
```

#### Security

Use least privilege RBAC:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "myapp.fullname" . }}-test-sa
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: {{ include "myapp.fullname" . }}-test-role
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: {{ include "myapp.fullname" . }}-test-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: {{ include "myapp.fullname" . }}-test-role
subjects:
- kind: ServiceAccount
  name: {{ include "myapp.fullname" . }}-test-sa
```

Don't embed secrets:

```yaml
# Avoid
command:
  ["curl", "-H", "Authorization: Bearer super-secret-key", "http://service/"]

# Better
env:
  - name: TEST_TOKEN
    valueFrom:
      secretKeyRef:
        name: test-credentials
        key: token
```

### Common Test Failures

| Symptom            | Cause                    | Solution                             |
| ------------------ | ------------------------ | ------------------------------------ |
| Image pull errors  | Wrong image/registry     | Verify image name and pull secrets   |
| Connection refused | Service not ready        | Add readiness test, increase timeout |
| Permission denied  | Insufficient RBAC        | Add service account and role         |
| Command not found  | Wrong base image         | Use image with required tools        |
| Timeout            | Service startup too slow | Increase timeout or add retry logic  |

### Test Anti-Patterns

```yaml
# Wrong - runs during install
helm.sh/hook: post-install

# Correct - runs with helm test
helm.sh/hook: test-success

# Wrong - Kubernetes guarantees this
command: ["kubectl", "get", "pod", "|", "grep", "myapp"]

# Correct - test application functionality
command: ["curl", "http://myapp-service/health"]

# Fragile - exact match
response=$(curl http://service/health)
[ "$response" == '{"status":"ok"}' ]

# Robust - content check
curl http://service/health | grep -q "status.*ok"

# Avoid - waits 60 seconds
for i in $(seq 1 60); do sleep 1; done

# Prefer - quick check
curl -f --max-time 10 http://service/health
```

### Helm-Unittest Plugin

```yaml
# tests/deployment_test.yaml
suite: deployment tests
templates:
  - deployment.yaml
tests:
  - it: should create deployment with correct replicas
    set:
      replicaCount: 3
    asserts:
      - equal:
          path: spec.replicas
          value: 3

  - it: should use correct image
    set:
      image:
        repository: myapp
        tag: v1.0.0
    asserts:
      - equal:
          path: spec.template.spec.containers[0].image
          value: myapp:v1.0.0

  - it: should have security context
    asserts:
      - isNotNull:
          path: spec.template.spec.securityContext
      - equal:
          path: spec.template.spec.containers[0].securityContext.runAsNonRoot
          value: true

  - it: should fail without required value
    set:
      image.repository: null
    asserts:
      - failedTemplate: {}
```

Running tests:

```bash
# Helm built-in test
helm test myrelease

# helm-unittest plugin
helm unittest mychart/

# With coverage
helm unittest mychart/ --output-file results.xml --output-type JUnit
```

---

## Review & Quality Assurance

### Review Checklist

#### Structure & Organization

- [ ] Standard directory structure followed
- [ ] Chart.yaml has required fields (apiVersion, name, version)
- [ ] README.md exists and is complete
- [ ] NOTES.txt provides useful post-install information
- [ ] .helmignore excludes unnecessary files
- [ ] Templates organized logically

#### Values Design

- [ ] values.yaml has sensible defaults
- [ ] All values documented with comments
- [ ] values.schema.json validates inputs
- [ ] No hardcoded values in templates
- [ ] Sensitive values use secrets, not configmaps

#### Security

- [ ] Pod security context defined
- [ ] Container security context defined
- [ ] Service account with minimal permissions
- [ ] Network policies included (if applicable)
- [ ] No privileged containers by default
- [ ] Resource limits defined

#### Quality

- [ ] Templates pass `helm lint`
- [ ] Unit tests exist and pass
- [ ] Labels follow Kubernetes conventions
- [ ] Proper use of helpers (_helpers.tpl)
- [ ] Consistent naming conventions

### Security Review

#### Pod Security Checklist

```yaml
# REQUIRED security settings
podSecurityContext:
  runAsNonRoot: true # ✓ Never run as root
  fsGroup: 1000 # ✓ Set filesystem group
  seccompProfile:
    type: RuntimeDefault # ✓ Use seccomp

securityContext:
  allowPrivilegeEscalation: false # ✓ Block privilege escalation
  readOnlyRootFilesystem: true # ✓ Immutable container
  runAsNonRoot: true # ✓ Non-root user
  runAsUser: 1000 # ✓ Specific UID
  capabilities:
    drop:
      - ALL # ✓ Drop all capabilities
```

#### Security Anti-Patterns

```yaml
# ❌ BAD: Privileged container
securityContext:
  privileged: true

# ❌ BAD: Running as root
securityContext:
  runAsUser: 0

# ❌ BAD: Writable root filesystem
securityContext:
  readOnlyRootFilesystem: false

# ❌ BAD: Host namespaces
hostNetwork: true
hostPID: true
hostIPC: true

# ❌ BAD: Dangerous volume mounts
volumes:
  - name: host
    hostPath:
      path: /

# ❌ BAD: Secrets in environment variables (prefer mounted secrets)
env:
  - name: DB_PASSWORD
    value: "hardcoded-password"

# ❌ BAD: No resource limits
resources: {}
```

#### RBAC Review

```yaml
# ✓ GOOD: Minimal permissions
rules:
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get", "list", "watch"]
  resourceNames: ["my-config"]  # Even better: specific resources

# ❌ BAD: Overly permissive
rules:
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["*"]

# ❌ BAD: Cluster-wide access when namespace-scoped sufficient
kind: ClusterRole  # Should be Role if namespace-scoped
```

#### Image Security

```yaml
# ✓ GOOD: Specific tag
image:
  repository: myapp
  tag: "v1.2.3"  # Specific version

# ❌ BAD: Latest tag
image:
  repository: myapp
  tag: "latest"  # Mutable, unpredictable

# ✓ GOOD: Digest pinning for critical apps
image:
  repository: myapp@sha256:abc123...
```

### Automated Review Tools

```bash
# Basic linting
helm lint mychart/

# Strict mode
helm lint mychart/ --strict

# With values
helm lint mychart/ -f values-production.yaml

# Security scanning
trivy config mychart/

# Best practices
helm template myrelease mychart/ | polaris audit --audit-path -

# Deprecated APIs
helm template myrelease mychart/ | pluto detect -

# NSA security framework
helm template myrelease mychart/ | kubescape scan framework nsa -
```

### Code Review Comments

#### Severity Levels

| Level         | Description                                | Action                |
| ------------- | ------------------------------------------ | --------------------- |
| 🔴 Critical   | Security vulnerability, data loss risk     | Must fix before merge |
| 🟠 Major      | Best practice violation, significant issue | Should fix            |
| 🟡 Minor      | Style, minor improvement                   | Nice to have          |
| 🔵 Suggestion | Alternative approach                       | Consider              |

#### Example Review Comments

```markdown
🔴 **Critical: Security - Privileged Container**
The container is running as privileged which grants full host access.

```yaml
# Current
securityContext:
  privileged: true

# Suggested
securityContext:
  privileged: false
  allowPrivilegeEscalation: false
```

---

🟠 **Major: Missing Resource Limits**
No resource limits defined. This can lead to resource starvation.

```yaml
# Add to values.yaml
resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

---

🟡 **Minor: Use nindent instead of indent**
`nindent` handles newlines automatically and is more reliable.

```yaml
# Current
{{ toYaml .Values.labels | indent 4 }}

# Suggested
{{- toYaml .Values.labels | nindent 4 }}
```

---

🔵 **Suggestion: Consider using a helper**
This pattern is repeated in multiple templates. Consider extracting to \_helpers.tpl.
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Helm Chart CI

on:
  push:
    paths:
      - "charts/**"
  pull_request:
    paths:
      - "charts/**"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v3
      - name: Lint charts
        run: helm lint charts/*

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v3
      - name: Install helm-unittest
        run: helm plugin install https://github.com/helm-unittest/helm-unittest
      - name: Run tests
        run: helm unittest charts/*

  template:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v3
      - name: Template charts
        run: |
          for chart in charts/*; do
            helm template test $chart --debug
          done

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy
        uses: aquasecurity/trivy-action@0.28.0
        with:
          scan-type: "config"
          scan-ref: "charts/"

  release:
    needs: [lint, test, template, security]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Package and push
        run: |
          helm package charts/*
          # Push to registry
```

### Chart Releaser (cr)

```bash
# Package and upload to GitHub releases
cr package charts/mychart
cr upload --owner org --git-repo charts
cr index --owner org --git-repo charts --push
```

---

## Documentation

### README Template

````markdown
# MyApp Helm Chart

![Version: 1.0.0](https://img.shields.io/badge/Version-1.0.0-informational)
![AppVersion: 2.3.1](https://img.shields.io/badge/AppVersion-2.3.1-informational)

## Description

A Helm chart for deploying MyApp on Kubernetes.

## Prerequisites

- Kubernetes 1.23+
- Helm 3.10+
- PV provisioner (if persistence enabled)

## Installing

```bash
helm repo add myrepo https://charts.example.com
helm install myrelease myrepo/myapp
```

## Configuration

| Parameter          | Description        | Default                |
| ------------------ | ------------------ | ---------------------- |
| `replicaCount`     | Number of replicas | `1`                    |
| `image.repository` | Image repository   | `myapp`                |
| `image.tag`        | Image tag          | `""` (uses appVersion) |

## Upgrading

### From 1.x to 2.x

Breaking changes:

- `image.name` renamed to `image.repository`
- Minimum Kubernetes version is now 1.23

Migration:

```yaml
# Old (1.x)
image:
  name: myapp

# New (2.x)
image:
  repository: myapp
```
````

### Auto-Generate Docs (helm-docs)

```bash
helm-docs --chart-search-root=charts/
```
