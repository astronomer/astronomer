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
├── test_profile.yaml   # manifest: topology, values, kube_version (optional), namespace_labels (optional)
└── test_*.py           # this scenario's own assertions
```

## `test_profile.yaml` fields

| Field             | Required | Meaning                                                                                   |
| ------------------ | -------- | ------------------------------------------------------------------------------------------ |
| `topology`         | yes      | `unified`, `control`, or `data` — which existing install topology to layer this scenario on |
| `values`            | yes      | ordered list of values files (repo-relative), passed as `--helm-values` in order            |
| `kube_version`      | no       | pinned k8s version; defaults to the latest entry in `metadata.yaml`'s `test_k8s_versions`   |
| `namespace_labels`  | no       | labels to apply to the `astronomer` namespace *before* install (PSA is not retroactive)      |

## Running a scenario locally

```sh
uv run bin/run-scenario.py auth-sidecar
uv run pytest tests/functional/scenarios/auth-sidecar
```
