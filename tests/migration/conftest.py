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
          podDisruptionBudgetsEnabled: true
          postgresqlEnabled: false
          prometheusPostgresExporterEnabled: false
          manualNamespaceNamesEnabled: false
          enablePerHostIngress: false
          enableArgoCDAnnotation: false
          disableManageClusterScopedResources: false
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
            config:
              deployments:
                dagProcessorEnabled: true
                triggererEnabled: true
                configureDagDeployment: true
                gitSyncDagDeployment: true
                nfsMountDagDeployment: true
                enableListAllRuntimeVersions: true
                enableUpdateDeploymentImageEndpoint: true
                grafanaUIEnabled: true
                hardDeleteDeployment: true
                logHelmValues: true
                manualReleaseNames: false
                pgBouncerResourceCalculationStrategy: airflowStratV2
                serviceAccountAnnotationKey: eks.amazonaws.com/role-arn
                astroUnitsEnabled: false
                resourceProvisioningStrategy:
                  astroUnitsEnabled: false
                maxPodAu: 100
                upsertDeploymentEnabled: true
                canUpsertDeploymentFromUI: true
                enableSystemAdminCanCreateDeprecatedAirflows: false
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
          podDisruptionBudgets:
            enabled: true
          postgresql:
            enabled: false
          prometheusPostgresExporter:
            enabled: false
          perHostIngress:
            enabled: false
          argoCD:
            annotation:
              enabled: false
          manageClusterScopedResources:
            enabled: true
          namespaceManagement:
            namespaceFreeFormEntry:
              enabled: true
            manualNamespaceNames:
              enabled: false
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
            config:
              deployments:
                airflowComponents:
                  dagProcessor:
                    enabled: true
                  triggerer:
                    enabled: true
                deployMechanisms:
                  configureDagDeployment:
                    enabled: true
                  gitSyncDagDeployment:
                    enabled: true
                  nfsMountDagDeployment:
                    enabled: true
                runtimeManagement:
                  listAllRuntimeVersions:
                    enabled: true
                deploymentImagesRegistry:
                  updateDeploymentImageEndpoint:
                    enabled: true
                  serviceAccountAnnotationKey: eks.amazonaws.com/role-arn
                metricsReporting:
                  grafana:
                    enabled: true
                deploymentLifecycle:
                  hardDeleteDeployment:
                    enabled: true
                logHelmValues:
                  enabled: true
                namespaceManagement:
                  manualReleaseNames:
                    enabled: false
                databaseManagement:
                  pgBouncerResourceCalculationStrategy: airflowStratV2
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
          podDisruptionBudgets:
            enabled: true
          postgresql:
            enabled: false
          prometheusPostgresExporter:
            enabled: false
          perHostIngress:
            enabled: false
          argoCD:
            annotation:
              enabled: false
          manageClusterScopedResources:
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

        astronomer:
          houston:
            config:
              deployments:
                airflowComponents:
                  dagProcessor:
                    enabled: true
                  triggerer:
                    enabled: true
                deployMechanisms:
                  configureDagDeployment:
                    enabled: true
                logHelmValues:
                  enabled: true
    """)


@pytest.fixture()
def old_full_values_text() -> str:
    """Load the pinned 1.x full values.yaml fixture."""
    return (FIXTURES_DIR / "old-1x-values.yaml").read_text()


@pytest.fixture()
def new_full_values_text() -> str:
    """Load the current values.yaml from disk (new 2.x schema)."""
    return (REPO_ROOT / "values.yaml").read_text()


# ---------------------------------------------------------------------------
# 0.37.x -> 2.x migration fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def old_037x_full_values_text() -> str:
    """Load the pinned 0.37.x full values.yaml fixture."""
    return (FIXTURES_DIR / "old-037x-values.yaml").read_text()


@pytest.fixture()
def old_037x_partial_override_text() -> str:
    """A realistic customer partial override using the old 0.37.x schema.

    Includes all key categories that need migration: flat booleans, subtrees,
    obsolete keys (stan, kibana, fluentd, blackbox), pgbouncer with old key
    names, and NATS with jetStream disabled.
    """
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
          podDisruptionBudgetsEnabled: true
          postgresqlEnabled: false
          prometheusPostgresExporterEnabled: false
          manualNamespaceNamesEnabled: false
          enablePerHostIngress: false
          enableArgoCDAnnotation: false
          disableManageClusterScopedResources: false
          singleNamespace: true
          veleroEnabled: true
          enableHoustonInternalAuthorization: true
          nodeExporterSccEnabled: true
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
          stan:
            enabled: true
            replicas: 3
          nats:
            enabled: true
            replicas: 3
            jetStream:
              enabled: false
              tls: false
          pgbouncer:
            enabled: true
            gssSupport: true
            krb5ConfSecretName: my-krb5-secret
            servicePort: "5432"

        tags:
          platform: true
          monitoring: true
          logging: true
          stan: true

        astronomer:
          houston:
            resources:
              requests:
                cpu: "1000m"
            config:
              deployments:
                dagProcessorEnabled: true
                triggererEnabled: true
                configureDagDeployment: true
                gitSyncDagDeployment: true
                nfsMountDagDeployment: true
                enableListAllRuntimeVersions: true
                enableUpdateDeploymentImageEndpoint: true
                grafanaUIEnabled: true
                hardDeleteDeployment: true
                logHelmValues: true
                manualReleaseNames: false
                pgBouncerResourceCalculationStrategy: airflowStratV2
                serviceAccountAnnotationKey: eks.amazonaws.com/role-arn
                astroUnitsEnabled: false
                resourceProvisioningStrategy:
                  astroUnitsEnabled: false
                maxPodAu: 100
                upsertDeploymentEnabled: true
                canUpsertDeploymentFromUI: true
                enableSystemAdminCanCreateDeprecatedAirflows: false

        stan:
          stan:
            resources:
              requests:
                cpu: "100m"

        kibana:
          resources:
            requests:
              cpu: "250m"

        fluentd:
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "1000m"
              memory: "2Gi"

        prometheus-blackbox-exporter:
          resources:
            requests:
              cpu: "50m"
    """)


