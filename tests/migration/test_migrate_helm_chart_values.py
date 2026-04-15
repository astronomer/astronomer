"""Tests for bin/migrate-helm-chart-values-1x-to-2x.py migration script."""

from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path
from textwrap import dedent

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT_PATH = REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"
_spec = importlib.util.spec_from_file_location("migrate_helm_chart_values_1x_to_2x", _SCRIPT_PATH)
migrate_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migrate_mod
_spec.loader.exec_module(migrate_mod)
migrate_values = migrate_mod.migrate_values
BoolToNested = migrate_mod.BoolToNested
SubtreeMove = migrate_mod.SubtreeMove
MIGRATIONS = migrate_mod.MIGRATIONS
HOUSTON_DEPLOYMENT_MIGRATIONS = migrate_mod.HOUSTON_DEPLOYMENT_MIGRATIONS
main = migrate_mod.main


def _load_rt(text: str):
    """Load YAML text with round-trip mode."""
    yml = YAML(typ="rt")
    return yml.load(StringIO(text))


def _dump_rt(data) -> str:
    """Dump YAML data to string with round-trip mode."""
    yml = YAML(typ="rt")
    stream = StringIO()
    yml.dump(data, stream)
    return stream.getvalue()


def _to_plain(data) -> dict:
    """Convert CommentedMap to a plain dict recursively for comparison."""
    yml_rt = YAML(typ="rt")
    yml_safe = YAML(typ="safe")
    stream = StringIO()
    yml_rt.dump(data, stream)
    stream.seek(0)
    return yml_safe.load(stream)


# ---------------------------------------------------------------------------
# Correctness tests
# ---------------------------------------------------------------------------


