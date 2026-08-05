# Scenarios

A **scenario** here is a named test configuration: an install topology, an ordered list of
values overlays, an optional pinned k8s version, and optional namespace labels to apply
before install. This is a different axis from topology (`unified`/`control`/`data`, see
`tests/functional/README.md`) — a scenario composes a topology with extra values/labels on
top; `topology: unified` in a scenario's `test_profile.yaml` means it installs using the
existing `unified` topology, with this scenario's own overlays layered on.

Topology is never read from an env var anywhere in this mechanism — `bin/run-scenario.py`
passes it to `bin/reset-local-dev`/`bin/helm-install.py` as an explicit `--topology` flag,
and pytest's `tests/functional/conftest.py` infers it directly from this manifest for any
test under `tests/functional/scenarios/<name>/`.

Existing `tests/functional/{unified,control,data}/` tests are not part of this mechanism
and aren't being migrated into it.

## Layout

```
tests/functional/scenarios/<name>/
├── test_profile.yaml   # manifest: topology, values, kube_version / namespace_labels / pre_helm_scripts (optional)
└── test_*.py           # this scenario's own assertions
```

## `test_profile.yaml` fields

| Field             | Required | Meaning                                                                                   |
| ------------------ | -------- | ------------------------------------------------------------------------------------------ |
| `topology`         | yes      | `unified`, `control`, or `data` — which existing install topology to layer this scenario on |
| `description`       | no       | one-paragraph summary of what the scenario validates; printed when the scenario runs and when `bin/run-scenario.py` is invoked with no argument to list scenarios |
| `values`            | yes      | ordered list of values files (repo-relative), passed as `--helm-values` in order; an empty list is fine if the scenario needs no overlay |
| `kube_version`      | no       | pinned k8s version; defaults to the latest entry in `metadata.yaml`'s `test_k8s_versions`   |
| `namespace_labels`  | no       | labels to apply to the `astronomer` namespace *before* install (PSA is not retroactive)      |
| `pre_helm_scripts`  | no       | ordered list of scripts run *after* the cluster is created but *before* `helm install` — for setup the chart's install-time values depend on (e.g. creating a private-CA Secret named in `global.privateCaCerts`). Each entry is a repo-relative script path, optionally followed by arguments (e.g. `bin/setup-forgejo-ca.py --platform-namespace astronomer --forgejo-namespace git-forgejo`). Each runs with `KUBECONFIG` pointed at the fresh cluster and the helper-tools PATH, and must be executable (shebang + `chmod +x`). |
| `resource_class`    | no       | CircleCI machine-executor resource class for this scenario's CI job (e.g. `xlarge`, `2xlarge`); defaults to `xlarge` |
| `kyverno_scan`      | no       | if `true`, installs a live Kyverno admission controller before this scenario's own tests run (`bin/install-kyverno-scan.py`) and reports the violations it recorded afterward (`bin/report-kyverno-scan.py`), without failing the build (PINF-1034); defaults to `false` |

## Running a scenario locally

```sh
uv run bin/run-scenario.py auth-sidecar
uv run pytest tests/functional/scenarios/auth-sidecar
```