@pytest.fixture()
def expected_037x_new_partial_text() -> str:
    """Expected output after migrating old_037x_partial_override."""
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
          podDisruptionBudgets:
            enabled: true
          postgresql:
            enabled: false
          prometheusPostgresExporter:
            enabled: false
          perHostIngress:
            enabled: false
          argoCD:
            annotation:
              enabled: false
          manageClusterScopedResources:
            enabled: true
          namespaceManagement:
            namespaceFreeFormEntry:
              enabled: true
            manualNamespaceNames:
              enabled: false
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
            provider:
          nats:
            enabled: true
            replicas: 3
            jetStream:
              enabled: true
              tls: false
          pgbouncer:
            enabled: true
            gssSupport: true
            secretName: my-krb5-secret
            servicePort: "6543"
          authHeaderSecretName:
          plane:
            mode: unified
            domainPrefix: ''
          podLabels: {}

        tags:
          platform: true
          monitoring: true
          logging: true

        astronomer:
          houston:
            resources:
              requests:
                cpu: "1000m"
            config:
              deployments:
                airflowComponents:
                  dagProcessor:
                    enabled: true
                  triggerer:
                    enabled: true
                deployMechanisms:
                  configureDagDeployment:
                    enabled: true
                  gitSyncDagDeployment:
                    enabled: true
                  nfsMountDagDeployment:
                    enabled: true
                runtimeManagement:
                  listAllRuntimeVersions:
                    enabled: true
                deploymentImagesRegistry:
                  updateDeploymentImageEndpoint:
                    enabled: true
                  serviceAccountAnnotationKey: eks.amazonaws.com/role-arn
                metricsReporting:
                  grafana:
                    enabled: true
                deploymentLifecycle:
                  hardDeleteDeployment:
                    enabled: true
                namespaceManagement:
                  manualReleaseNames:
                    enabled: false
                databaseManagement:
                  pgBouncerResourceCalculationStrategy: airflowStratV2

        vector:
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "1000m"
              memory: "2Gi"

        nats:
          init:
            resources:
              requests:
                cpu: 75m
                memory: 30Mi
              limits:
                cpu: 250m
                memory: 100Mi
    """)


@pytest.fixture()
def new_037x_schema_partial_text() -> str:
    """A partial override already using the new 2.x schema (for 0.37.x idempotency tests)."""
    return dedent("""\
        global:
          baseDomain: mycompany.astronomer.io
          authHeaderSecretName: my-secret
          plane:
            mode: unified
            domainPrefix: cluster-1
          podLabels:
            team: data
          rbac:
            enabled: true
          scc:
            enabled: false
          openshift:
            enabled: false
          networkNSLabels:
            enabled: true
          podDisruptionBudgets:
            enabled: true
          postgresql:
            enabled: false
          prometheusPostgresExporter:
            enabled: false
          perHostIngress:
            enabled: false
          argoCD:
            annotation:
              enabled: false
          manageClusterScopedResources:
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
            provider: elasticsearch
          nats:
            enabled: true
            replicas: 3
            jetStream:
              enabled: true
              tls: false
          pgbouncer:
            enabled: true
            gssSupport: true
            secretName: astronomer-pgbouncer-config
            servicePort: "6543"

        astronomer:
          houston:
            config:
              deployments:
                airflowComponents:
                  dagProcessor:
                    enabled: true
                  triggerer:
                    enabled: true

        tags:
          platform: true
          monitoring: true
          logging: true

        vector:
          resources:
            requests:
              cpu: "250m"

        nats:
          init:
            resources:
              requests:
                cpu: "75m"
    """)