class TestPartialOverrideMigration:
    """Test migration of a realistic customer partial override."""

    def test_partial_override_migration(
        self,
        old_partial_override_text: str,
        expected_new_partial_text: str,
    ):
        """Converting a partial override with all old keys produces the expected new structure."""
        data = _load_rt(old_partial_override_text)
        changes = migrate_values(data)
        result = _to_plain(data)
        expected = _to_plain(_load_rt(expected_new_partial_text))

        assert result == expected
        assert len(changes) == 36

    def test_non_global_sections_preserved(self, old_partial_override_text: str):
        """Sections outside global (astronomer, nginx, etc.) are not modified."""
        data = _load_rt(old_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["astronomer"]["houston"]["resources"]["requests"]["cpu"] == "1000m"

    def test_unrelated_global_keys_preserved(self, old_partial_override_text: str):
        """Keys like baseDomain inside global are untouched."""
        data = _load_rt(old_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["baseDomain"] == "mycompany.astronomer.io"


class TestFullValuesMigration:
    """Test migration of the complete old values.yaml from master."""

    def test_full_values_migration_feature_flags(self, old_full_values_text: str):
        """Migrating old full values.yaml produces correct feature flag paths."""
        data = _load_rt(old_full_values_text)
        changes = migrate_values(data)
        g = _to_plain(data)["global"]

        assert g["rbac"]["enabled"] is True
        assert g["scc"]["enabled"] is False
        assert g["openshift"]["enabled"] is False
        assert g["networkNSLabels"]["enabled"] is False
        assert g["namespaceManagement"]["namespaceFreeFormEntry"]["enabled"] is False
        assert g["namespaceManagement"]["namespacePools"]["enabled"] is False
        assert g["namespaceManagement"]["namespacePools"]["createRbac"] is True
        assert g["metricsReporting"]["taskUsageMetrics"]["enabled"] is False
        assert g["deploymentLifecycle"]["deployRollback"]["enabled"] is False
        assert g["deployMechanisms"]["dagOnlyDeployment"]["enabled"] is False
        assert g["deployMechanisms"]["dagOnlyDeployment"]["repository"] == "quay.io/astronomer/ap-dag-deploy"
        assert g["logging"]["loggingSidecar"]["enabled"] is False
        assert g["logging"]["loggingSidecar"]["name"] == "sidecar-log-consumer"
        assert g["podDisruptionBudgets"]["enabled"] is True
        assert g["postgresql"]["enabled"] is False
        assert g["prometheusPostgresExporter"]["enabled"] is False
        assert g["namespaceManagement"]["manualNamespaceNames"]["enabled"] is False
        assert g["perHostIngress"]["enabled"] is False
        assert g["argoCD"]["annotation"]["enabled"] is False
        assert g["manageClusterScopedResources"]["enabled"] is True
        assert len(changes) == 36

    def test_houston_config_migrated(self, old_full_values_text: str):
        """Houston config deployment flags are restructured and obsolete keys deleted."""
        data = _load_rt(old_full_values_text)
        migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert deployments["airflowComponents"]["triggerer"]["enabled"] is True
        assert deployments["deployMechanisms"]["configureDagDeployment"]["enabled"] is True
        assert deployments["logHelmValues"]["enabled"] is False
        assert "dagProcessorEnabled" not in deployments
        assert "triggererEnabled" not in deployments
        assert "configureDagDeployment" not in deployments
        assert "grafanaUIEnabled" not in deployments
        assert "astroUnitsEnabled" not in deployments
        assert "resourceProvisioningStrategy" not in deployments
        assert "maxPodAu" not in deployments
        assert "upsertDeploymentEnabled" not in deployments
        assert "canUpsertDeploymentFromUI" not in deployments
        assert "enableSystemAdminCanCreateDeprecatedAirflows" not in deployments

    def test_old_keys_removed_after_migration(self, old_full_values_text: str):
        """Old flat keys no longer exist at the global root after migration."""
        data = _load_rt(old_full_values_text)
        migrate_values(data)
        g = _to_plain(data)["global"]

        old_keys = [
            "rbacEnabled",
            "sccEnabled",
            "openshiftEnabled",
            "namespaceFreeFormEntry",
            "taskUsageMetricsEnabled",
            "deployRollbackEnabled",
            "dagOnlyDeployment",
            "loggingSidecar",
            "podDisruptionBudgetsEnabled",
            "postgresqlEnabled",
            "prometheusPostgresExporterEnabled",
            "nodeExporterEnabled",
            "fluentdEnabled",
            "manualNamespaceNamesEnabled",
            "enablePerHostIngress",
            "enableArgoCDAnnotation",
            "disableManageClusterScopedResources",
        ]
        for key in old_keys:
            assert key not in g, f"Old key '{key}' should have been removed from global"

        assert "features" not in g, "Empty 'features' key should have been cleaned up"

    def test_unchanged_keys_preserved(self, old_full_values_text: str):
        """Keys that are already in the correct format are not modified."""
        data = _load_rt(old_full_values_text)
        migrate_values(data)
        g = _to_plain(data)["global"]

        assert g["networkPolicy"]["enabled"] is True
        assert g["authSidecar"]["enabled"] is False
        assert g["airflowOperator"]["enabled"] is False
        assert g["nats"]["enabled"] is True


# ---------------------------------------------------------------------------
# Individual rule tests
# ---------------------------------------------------------------------------


class TestBoolToNested:
    """Test the BoolToNested rule type."""

    @pytest.mark.parametrize("value", [True, False])
    def test_bool_to_nested(self, value: bool):
        """BoolToNested correctly moves a boolean to a nested .enabled key."""
        data = _load_rt(f"global:\n  rbacEnabled: {str(value).lower()}\n")
        rule = BoolToNested("rbacEnabled", ["rbac", "enabled"])
        changes = rule.apply(data["global"])

        result = _to_plain(data)
        assert result["global"]["rbac"]["enabled"] is value
        assert "rbacEnabled" not in result["global"]
        assert len(changes) == 1
        assert changes[0].old_path == "global.rbacEnabled"
        assert changes[0].new_path == "global.rbac.enabled"

    def test_bool_to_deeply_nested(self):
        """BoolToNested handles multi-level nesting like namespaceManagement.namespaceFreeFormEntry.enabled."""
        data = _load_rt("global:\n  namespaceFreeFormEntry: true\n")
        rule = BoolToNested("namespaceFreeFormEntry", ["namespaceManagement", "namespaceFreeFormEntry", "enabled"])
        changes = rule.apply(data["global"])

        result = _to_plain(data)
        assert result["global"]["namespaceManagement"]["namespaceFreeFormEntry"]["enabled"] is True
        assert "namespaceFreeFormEntry" not in result["global"]
        assert len(changes) == 1

    def test_bool_to_nested_missing_key(self):
        """BoolToNested does nothing when the old key is absent."""
        data = _load_rt("global:\n  baseDomain: example.com\n")
        rule = BoolToNested("rbacEnabled", ["rbac", "enabled"])
        changes = rule.apply(data["global"])

        result = _to_plain(data)
        assert "rbac" not in result["global"]
        assert len(changes) == 0

    def test_networkNSLabels_special_case(self):
        """networkNSLabels reuses the same name for the parent key."""
        data = _load_rt("global:\n  networkNSLabels: true\n")
        rule = BoolToNested("networkNSLabels", ["networkNSLabels", "enabled"])
        changes = rule.apply(data["global"])

        result = _to_plain(data)
        assert result["global"]["networkNSLabels"]["enabled"] is True
        assert len(changes) == 1


class TestNginxCspPolicyMigration:
    """Legacy CSP toggle shapes -> `nginx.cspPolicy.enabled`."""

    def test_migrates_cdnEnabled_to_flat_enabled(self) -> None:
        """Full migrate_values rewrites flat cdnEnabled -> cspPolicy.enabled."""
        data = _load_rt(
            dedent("""\
                nginx:
                  cspPolicy:
                    cdnEnabled: false
                    connectsrc: "cdn.example.com"
            """)
        )
        changes = migrate_values(data)
        result = _to_plain(data)
        assert result["nginx"]["cspPolicy"]["enabled"] is False
        assert "cdnEnabled" not in result["nginx"]["cspPolicy"]
        assert "cdn" not in result["nginx"]["cspPolicy"]
        assert result["nginx"]["cspPolicy"]["connectsrc"] == "cdn.example.com"
        assert any(c.old_path == "nginx.cspPolicy.cdnEnabled" and c.new_path == "nginx.cspPolicy.enabled" for c in changes)

    def test_no_op_when_csp_policy_missing(self) -> None:
        """No nginx.cspPolicy section produces no nginx CSP migration changes."""
        data = _load_rt("nginx:\n  replicas: 2\n")
        changes = migrate_values(data)
        assert _to_plain(data)["nginx"]["replicas"] == 2
        assert not any("nginx.cspPolicy" in c.old_path for c in changes)

    def test_idempotent_when_already_flat_enabled(self) -> None:
        """Second migration pass does not alter already-flat cspPolicy.enabled."""
        data = _load_rt(
            dedent("""\
                nginx:
                  cspPolicy:
                    enabled: true
                    connectsrc: "x"
            """)
        )
        migrate_values(data)
        plain_after_first = _to_plain(data)
        data2 = _load_rt(_dump_rt(data))
        changes2 = migrate_values(data2)
        assert _to_plain(data2) == plain_after_first
        assert not any("nginx.cspPolicy" in c.old_path for c in changes2)


class TestSubtreeMove:
    """Test the SubtreeMove rule type."""

    def test_subtree_move_preserves_all_children(self):
        """SubtreeMove keeps all nested keys intact."""
        data = _load_rt(
            dedent("""\
            global:
              dagOnlyDeployment:
                enabled: true
                repository: custom/repo
                tag: 1.0.0
                securityContexts:
                  pod:
                    fsGroup: 50000
        """)
        )
        rule = SubtreeMove(["dagOnlyDeployment"], ["deployMechanisms", "dagOnlyDeployment"])
        changes = rule.apply(data["global"])

        result = _to_plain(data)
        dag = result["global"]["deployMechanisms"]["dagOnlyDeployment"]
        assert dag["enabled"] is True
        assert dag["repository"] == "custom/repo"
        assert dag["tag"] == "1.0.0"
        assert dag["securityContexts"]["pod"]["fsGroup"] == 50000
        assert "dagOnlyDeployment" not in result["global"]
        assert len(changes) == 1

    def test_features_namespace_pools_move(self):
        """Moving features.namespacePools cleans up the empty features key."""
        data = _load_rt(
            dedent("""\
            global:
              features:
                namespacePools:
                  enabled: true
                  createRbac: true
                  namespaces:
                    create: true
                    names:
                    - ns1
                    - ns2
        """)
        )
        rule = SubtreeMove(["features", "namespacePools"], ["namespaceManagement", "namespacePools"])
        changes = rule.apply(data["global"])

        result = _to_plain(data)
        ns = result["global"]["namespaceManagement"]["namespacePools"]
        assert ns["enabled"] is True
        assert ns["createRbac"] is True
        assert ns["namespaces"]["names"] == ["ns1", "ns2"]
        assert "features" not in result["global"]
        assert len(changes) == 1

    def test_subtree_move_missing_source(self):
        """SubtreeMove does nothing when the source path doesn't exist."""
        data = _load_rt("global:\n  baseDomain: example.com\n")
        rule = SubtreeMove(["dagOnlyDeployment"], ["deployMechanisms", "dagOnlyDeployment"])
        changes = rule.apply(data["global"])

        result = _to_plain(data)
        assert "deployMechanisms" not in result["global"]
        assert len(changes) == 0

    def test_logging_sidecar_move(self):
        """loggingSidecar moves under logging correctly."""
        data = _load_rt(
            dedent("""\
            global:
              loggingSidecar:
                enabled: true
                name: my-sidecar
                resources:
                  requests:
                    cpu: 100m
        """)
        )
        rule = SubtreeMove(["loggingSidecar"], ["logging", "loggingSidecar"])
        rule.apply(data["global"])

        result = _to_plain(data)
        ls = result["global"]["logging"]["loggingSidecar"]
        assert ls["enabled"] is True
        assert ls["name"] == "my-sidecar"
        assert ls["resources"]["requests"]["cpu"] == "100m"
        assert "loggingSidecar" not in result["global"]

    def test_logging_sidecar_merges_with_existing_logging(self):
        """When global.logging already exists, loggingSidecar is added alongside."""
        data = _load_rt(
            dedent("""\
            global:
              logging:
                indexNamePrefix: my-prefix
              loggingSidecar:
                enabled: true
                name: my-sidecar
        """)
        )
        rule = SubtreeMove(["loggingSidecar"], ["logging", "loggingSidecar"])
        rule.apply(data["global"])

        result = _to_plain(data)
        assert result["global"]["logging"]["indexNamePrefix"] == "my-prefix"
        assert result["global"]["logging"]["loggingSidecar"]["enabled"] is True
        assert result["global"]["logging"]["loggingSidecar"]["name"] == "my-sidecar"
        assert "loggingSidecar" not in result["global"]


# ---------------------------------------------------------------------------
# Parametrized test over all migration rules
# ---------------------------------------------------------------------------


RULE_TEST_CASES = [
    (
        "rbacEnabled",
        "global:\n  rbacEnabled: true\n",
        lambda g: g["rbac"]["enabled"] is True,
    ),
    (
        "sccEnabled",
        "global:\n  sccEnabled: false\n",
        lambda g: g["scc"]["enabled"] is False,
    ),
    (
        "openshiftEnabled",
        "global:\n  openshiftEnabled: true\n",
        lambda g: g["openshift"]["enabled"] is True,
    ),
    (
        "networkNSLabels",
        "global:\n  networkNSLabels: true\n",
        lambda g: g["networkNSLabels"]["enabled"] is True,
    ),
    (
        "namespaceFreeFormEntry",
        "global:\n  namespaceFreeFormEntry: false\n",
        lambda g: g["namespaceManagement"]["namespaceFreeFormEntry"]["enabled"] is False,
    ),
    (
        "taskUsageMetricsEnabled",
        "global:\n  taskUsageMetricsEnabled: true\n",
        lambda g: g["metricsReporting"]["taskUsageMetrics"]["enabled"] is True,
    ),
    (
        "deployRollbackEnabled",
        "global:\n  deployRollbackEnabled: false\n",
        lambda g: g["deploymentLifecycle"]["deployRollback"]["enabled"] is False,
    ),
    (
        "features.namespacePools",
        "global:\n  features:\n    namespacePools:\n      enabled: true\n      createRbac: true\n",
        lambda g: (
            g["namespaceManagement"]["namespacePools"]["enabled"] is True
            and g["namespaceManagement"]["namespacePools"]["createRbac"] is True
        ),
    ),
    (
        "dagOnlyDeployment",
        "global:\n  dagOnlyDeployment:\n    enabled: true\n    repository: test/repo\n",
        lambda g: (
            g["deployMechanisms"]["dagOnlyDeployment"]["enabled"] is True
            and g["deployMechanisms"]["dagOnlyDeployment"]["repository"] == "test/repo"
        ),
    ),
    (
        "loggingSidecar",
        "global:\n  loggingSidecar:\n    enabled: true\n    name: test-sidecar\n",
        lambda g: g["logging"]["loggingSidecar"]["enabled"] is True and g["logging"]["loggingSidecar"]["name"] == "test-sidecar",
    ),
    (
        "podDisruptionBudgetsEnabled",
        "global:\n  podDisruptionBudgetsEnabled: true\n",
        lambda g: g["podDisruptionBudgets"]["enabled"] is True,
    ),
    (
        "postgresqlEnabled",
        "global:\n  postgresqlEnabled: false\n",
        lambda g: g["postgresql"]["enabled"] is False,
    ),
    (
        "prometheusPostgresExporterEnabled",
        "global:\n  prometheusPostgresExporterEnabled: false\n",
        lambda g: g["prometheusPostgresExporter"]["enabled"] is False,
    ),
    (
        "nodeExporterEnabled",
        "global:\n  nodeExporterEnabled: true\n",
        lambda g: g["nodeExporter"]["enabled"] is True,
    ),
    (
        "fluentdEnabled",
        "global:\n  fluentdEnabled: false\n",
        lambda g: g["daemonsetLogging"]["enabled"] is False and "fluentdEnabled" not in g,
    ),
    (
        "manualNamespaceNamesEnabled",
        "global:\n  manualNamespaceNamesEnabled: false\n",
        lambda g: g["namespaceManagement"]["manualNamespaceNames"]["enabled"] is False,
    ),
    (
        "enablePerHostIngress",
        "global:\n  enablePerHostIngress: false\n",
        lambda g: g["perHostIngress"]["enabled"] is False,
    ),
    (
        "enableArgoCDAnnotation",
        "global:\n  enableArgoCDAnnotation: false\n",
        lambda g: g["argoCD"]["annotation"]["enabled"] is False,
    ),
    (
        "disableManageClusterScopedResources",
        "global:\n  disableManageClusterScopedResources: false\n",
        lambda g: g["manageClusterScopedResources"]["enabled"] is True,
    ),
    (
        "vectorEnabled",
        "global:\n  vectorEnabled: true\n",
        lambda g: g["daemonsetLogging"]["enabled"] is True and "vectorEnabled" not in g,
    ),
]


class TestEachMigrationRule:
    """Parametrized test over each migration rule in isolation."""

    @pytest.mark.parametrize(
        "rule_name,yaml_input,check_fn",
        RULE_TEST_CASES,
        ids=[case[0] for case in RULE_TEST_CASES],
    )
    def test_individual_rule(self, rule_name: str, yaml_input: str, check_fn):
        """Each migration rule transforms its input correctly."""
        data = _load_rt(yaml_input)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert len(changes) >= 1, f"Rule {rule_name} should have produced at least 1 change"
        assert check_fn(result["global"]), f"Rule {rule_name} did not produce the expected output"


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Verify running migration on already-migrated data is a no-op."""

    def test_idempotent_already_migrated(self, old_partial_override_text: str):
        """Running migration twice produces the same result."""
        data = _load_rt(old_partial_override_text)
        migrate_values(data)
        first_pass = _dump_rt(data)

        data2 = _load_rt(first_pass)
        changes = migrate_values(data2)
        second_pass = _dump_rt(data2)

        assert first_pass == second_pass
        assert len(changes) == 0

    def test_idempotent_new_schema_input(self, new_schema_partial_text: str):
        """Running migration on new-schema values makes no changes."""
        data = _load_rt(new_schema_partial_text)
        original = _dump_rt(data)

        changes = migrate_values(data)
        after = _dump_rt(data)

        assert original == after
        assert len(changes) == 0


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases that should not break the migration."""

    def test_empty_file(self):
        """Empty YAML file (None document) returns no changes."""
        data = _load_rt("")
        changes = migrate_values(data)
        assert len(changes) == 0

    def test_no_global_section(self):
        """YAML without a global key passes through unchanged."""
        text = "astronomer:\n  houston:\n    replicas: 3\n"
        data = _load_rt(text)
        changes = migrate_values(data)

        result = _to_plain(data)
        assert result["astronomer"]["houston"]["replicas"] == 3
        assert len(changes) == 0

    def test_mixed_old_and_new_keys(self):
        """File with some old keys and some new keys migrates only the old ones."""
        text = dedent("""\
            global:
              rbacEnabled: true
              scc:
                enabled: false
              openshiftEnabled: true
              networkNSLabels:
                enabled: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["rbac"]["enabled"] is True
        assert result["global"]["scc"]["enabled"] is False
        assert result["global"]["openshift"]["enabled"] is True
        assert result["global"]["networkNSLabels"]["enabled"] is True
        assert "rbacEnabled" not in result["global"]
        assert "openshiftEnabled" not in result["global"]
        assert len(changes) == 2

    def test_global_section_empty(self):
        """global section that is empty does not crash."""
        data = _load_rt("global: {}\n")
        changes = migrate_values(data)
        assert len(changes) == 0

    def test_global_section_null(self):
        """global section set to null does not crash."""
        data = _load_rt("global:\n")
        changes = migrate_values(data)
        assert len(changes) == 0

    def test_only_unrelated_global_keys(self):
        """global section with only unrelated keys is not modified."""
        text = dedent("""\
            global:
              baseDomain: example.com
              tlsSecret: my-secret
              privateCaCerts: []
        """)
        data = _load_rt(text)
        original = _dump_rt(data)
        changes = migrate_values(data)
        after = _dump_rt(data)

        assert original == after
        assert len(changes) == 0

    def test_features_with_extra_keys_not_deleted(self):
        """If features has keys besides namespacePools, features is kept."""
        text = dedent("""\
            global:
              features:
                namespacePools:
                  enabled: true
                someOtherFeature:
                  enabled: false
        """)
        data = _load_rt(text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["namespaceManagement"]["namespacePools"]["enabled"] is True
        assert result["global"]["features"]["someOtherFeature"]["enabled"] is False


# ---------------------------------------------------------------------------
# Conflict / precedence tests
# ---------------------------------------------------------------------------


class TestConflictPrecedence:
    """When both old and new keys exist, new-schema values take precedence."""

    def test_bool_to_nested_keeps_new_value(self):
        """BoolToNested preserves the existing new-schema value and removes the old key."""
        text = dedent("""\
            global:
              rbacEnabled: true
              rbac:
                enabled: false
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["rbac"]["enabled"] is False
        assert "rbacEnabled" not in result["global"]
        assert len(changes) >= 1

    def test_bool_to_nested_deeply_nested_keeps_new(self):
        """BoolToNested for a deep path preserves the existing new-schema value."""
        text = dedent("""\
            global:
              namespaceFreeFormEntry: true
              namespaceManagement:
                namespaceFreeFormEntry:
                  enabled: false
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["namespaceManagement"]["namespaceFreeFormEntry"]["enabled"] is False
        assert "namespaceFreeFormEntry" not in result["global"]
        assert len(changes) >= 1

    def test_subtree_move_keeps_new_subtree(self):
        """SubtreeMove preserves the existing new-location subtree and removes the old one."""
        text = dedent("""\
            global:
              dagOnlyDeployment:
                enabled: true
                repository: old/repo
              deployMechanisms:
                dagOnlyDeployment:
                  enabled: false
                  repository: new/repo
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        dag = result["global"]["deployMechanisms"]["dagOnlyDeployment"]
        assert dag["enabled"] is False
        assert dag["repository"] == "new/repo"
        assert "dagOnlyDeployment" not in result["global"]
        assert len(changes) >= 1

    def test_subtree_move_features_keeps_new_namespace_pools(self):
        """SubtreeMove for features.namespacePools preserves the new-location value."""
        text = dedent("""\
            global:
              features:
                namespacePools:
                  enabled: true
                  createRbac: false
              namespaceManagement:
                namespacePools:
                  enabled: false
                  createRbac: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        ns = result["global"]["namespaceManagement"]["namespacePools"]
        assert ns["enabled"] is False
        assert ns["createRbac"] is True
        assert "features" not in result["global"]
        assert len(changes) >= 1

    def test_logging_sidecar_conflict_keeps_new(self):
        """SubtreeMove for loggingSidecar preserves the new-location subtree."""
        text = dedent("""\
            global:
              loggingSidecar:
                enabled: true
                name: old-sidecar
              logging:
                loggingSidecar:
                  enabled: false
                  name: new-sidecar
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        ls = result["global"]["logging"]["loggingSidecar"]
        assert ls["enabled"] is False
        assert ls["name"] == "new-sidecar"
        assert "loggingSidecar" not in result["global"]
        assert len(changes) >= 1

    def test_mixed_conflicts_and_normal_migrations(self):
        """A file with some conflicts and some normal migrations handles both correctly."""
        text = dedent("""\
            global:
              rbacEnabled: true
              rbac:
                enabled: false
              sccEnabled: true
              openshiftEnabled: false
              openshift:
                enabled: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["rbac"]["enabled"] is False
        assert result["global"]["scc"]["enabled"] is True
        assert result["global"]["openshift"]["enabled"] is True
        assert "rbacEnabled" not in result["global"]
        assert "sccEnabled" not in result["global"]
        assert "openshiftEnabled" not in result["global"]
        assert len(changes) == 3

    def test_vector_enabled_conflict_keeps_new(self):
        """vectorEnabled conflict with loggingDaemonset.enabled preserves the new-schema value."""
        text = dedent("""\
            global:
              vectorEnabled: true
              daemonsetLogging:
                enabled: false
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["daemonsetLogging"]["enabled"] is False
        assert "vectorEnabled" not in result["global"]
        assert len(changes) >= 1

    def test_fluentd_enabled_conflict_keeps_new(self):
        """fluentdEnabled conflict with daemonsetLogging.enabled preserves the new-schema value."""
        text = dedent("""\
            global:
              fluentdEnabled: true
              daemonsetLogging:
                enabled: false
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["daemonsetLogging"]["enabled"] is False
        assert "fluentdEnabled" not in result["global"]
        assert len(changes) >= 1


# ---------------------------------------------------------------------------
# Comment preservation tests
# ---------------------------------------------------------------------------


class TestCommentPreservation:
    """Verify that ruamel.yaml round-trip preserves comments."""

    def test_comments_preserved_on_untouched_keys(self):
        """Comments on keys not touched by migration survive."""
        text = dedent("""\
            global:
              # Base domain comment
              baseDomain: example.com  # inline comment
              rbacEnabled: true
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# Base domain comment" in output
        assert "# inline comment" in output

    def test_block_comments_preserved(self):
        """Multi-line block comments near migrated keys survive."""
        text = dedent("""\
            global:
              # This is a multi-line comment
              # about the RBAC setting
              rbacEnabled: true
              baseDomain: example.com
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# This is a multi-line comment" in output
        assert "# about the RBAC setting" in output

    def test_comments_preserved_on_untouched_sections(self):
        """Inline comments on sections outside global are preserved."""
        text = dedent("""\
            global:
              rbacEnabled: true
            astronomer:
              houston:
                replicas: 3  # scale up
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# scale up" in output

    def test_inline_comment_transferred_on_bool_to_nested(self):
        """Inline comment on a renamed BoolToNested key transfers to the new leaf key."""
        text = dedent("""\
            global:
              rbacEnabled: true  # Enable RBAC
              baseDomain: example.com
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# Enable RBAC" in output
        assert "rbacEnabled" not in output

    def test_inline_comment_on_self_rename_preserved(self):
        """Inline comment survives when key name stays the same (networkNSLabels)."""
        text = dedent("""\
            global:
              networkNSLabels: true  # NS labels
              baseDomain: example.com
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# NS labels" in output
        assert "networkNSLabels:" in output

    def test_inline_comment_on_subtree_move_preserved(self):
        """Inline comment on a subtree top-level key survives the move."""
        text = dedent("""\
            global:
              dagOnlyDeployment:  # DAG deploy config
                enabled: true
                repository: test/repo  # custom repo
              baseDomain: example.com
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# DAG deploy config" in output
        assert "# custom repo" in output
        assert "deployMechanisms" in output

    def test_multiple_inline_comments_transferred(self):
        """Inline comments on multiple BoolToNested keys all transfer."""
        text = dedent("""\
            global:
              rbacEnabled: true  # RBAC comment
              sccEnabled: false  # SCC comment
              openshiftEnabled: true  # OpenShift comment
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# RBAC comment" in output
        assert "# SCC comment" in output
        assert "# OpenShift comment" in output


# ---------------------------------------------------------------------------
# Houston config deployment flag tests
# ---------------------------------------------------------------------------


class TestHoustonDeploymentMigration:
    """Test migration of houston config deployment flags."""

    def test_dag_processor_enabled_migrated(self):
        """dagProcessorEnabled is moved to airflowComponents.dagProcessor.enabled."""
        text = dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    dagProcessorEnabled: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert "dagProcessorEnabled" not in deployments
        assert len(changes) == 1

    def test_triggerer_enabled_migrated(self):
        """triggererEnabled is moved to airflowComponents.triggerer.enabled."""
        text = dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    triggererEnabled: false
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["triggerer"]["enabled"] is False
        assert "triggererEnabled" not in deployments
        assert len(changes) == 1

    def test_both_houston_flags_migrated(self):
        """Both dagProcessorEnabled and triggererEnabled migrate together."""
        text = dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    dagProcessorEnabled: true
                    triggererEnabled: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert deployments["airflowComponents"]["triggerer"]["enabled"] is True
        assert "dagProcessorEnabled" not in deployments
        assert "triggererEnabled" not in deployments
        assert len(changes) == 2

    def test_obsolete_houston_keys_deleted(self):
        """Obsolete houston config deployment keys are deleted."""
        text = dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    astroUnitsEnabled: false
                    resourceProvisioningStrategy:
                      astroUnitsEnabled: false
                    maxPodAu: 100
                    upsertDeploymentEnabled: true
                    canUpsertDeploymentFromUI: true
                    enableSystemAdminCanCreateDeprecatedAirflows: false
                    otherKey: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert "astroUnitsEnabled" not in deployments
        assert "resourceProvisioningStrategy" not in deployments
        assert "maxPodAu" not in deployments
        assert "upsertDeploymentEnabled" not in deployments
        assert "canUpsertDeploymentFromUI" not in deployments
        assert "enableSystemAdminCanCreateDeprecatedAirflows" not in deployments
        assert deployments["otherKey"] is True
        assert len(changes) == 6

    def test_houston_config_absent(self):
        """Missing astronomer.houston.config.deployments section produces no changes."""
        text = "global:\n  rbacEnabled: true\n"
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["rbac"]["enabled"] is True
        assert len(changes) == 1

    def test_houston_config_already_migrated(self):
        """Already-migrated houston config is not changed."""
        text = dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    airflowComponents:
                      dagProcessor:
                        enabled: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)

        assert len(changes) == 0

    def test_houston_config_conflict_keeps_new(self):
        """When both old and new keys exist, new-schema value is preserved."""
        text = dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    dagProcessorEnabled: false
                    airflowComponents:
                      dagProcessor:
                        enabled: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert "dagProcessorEnabled" not in deployments
        assert len(changes) >= 1

    def test_global_and_houston_migrate_together(self):
        """Both global flags and houston config flags are migrated in a single pass."""
        text = dedent("""\
            global:
              rbacEnabled: true
            astronomer:
              houston:
                config:
                  deployments:
                    dagProcessorEnabled: true
        """)
        data = _load_rt(text)
        changes = migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["rbac"]["enabled"] is True
        assert "rbacEnabled" not in result["global"]
        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert "dagProcessorEnabled" not in deployments
        assert len(changes) == 2


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test the command-line interface of the migration script."""

    def test_stdout_output_default(self, tmp_path: Path):
        """Without output path, migrated YAML is written to stdout."""
        input_file = tmp_path / "values.yaml"
        input_file.write_text("global:\n  rbacEnabled: true\n")

        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"), str(input_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        yml = YAML(typ="safe")
        output = yml.load(StringIO(result.stdout))
        assert output["global"]["rbac"]["enabled"] is True
        assert "rbacEnabled" not in output["global"]

    def test_dry_run_shows_changes(self, tmp_path: Path):
        """--dry-run outputs the list of changes to stderr without modifying anything."""
        input_file = tmp_path / "values.yaml"
        original_text = "global:\n  rbacEnabled: true\n  sccEnabled: false\n"
        input_file.write_text(original_text)

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"),
                "--dry-run",
                str(input_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "global.rbacEnabled -> global.rbac.enabled" in result.stderr
        assert "global.sccEnabled -> global.scc.enabled" in result.stderr
        assert "2 migration(s)" in result.stderr
        assert input_file.read_text() == original_text

    def test_dry_run_no_changes(self, tmp_path: Path):
        """--dry-run on an already-migrated file reports no changes."""
        input_file = tmp_path / "values.yaml"
        input_file.write_text("global:\n  rbac:\n    enabled: true\n")

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"),
                "--dry-run",
                str(input_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No migrations needed" in result.stderr

    def test_in_place_modifies_file(self, tmp_path: Path):
        """--in-place writes back to the same file."""
        input_file = tmp_path / "values.yaml"
        input_file.write_text("global:\n  rbacEnabled: true\n")

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"),
                "--in-place",
                str(input_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        yml = YAML(typ="safe")
        modified = yml.load(input_file)
        assert modified["global"]["rbac"]["enabled"] is True
        assert "rbacEnabled" not in modified["global"]

    def test_backup_creates_bak_file(self, tmp_path: Path):
        """--backup creates a .bak copy before in-place modification."""
        input_file = tmp_path / "values.yaml"
        original_text = "global:\n  rbacEnabled: true\n"
        input_file.write_text(original_text)

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"),
                "--in-place",
                "--backup",
                str(input_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        bak_file = tmp_path / "values.yaml.bak"
        assert bak_file.exists()
        assert bak_file.read_text() == original_text

    def test_output_file_argument(self, tmp_path: Path):
        """Specifying an output file writes the migrated YAML there."""
        input_file = tmp_path / "input.yaml"
        output_file = tmp_path / "output.yaml"
        input_file.write_text("global:\n  rbacEnabled: true\n")

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"),
                str(input_file),
                str(output_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert output_file.exists()
        yml = YAML(typ="safe")
        output = yml.load(output_file)
        assert output["global"]["rbac"]["enabled"] is True

    def test_in_place_with_output_is_error(self, tmp_path: Path):
        """Using --in-place with an output file argument should fail."""
        input_file = tmp_path / "input.yaml"
        output_file = tmp_path / "output.yaml"
        input_file.write_text("global:\n  rbacEnabled: true\n")

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"),
                "--in-place",
                str(input_file),
                str(output_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Cannot use --in-place with an output file" in result.stderr

    def test_nonexistent_input_file(self, tmp_path: Path):
        """Referencing a non-existent input file returns an error."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "migrate-helm-chart-values-1x-to-2x.py"),
                str(tmp_path / "nonexistent.yaml"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr
