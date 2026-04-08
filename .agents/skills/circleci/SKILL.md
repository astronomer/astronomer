---
name: circleci
description: Use when writing, editing, or reviewing CircleCI configuration for the Astronomer APC repository. Covers script organization, inline vs external scripts, and config conventions.
---

# CircleCI Configuration Guide

## Critical Rules

1. **No long inline scripts** — script logic for any language must not be written inline in `.circleci/config.yml` if the script has complicated flow control. Complicated scripts belong in `bin/`.
2. **Scripts live in `bin/`** — every script called from CircleCI must exist as a file in the `bin/` directory with an appropriate extension (e.g. `bin/my-script.sh`, `bin/my-script.py`).
3. **Pin all versions** — never use `latest` or unpinned tags for Docker images or installed tools. Always specify an exact version to prevent supply chain vulnerabilities and ensure reproducible builds.

---

## Script Organization

Scripts invoked by CircleCI jobs must be committed to the repository under `bin/` so they can be:

- Linted and reviewed like any other source file
- Tested and run locally without needing CI
- Reused across multiple jobs or workflows

```yaml
# ✅ CORRECT — call a script from bin/
steps:
  - run:
      name: Build Helm chart
      command: bin/build-helm-chart.sh
```

```yaml
# ❌ WRONG — inline shell logic in the CircleCI config
steps:
  - run:
      name: Build Helm chart
      command: |
        helm package .
        mv astronomer-*.tgz /tmp/chart/
```

---

## Config Generation Pipeline

`.circleci/config.yml` is **never edited directly**. It is a generated file produced by rendering the Jinja2 template `.circleci/config.yml.j2` via `bin/generate_circleci_config.py`:

```bash
# Regenerate config.yml from the template
uv run bin/generate_circleci_config.py
```

The generator injects a small set of computed variables (e.g. `ci_runner_version`, `kube_versions`, `machine_image_version`, `docker_images`) into the template at render time. Always edit `.circleci/config.yml.j2`, then regenerate.

---

## Version Pinning

Always pin exact versions for Docker images and any tools installed during a job. Using `latest` or loose tags introduces supply chain risk and makes builds non-reproducible.

All pinned versions must be declared as Jinja2 variables at the **top of `.circleci/config.yml.j2`**, not scattered inline throughout the file. This makes them easy to audit and update in one place. All version declarations must include a link to where the list of released versions can be found, so that updating them is straightforward and doesn't require searching online to find more recent releases.

```jinja
{# ✅ CORRECT — versions declared at top of config.yml.j2 #}
{#- https://circleci.com/docs/guides/execution-managed/building-docker-images/#docker-version -#}
{%- set circleci_docker_version = 'docker23' -%}

{#- https://circleci.com/developer/machine/image/ubuntu-2404 -#}
{%- set machine_image_version = 'ubuntu-2404:2025.09.1' -%}
```

```yaml
# Then referenced inline:
docker:
  - image: cimg/python:{{ python_image_version }}
```

```yaml
# ❌ WRONG — version hardcoded inline, not declared at top
docker:
  - image: cimg/python:3.8.1
```

```yaml
# ❌ WRONG — unpinned image
docker:
  - image: cimg/python:latest
```

```yaml
# ✅ CORRECT — pinned tool version installed in a step
- run:
    name: Install helm
    command: bin/install-ci-tools.py 3.17.2

# ❌ WRONG — unversioned tool install
- run:
    name: Install helm
    command: curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```
