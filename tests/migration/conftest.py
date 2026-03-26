"""Fixtures for migration script tests."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from textwrap import dedent

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_rt(text: str) -> dict:
    """Load YAML text using round-trip mode.

    Parameters:
        text: Raw YAML string to parse.

    Returns:
        Parsed YAML document.
    """
    yml = YAML(typ="rt")
    return yml.load(StringIO(text))


def _dump_rt(data: dict) -> str:
    """Dump a YAML document to string using round-trip mode.

    Parameters:
        data: Parsed YAML document.

    Returns:
        YAML string.
    """
    yml = YAML(typ="rt")
    stream = StringIO()
    yml.dump(data, stream)
    return stream.getvalue()


@pytest.fixture()
def old_partial_override_text() -> str:
    """A realistic customer partial override using the old 1.x schema."""
    return dedent("""\
        global:
          baseDomain: mycompany.astronomer.io
          # RBAC setting
          rbacEnabled: true
          sccEnabled: true
          openshiftEnabled: true
          namespaceFreeFormEntry: true
          taskUsageMetricsEnabled: true
          deployRollbackEnabled: true
          networkNSLabels: true
          features:
            namespacePools:
              enabled: true
              createRbac: true
              namespaces:
                create: true
                names:
                - ns1
                - ns2
          dagOnlyDeployment:
            enabled: true
            repository: custom-registry/dag-deploy
            tag: 1.0.0
          loggingSidecar:
            enabled: true
            name: my-sidecar
            repository: custom-registry/vector
            tag: 0.50.0

        astronomer:
          houston:
            resources:
              requests:
                cpu: "1000m"
    """)


@pytest.fixture()
def expected_new_partial_text() -> str:
    """Expected output after migrating old_partial_override."""
    return dedent("""\
        global:
          baseDomain: mycompany.astronomer.io
          # RBAC setting
          rbac:
            enabled: true
          scc:
            enabled: true
          openshift:
            enabled: true
          networkNSLabels:
            enabled: true
          namespaceManagement:
            namespaceFreeFormEntry:
              enabled: true
            namespacePools:
              enabled: true
              createRbac: true
              namespaces:
                create: true
                names:
                - ns1
                - ns2
          metricsReporting:
            taskUsageMetrics:
              enabled: true
          deploymentLifecycle:
            deployRollback:
              enabled: true
          deployMechanisms:
            dagOnlyDeployment:
              enabled: true
              repository: custom-registry/dag-deploy
              tag: 1.0.0
          logging:
            loggingSidecar:
              enabled: true
              name: my-sidecar
              repository: custom-registry/vector
              tag: 0.50.0

        astronomer:
          houston:
            resources:
              requests:
                cpu: "1000m"
    """)


@pytest.fixture()
def old_partial_override(old_partial_override_text: str) -> dict:
    """Parsed old partial override."""
    return _load_rt(old_partial_override_text)


@pytest.fixture()
def expected_new_partial(expected_new_partial_text: str) -> dict:
    """Parsed expected new partial."""
    return _load_rt(expected_new_partial_text)


@pytest.fixture()
def new_schema_partial_text() -> str:
    """A partial override already using the new 2.x schema (for idempotency tests)."""
    return dedent("""\
        global:
          baseDomain: mycompany.astronomer.io
          rbac:
            enabled: true
          scc:
            enabled: false
          openshift:
            enabled: false
          networkNSLabels:
            enabled: true
          namespaceManagement:
            namespaceFreeFormEntry:
              enabled: true
            namespacePools:
              enabled: true
              createRbac: true
          metricsReporting:
            taskUsageMetrics:
              enabled: true
          deploymentLifecycle:
            deployRollback:
              enabled: false
          deployMechanisms:
            dagOnlyDeployment:
              enabled: true
              repository: quay.io/astronomer/ap-dag-deploy
              tag: 0.9.3
          logging:
            loggingSidecar:
              enabled: true
              name: sidecar-log-consumer
    """)


@pytest.fixture()
def old_full_values_text() -> str:
    """Load the pinned 1.x full values.yaml fixture."""
    return (FIXTURES_DIR / "old-1x-values.yaml").read_text()


@pytest.fixture()
def new_full_values_text() -> str:
    """Load the current values.yaml from disk (new 2.x schema)."""
    return (REPO_ROOT / "values.yaml").read_text()
