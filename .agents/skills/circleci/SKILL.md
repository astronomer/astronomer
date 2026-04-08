---
name: circleci
description: Use when writing, editing, or reviewing CircleCI configuration for the Astronomer APC repository. Covers script organization, inline vs external scripts, and config conventions.
---

# CircleCI Configuration Guide

## Critical Rules

1. **No inline scripts** — script logic for any language must never be written inline in `.circleci/config.yml`. All scripts belong in `bin/`.
2. **Scripts live in `bin/`** — every script called from CircleCI must exist as a file in the `bin/` directory with an appropriate extension (e.g. `bin/my-script.sh`, `bin/my-script.py`).

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
