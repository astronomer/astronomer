"""Tests for bin/migrate-helm-chart-values-037x-to-2x.py migration script."""

from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path
from textwrap import dedent

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT_PATH = REPO_ROOT / "bin" / "migrate-helm-chart-values-037x-to-2x.py"
_spec = importlib.util.spec_from_file_location("migrate_helm_chart_values_037x_to_2x", _SCRIPT_PATH)
migrate_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migrate_mod
_spec.loader.exec_module(migrate_mod)
migrate_values = migrate_mod.migrate_values
BoolToNested = migrate_mod.BoolToNested
SubtreeMove = migrate_mod.SubtreeMove
DeleteKey = migrate_mod.DeleteKey
RenameKey = migrate_mod.RenameKey
SetValue = migrate_mod.SetValue
AddKeyIfMissing = migrate_mod.AddKeyIfMissing
HoustonDeploymentBoolToNested = migrate_mod.HoustonDeploymentBoolToNested
HoustonDeploymentDeleteKey = migrate_mod.HoustonDeploymentDeleteKey
MIGRATIONS = migrate_mod.MIGRATIONS
main = migrate_mod.main

TOTAL_RULES_ON_FULL_037X = 47


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
# Correctness tests: partial override
# ---------------------------------------------------------------------------


class TestPartialOverrideMigration:
    """Test migration of a realistic customer partial override from 0.37.x."""

    def test_partial_override_migration(
        self,
        old_037x_partial_override_text: str,
        expected_037x_new_partial_text: str,
    ):
        """Converting a 0.37.x partial override produces the expected new structure."""
        data = _load_rt(old_037x_partial_override_text)
        changes = migrate_values(data)
        result = _to_plain(data)
        expected = _to_plain(_load_rt(expected_037x_new_partial_text))

        assert result == expected
        assert len(changes) > 0

    def test_non_global_sections_preserved(self, old_037x_partial_override_text: str):
        """Sections outside global that are not migrated are untouched."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["astronomer"]["houston"]["resources"]["requests"]["cpu"] == "1000m"

    def test_unrelated_global_keys_preserved(self, old_037x_partial_override_text: str):
        """Keys like baseDomain inside global are untouched."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["baseDomain"] == "mycompany.astronomer.io"

    def test_obsolete_keys_removed(self, old_037x_partial_override_text: str):
        """Obsolete 0.37.x keys are deleted."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        for key in ["singleNamespace", "veleroEnabled", "enableHoustonInternalAuthorization", "nodeExporterSccEnabled", "stan"]:
            assert key not in result["global"], f"Obsolete key '{key}' should be deleted from global"

        assert "stan" not in result.get("tags", {}), "tags.stan should be deleted"
        assert "stan" not in result, "Top-level stan should be deleted"
        assert "kibana" not in result, "Top-level kibana should be deleted"
        assert "prometheus-blackbox-exporter" not in result, "Top-level prometheus-blackbox-exporter should be deleted"

    def test_fluentd_renamed_to_vector(self, old_037x_partial_override_text: str):
        """fluentd is renamed to vector with preserved subtree."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert "fluentd" not in result, "fluentd should be renamed"
        assert "vector" in result, "vector should exist after rename"
        assert result["vector"]["resources"]["requests"]["cpu"] == "500m"

    def test_pgbouncer_secret_renamed(self, old_037x_partial_override_text: str):
        """pgbouncer.krb5ConfSecretName is renamed to secretName."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        pgb = result["global"]["pgbouncer"]
        assert "krb5ConfSecretName" not in pgb
        assert pgb["secretName"] == "my-krb5-secret"

    def test_pgbouncer_port_updated(self, old_037x_partial_override_text: str):
        """pgbouncer.servicePort is updated from 5432 to 6543."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["pgbouncer"]["servicePort"] == "6543"

    def test_nats_jetstream_enabled(self, old_037x_partial_override_text: str):
        """nats.jetStream.enabled is updated from false to true."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["nats"]["jetStream"]["enabled"] is True

    def test_new_keys_added(self, old_037x_partial_override_text: str):
        """New keys with defaults are added when missing."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        assert "authHeaderSecretName" in result["global"]
        assert result["global"]["plane"]["mode"] == "unified"
        assert result["global"]["plane"]["domainPrefix"] == ""
        assert "podLabels" in result["global"]
        assert result["nats"]["init"]["resources"]["requests"]["cpu"] == "75m"

    def test_houston_config_migrated(self, old_037x_partial_override_text: str):
        """Houston config deployment flags are restructured and obsolete keys deleted."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        # Bool-to-nested migrations
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert deployments["airflowComponents"]["triggerer"]["enabled"] is True
        assert deployments["deployMechanisms"]["configureDagDeployment"]["enabled"] is True
        assert deployments["deployMechanisms"]["gitSyncDagDeployment"]["enabled"] is True
        assert deployments["deployMechanisms"]["nfsMountDagDeployment"]["enabled"] is True
        assert deployments["runtimeManagement"]["listAllRuntimeVersions"]["enabled"] is True
        assert deployments["deploymentImagesRegistry"]["updateDeploymentImageEndpoint"]["enabled"] is True
        assert deployments["metricsReporting"]["grafana"]["enabled"] is True
        assert deployments["deploymentLifecycle"]["hardDeleteDeployment"]["enabled"] is True
        assert deployments["logHelmValues"]["enabled"] is True
        assert deployments["namespaceManagement"]["manualReleaseNames"]["enabled"] is False
        # Move migrations
        assert deployments["databaseManagement"]["pgBouncerResourceCalculationStrategy"] == "airflowStratV2"
        assert deployments["deploymentImagesRegistry"]["serviceAccountAnnotationKey"] == "eks.amazonaws.com/role-arn"
        # Old flat keys removed
        for old_key in [
            "dagProcessorEnabled", "triggererEnabled", "configureDagDeployment",
            "gitSyncDagDeployment", "nfsMountDagDeployment", "enableListAllRuntimeVersions",
            "enableUpdateDeploymentImageEndpoint", "grafanaUIEnabled", "hardDeleteDeployment",
            "manualReleaseNames", "pgBouncerResourceCalculationStrategy",
            "serviceAccountAnnotationKey", "astroUnitsEnabled", "resourceProvisioningStrategy",
            "maxPodAu", "upsertDeploymentEnabled", "canUpsertDeploymentFromUI",
            "enableSystemAdminCanCreateDeprecatedAirflows",
        ]:
            assert old_key not in deployments, f"Old key '{old_key}' should have been removed"


# ---------------------------------------------------------------------------
# Correctness tests: full values.yaml
# ---------------------------------------------------------------------------


class TestFullValuesMigration:
    """Test migration of the complete old 0.37.x values.yaml."""

    def test_full_values_migration_feature_flags(self, old_037x_full_values_text: str):
        """Migrating 0.37.x full values.yaml produces correct feature flag paths."""
        data = _load_rt(old_037x_full_values_text)
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
        assert len(changes) == TOTAL_RULES_ON_FULL_037X

    def test_houston_config_migrated_full(self, old_037x_full_values_text: str):
        """Houston config deployment flags are restructured in full values."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        result = _to_plain(data)

        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert deployments["airflowComponents"]["triggerer"]["enabled"] is True
        assert deployments["deployMechanisms"]["configureDagDeployment"]["enabled"] is True
        assert deployments["logHelmValues"]["enabled"] is True
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

    def test_old_keys_removed_after_migration(self, old_037x_full_values_text: str):
        """Old flat keys no longer exist at the global root after migration."""
        data = _load_rt(old_037x_full_values_text)
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
            "singleNamespace",
            "veleroEnabled",
            "enableHoustonInternalAuthorization",
            "nodeExporterSccEnabled",
        ]
        for key in old_keys:
            assert key not in g, f"Old key '{key}' should have been removed from global"

        assert "features" not in g, "Empty 'features' key should have been cleaned up"
        assert "stan" not in g, "global.stan should have been deleted"

    def test_top_level_obsolete_sections_removed(self, old_037x_full_values_text: str):
        """Top-level obsolete sections are removed."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        result = _to_plain(data)

        assert "stan" not in result, "Top-level stan should be removed"
        assert "kibana" not in result, "Top-level kibana should be removed"
        assert "prometheus-blackbox-exporter" not in result, "Top-level prometheus-blackbox-exporter should be removed"
        assert "fluentd" not in result, "fluentd should be renamed to vector"

    def test_fluentd_renamed_to_vector_full(self, old_037x_full_values_text: str):
        """fluentd is renamed to vector in the full values."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        result = _to_plain(data)

        assert "vector" in result
        assert result["vector"]["resources"]["requests"]["cpu"] == "250m"
        assert result["vector"]["resources"]["requests"]["memory"] == "512Mi"

    def test_tags_stan_removed(self, old_037x_full_values_text: str):
        """tags.stan is removed."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        result = _to_plain(data)

        assert "stan" not in result.get("tags", {})

    def test_pgbouncer_migrated(self, old_037x_full_values_text: str):
        """PGBouncer keys are renamed and port updated in full values."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        g = _to_plain(data)["global"]

        pgb = g["pgbouncer"]
        assert "krb5ConfSecretName" not in pgb
        assert pgb["secretName"] == "krb5.conf"
        assert pgb["servicePort"] == "6543"

    def test_nats_jetstream_enabled_full(self, old_037x_full_values_text: str):
        """nats.jetStream.enabled set to true in full values."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        g = _to_plain(data)["global"]

        assert g["nats"]["jetStream"]["enabled"] is True

    def test_new_keys_added_full(self, old_037x_full_values_text: str):
        """New default keys are added to full values."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        result = _to_plain(data)
        g = result["global"]

        assert "authHeaderSecretName" in g
        assert g["plane"]["mode"] == "unified"
        assert g["plane"]["domainPrefix"] == ""
        assert "podLabels" in g
        assert g["logging"]["provider"] is None
        assert result["nats"]["init"]["resources"]["requests"]["cpu"] == "75m"

    def test_unchanged_keys_preserved(self, old_037x_full_values_text: str):
        """Keys that are already in the correct format are not modified."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        g = _to_plain(data)["global"]

        assert g["networkPolicy"]["enabled"] is True
        assert g["authSidecar"]["enabled"] is False
        assert g["airflowOperator"]["enabled"] is False
        assert g["nats"]["enabled"] is True


# ---------------------------------------------------------------------------
# Individual rule tests: DeleteKey
# ---------------------------------------------------------------------------


class TestDeleteKey:
    """Test the DeleteKey rule type."""

    def test_delete_global_key(self):
        """DeleteKey removes a key from within global."""
        data = _load_rt("global:\n  singleNamespace: true\n  baseDomain: x.com\n")
        rule = DeleteKey(["global", "singleNamespace"])
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "singleNamespace" not in result["global"]
        assert result["global"]["baseDomain"] == "x.com"
        assert len(changes) == 1

    def test_delete_top_level_key(self):
        """DeleteKey removes a top-level key."""
        data = _load_rt("kibana:\n  resources:\n    requests:\n      cpu: 100m\nglobal:\n  baseDomain: x.com\n")
        rule = DeleteKey(["kibana"])
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "kibana" not in result
        assert result["global"]["baseDomain"] == "x.com"
        assert len(changes) == 1

    def test_delete_nested_key(self):
        """DeleteKey removes a key nested under tags."""
        data = _load_rt("tags:\n  platform: true\n  stan: true\n")
        rule = DeleteKey(["tags", "stan"])
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "stan" not in result["tags"]
        assert result["tags"]["platform"] is True
        assert len(changes) == 1

    def test_delete_missing_key(self):
        """DeleteKey does nothing when key is absent."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = DeleteKey(["global", "singleNamespace"])
        changes = rule.apply(data)

        assert len(changes) == 0

    def test_delete_subtree(self):
        """DeleteKey removes an entire subtree."""
        data = _load_rt("global:\n  stan:\n    enabled: true\n    replicas: 3\n")
        rule = DeleteKey(["global", "stan"])
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "stan" not in result["global"]
        assert len(changes) == 1


# ---------------------------------------------------------------------------
# Individual rule tests: RenameKey
# ---------------------------------------------------------------------------


class TestRenameKey:
    """Test the RenameKey rule type."""

    def test_rename_top_level(self):
        """RenameKey renames a top-level key preserving value."""
        data = _load_rt("fluentd:\n  resources:\n    requests:\n      cpu: 250m\n")
        rule = RenameKey(["fluentd"], "vector")
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "fluentd" not in result
        assert result["vector"]["resources"]["requests"]["cpu"] == "250m"
        assert len(changes) == 1
        assert changes[0].old_path == "fluentd"
        assert changes[0].new_path == "vector"

    def test_rename_nested_key(self):
        """RenameKey renames a nested key."""
        data = _load_rt("global:\n  pgbouncer:\n    krb5ConfSecretName: my-secret\n    enabled: true\n")
        rule = RenameKey(["global", "pgbouncer", "krb5ConfSecretName"], "secretName")
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "krb5ConfSecretName" not in result["global"]["pgbouncer"]
        assert result["global"]["pgbouncer"]["secretName"] == "my-secret"
        assert result["global"]["pgbouncer"]["enabled"] is True
        assert len(changes) == 1

    def test_rename_missing_key(self):
        """RenameKey does nothing when old key is absent."""
        data = _load_rt("global:\n  pgbouncer:\n    enabled: true\n")
        rule = RenameKey(["global", "pgbouncer", "krb5ConfSecretName"], "secretName")
        changes = rule.apply(data)

        assert len(changes) == 0

    def test_rename_conflict_keeps_new(self):
        """When new name already exists, old key is removed and new value kept."""
        data = _load_rt(
            dedent("""\
            global:
              pgbouncer:
                krb5ConfSecretName: old-secret
                secretName: new-secret
        """)
        )
        rule = RenameKey(["global", "pgbouncer", "krb5ConfSecretName"], "secretName")
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["pgbouncer"]["secretName"] == "new-secret"
        assert "krb5ConfSecretName" not in result["global"]["pgbouncer"]
        assert len(changes) == 1

    def test_rename_preserves_inline_comment(self):
        """RenameKey preserves inline comment on the renamed key."""
        data = _load_rt("fluentd:  # logging collector\n  resources: {}\n")
        rule = RenameKey(["fluentd"], "vector")
        rule.apply(data)
        output = _dump_rt(data)

        assert "# logging collector" in output
        assert "vector" in output
        assert "fluentd" not in output


# ---------------------------------------------------------------------------
# Individual rule tests: SetValue
# ---------------------------------------------------------------------------


class TestSetValue:
    """Test the SetValue rule type."""

    def test_set_value_matches(self):
        """SetValue updates value when old value matches."""
        data = _load_rt("global:\n  pgbouncer:\n    servicePort: '5432'\n")
        rule = SetValue(["global", "pgbouncer", "servicePort"], old_value="5432", new_value="6543")
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["pgbouncer"]["servicePort"] == "6543"
        assert len(changes) == 1

    def test_set_value_no_match(self):
        """SetValue does nothing when current value does not match."""
        data = _load_rt("global:\n  pgbouncer:\n    servicePort: '9999'\n")
        rule = SetValue(["global", "pgbouncer", "servicePort"], old_value="5432", new_value="6543")
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["pgbouncer"]["servicePort"] == "9999"
        assert len(changes) == 0

    def test_set_value_missing_key(self):
        """SetValue does nothing when path does not exist."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = SetValue(["global", "pgbouncer", "servicePort"], old_value="5432", new_value="6543")
        changes = rule.apply(data)

        assert len(changes) == 0

    def test_set_boolean_value(self):
        """SetValue works with boolean values."""
        data = _load_rt("global:\n  nats:\n    jetStream:\n      enabled: false\n")
        rule = SetValue(["global", "nats", "jetStream", "enabled"], old_value=False, new_value=True)
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["nats"]["jetStream"]["enabled"] is True
        assert len(changes) == 1

    def test_set_value_preserves_inline_comment(self):
        """SetValue preserves inline comment on the updated key."""
        data = _load_rt("global:\n  pgbouncer:\n    servicePort: '5432'  # pgb port\n")
        rule = SetValue(["global", "pgbouncer", "servicePort"], old_value="5432", new_value="6543")
        rule.apply(data)
        output = _dump_rt(data)

        assert "# pgb port" in output
        assert "6543" in output


# ---------------------------------------------------------------------------
# Individual rule tests: AddKeyIfMissing
# ---------------------------------------------------------------------------


class TestAddKeyIfMissing:
    """Test the AddKeyIfMissing rule type."""

    def test_add_simple_key(self):
        """AddKeyIfMissing adds a key with None value."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = AddKeyIfMissing(["global", "authHeaderSecretName"], value=None)
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "authHeaderSecretName" in result["global"]
        assert result["global"]["authHeaderSecretName"] is None
        assert len(changes) == 1

    def test_add_dict_key(self):
        """AddKeyIfMissing adds a key with dict value."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = AddKeyIfMissing(["global", "plane"], value={"mode": "unified", "domainPrefix": ""})
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["plane"]["mode"] == "unified"
        assert result["global"]["plane"]["domainPrefix"] == ""
        assert len(changes) == 1

    def test_add_empty_dict_key(self):
        """AddKeyIfMissing adds a key with empty dict value."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = AddKeyIfMissing(["global", "podLabels"], value={})
        changes = rule.apply(data)

        result = _to_plain(data)
        assert "podLabels" in result["global"]
        assert len(changes) == 1

    def test_add_nested_dict_key(self):
        """AddKeyIfMissing adds a key with nested dict value."""
        data = _load_rt("nats:\n  nats:\n    resources: {}\n")
        rule = AddKeyIfMissing(
            ["nats", "init"],
            value={"resources": {"requests": {"cpu": "75m", "memory": "30Mi"}, "limits": {"cpu": "250m", "memory": "100Mi"}}},
        )
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["nats"]["init"]["resources"]["requests"]["cpu"] == "75m"
        assert result["nats"]["init"]["resources"]["limits"]["memory"] == "100Mi"
        assert len(changes) == 1

    def test_add_skips_existing(self):
        """AddKeyIfMissing does nothing when key already exists."""
        data = _load_rt("global:\n  authHeaderSecretName: my-secret\n")
        rule = AddKeyIfMissing(["global", "authHeaderSecretName"], value=None)
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["authHeaderSecretName"] == "my-secret"
        assert len(changes) == 0

    def test_add_creates_parents(self):
        """AddKeyIfMissing creates parent keys if needed."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = AddKeyIfMissing(["global", "logging", "provider"], value=None)
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["logging"]["provider"] is None
        assert len(changes) == 1

    def test_add_to_existing_parent(self):
        """AddKeyIfMissing adds to an existing parent without overwriting siblings."""
        data = _load_rt("global:\n  logging:\n    indexNamePrefix: my-prefix\n")
        rule = AddKeyIfMissing(["global", "logging", "provider"], value=None)
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["logging"]["indexNamePrefix"] == "my-prefix"
        assert result["global"]["logging"]["provider"] is None
        assert len(changes) == 1


# ---------------------------------------------------------------------------
# Individual rule tests: HoustonDeploymentBoolToNested
# ---------------------------------------------------------------------------


class TestHoustonDeploymentBoolToNested:
    """Test the HoustonDeploymentBoolToNested rule type."""

    def test_migrates_dag_processor(self):
        """HoustonDeploymentBoolToNested migrates dagProcessorEnabled."""
        data = _load_rt(
            dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    dagProcessorEnabled: true
        """)
        )
        rule = HoustonDeploymentBoolToNested("dagProcessorEnabled", ["airflowComponents", "dagProcessor", "enabled"])
        changes = rule.apply(data)

        result = _to_plain(data)
        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert "dagProcessorEnabled" not in deployments
        assert len(changes) == 1

    def test_migrates_triggerer(self):
        """HoustonDeploymentBoolToNested migrates triggererEnabled."""
        data = _load_rt(
            dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    triggererEnabled: false
        """)
        )
        rule = HoustonDeploymentBoolToNested("triggererEnabled", ["airflowComponents", "triggerer", "enabled"])
        changes = rule.apply(data)

        result = _to_plain(data)
        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["triggerer"]["enabled"] is False
        assert "triggererEnabled" not in deployments
        assert len(changes) == 1

    def test_missing_section(self):
        """HoustonDeploymentBoolToNested does nothing when section is absent."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = HoustonDeploymentBoolToNested("dagProcessorEnabled", ["airflowComponents", "dagProcessor", "enabled"])
        changes = rule.apply(data)

        assert len(changes) == 0

    def test_conflict_keeps_new(self):
        """When new path already exists, old key is removed and new value kept."""
        data = _load_rt(
            dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    dagProcessorEnabled: false
                    airflowComponents:
                      dagProcessor:
                        enabled: true
        """)
        )
        rule = HoustonDeploymentBoolToNested("dagProcessorEnabled", ["airflowComponents", "dagProcessor", "enabled"])
        changes = rule.apply(data)

        result = _to_plain(data)
        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert deployments["airflowComponents"]["dagProcessor"]["enabled"] is True
        assert "dagProcessorEnabled" not in deployments
        assert len(changes) == 1


# ---------------------------------------------------------------------------
# Individual rule tests: HoustonDeploymentDeleteKey
# ---------------------------------------------------------------------------


class TestHoustonDeploymentDeleteKey:
    """Test the HoustonDeploymentDeleteKey rule type."""

    def test_deletes_key(self):
        """HoustonDeploymentDeleteKey removes a key from houston config deployments."""
        data = _load_rt(
            dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    astroUnitsEnabled: false
                    dagProcessorEnabled: true
        """)
        )
        rule = HoustonDeploymentDeleteKey("astroUnitsEnabled")
        changes = rule.apply(data)

        result = _to_plain(data)
        deployments = result["astronomer"]["houston"]["config"]["deployments"]
        assert "astroUnitsEnabled" not in deployments
        assert deployments["dagProcessorEnabled"] is True
        assert len(changes) == 1

    def test_missing_key(self):
        """HoustonDeploymentDeleteKey does nothing when key is absent."""
        data = _load_rt(
            dedent("""\
            astronomer:
              houston:
                config:
                  deployments:
                    dagProcessorEnabled: true
        """)
        )
        rule = HoustonDeploymentDeleteKey("astroUnitsEnabled")
        changes = rule.apply(data)

        assert len(changes) == 0

    def test_missing_section(self):
        """HoustonDeploymentDeleteKey does nothing when section is absent."""
        data = _load_rt("global:\n  baseDomain: x.com\n")
        rule = HoustonDeploymentDeleteKey("astroUnitsEnabled")
        changes = rule.apply(data)

        assert len(changes) == 0


# ---------------------------------------------------------------------------
# BoolToNested and SubtreeMove (same behavior as 1.x, tested for completeness)
# ---------------------------------------------------------------------------


class TestBoolToNestedAndSubtreeMove:
    """Verify BoolToNested and SubtreeMove operate correctly via the root doc."""

    @pytest.mark.parametrize("value", [True, False])
    def test_bool_to_nested(self, value: bool):
        """BoolToNested correctly moves a boolean to a nested .enabled key."""
        data = _load_rt(f"global:\n  rbacEnabled: {str(value).lower()}\n")
        rule = BoolToNested("rbacEnabled", ["rbac", "enabled"])
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["rbac"]["enabled"] is value
        assert "rbacEnabled" not in result["global"]
        assert len(changes) == 1

    def test_subtree_move(self):
        """SubtreeMove keeps all nested keys intact."""
        data = _load_rt(
            dedent("""\
            global:
              dagOnlyDeployment:
                enabled: true
                repository: custom/repo
        """)
        )
        rule = SubtreeMove(["dagOnlyDeployment"], ["deployMechanisms", "dagOnlyDeployment"])
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["deployMechanisms"]["dagOnlyDeployment"]["enabled"] is True
        assert result["global"]["deployMechanisms"]["dagOnlyDeployment"]["repository"] == "custom/repo"
        assert "dagOnlyDeployment" not in result["global"]
        assert len(changes) == 1


# ---------------------------------------------------------------------------
# Parametrized test over all migration rules
# ---------------------------------------------------------------------------


RULE_TEST_CASES = [
    # BoolToNested
    ("rbacEnabled", "global:\n  rbacEnabled: true\n", lambda d: d["global"]["rbac"]["enabled"] is True),
    ("sccEnabled", "global:\n  sccEnabled: false\n", lambda d: d["global"]["scc"]["enabled"] is False),
    ("openshiftEnabled", "global:\n  openshiftEnabled: true\n", lambda d: d["global"]["openshift"]["enabled"] is True),
    ("networkNSLabels", "global:\n  networkNSLabels: true\n", lambda d: d["global"]["networkNSLabels"]["enabled"] is True),
    (
        "namespaceFreeFormEntry",
        "global:\n  namespaceFreeFormEntry: false\n",
        lambda d: d["global"]["namespaceManagement"]["namespaceFreeFormEntry"]["enabled"] is False,
    ),
    (
        "taskUsageMetricsEnabled",
        "global:\n  taskUsageMetricsEnabled: true\n",
        lambda d: d["global"]["metricsReporting"]["taskUsageMetrics"]["enabled"] is True,
    ),
    (
        "deployRollbackEnabled",
        "global:\n  deployRollbackEnabled: false\n",
        lambda d: d["global"]["deploymentLifecycle"]["deployRollback"]["enabled"] is False,
    ),
    # SubtreeMove
    (
        "features.namespacePools",
        "global:\n  features:\n    namespacePools:\n      enabled: true\n      createRbac: true\n",
        lambda d: d["global"]["namespaceManagement"]["namespacePools"]["enabled"] is True,
    ),
    (
        "dagOnlyDeployment",
        "global:\n  dagOnlyDeployment:\n    enabled: true\n    repository: test/repo\n",
        lambda d: d["global"]["deployMechanisms"]["dagOnlyDeployment"]["enabled"] is True,
    ),
    (
        "loggingSidecar",
        "global:\n  loggingSidecar:\n    enabled: true\n    name: test-sidecar\n",
        lambda d: d["global"]["logging"]["loggingSidecar"]["enabled"] is True,
    ),
    # DeleteKey
    (
        "delete_singleNamespace",
        "global:\n  singleNamespace: true\n  baseDomain: x.com\n",
        lambda d: "singleNamespace" not in d["global"],
    ),
    ("delete_veleroEnabled", "global:\n  veleroEnabled: true\n  baseDomain: x.com\n", lambda d: "veleroEnabled" not in d["global"]),
    (
        "delete_enableHoustonInternalAuthorization",
        "global:\n  enableHoustonInternalAuthorization: true\n  baseDomain: x.com\n",
        lambda d: "enableHoustonInternalAuthorization" not in d["global"],
    ),
    (
        "delete_nodeExporterSccEnabled",
        "global:\n  nodeExporterSccEnabled: true\n  baseDomain: x.com\n",
        lambda d: "nodeExporterSccEnabled" not in d["global"],
    ),
    ("delete_global_stan", "global:\n  stan:\n    enabled: true\n  baseDomain: x.com\n", lambda d: "stan" not in d["global"]),
    ("delete_tags_stan", "tags:\n  stan: true\n  platform: true\n", lambda d: "stan" not in d.get("tags", {})),
    ("delete_top_stan", "stan:\n  stan:\n    resources: {}\nglobal:\n  baseDomain: x.com\n", lambda d: "stan" not in d),
    ("delete_kibana", "kibana:\n  resources: {}\nglobal:\n  baseDomain: x.com\n", lambda d: "kibana" not in d),
    (
        "delete_blackbox",
        "prometheus-blackbox-exporter:\n  resources: {}\nglobal:\n  baseDomain: x.com\n",
        lambda d: "prometheus-blackbox-exporter" not in d,
    ),
    # RenameKey
    (
        "rename_fluentd",
        "fluentd:\n  resources:\n    requests:\n      cpu: 100m\n",
        lambda d: "fluentd" not in d and d["vector"]["resources"]["requests"]["cpu"] == "100m",
    ),
    (
        "rename_pgbouncer_secret",
        "global:\n  pgbouncer:\n    krb5ConfSecretName: my-secret\n",
        lambda d: d["global"]["pgbouncer"]["secretName"] == "my-secret" and "krb5ConfSecretName" not in d["global"]["pgbouncer"],
    ),
    # SetValue
    (
        "set_pgbouncer_port",
        "global:\n  pgbouncer:\n    servicePort: '5432'\n",
        lambda d: d["global"]["pgbouncer"]["servicePort"] == "6543",
    ),
    (
        "set_jetstream_enabled",
        "global:\n  nats:\n    jetStream:\n      enabled: false\n",
        lambda d: d["global"]["nats"]["jetStream"]["enabled"] is True,
    ),
    # AddKeyIfMissing
    ("add_authHeaderSecretName", "global:\n  baseDomain: x.com\n", lambda d: "authHeaderSecretName" in d["global"]),
    ("add_plane", "global:\n  baseDomain: x.com\n", lambda d: d["global"]["plane"]["mode"] == "unified"),
    ("add_podLabels", "global:\n  baseDomain: x.com\n", lambda d: "podLabels" in d["global"]),
    (
        "add_logging_provider",
        "global:\n  baseDomain: x.com\n",
        lambda d: "logging" in d["global"] and "provider" in d["global"]["logging"],
    ),
    ("add_nats_init", "nats:\n  nats:\n    resources: {}\n", lambda d: d["nats"]["init"]["resources"]["requests"]["cpu"] == "75m"),
    # HoustonDeploymentBoolToNested
    (
        "houston_dagProcessorEnabled",
        "astronomer:\n  houston:\n    config:\n      deployments:\n        dagProcessorEnabled: true\n",
        lambda d: d["astronomer"]["houston"]["config"]["deployments"]["airflowComponents"]["dagProcessor"]["enabled"] is True
        and "dagProcessorEnabled" not in d["astronomer"]["houston"]["config"]["deployments"],
    ),
    (
        "houston_triggererEnabled",
        "astronomer:\n  houston:\n    config:\n      deployments:\n        triggererEnabled: false\n",
        lambda d: d["astronomer"]["houston"]["config"]["deployments"]["airflowComponents"]["triggerer"]["enabled"] is False
        and "triggererEnabled" not in d["astronomer"]["houston"]["config"]["deployments"],
    ),
    # HoustonDeploymentDeleteKey
    (
        "houston_delete_astroUnitsEnabled",
        "astronomer:\n  houston:\n    config:\n      deployments:\n        astroUnitsEnabled: false\n        otherKey: true\n",
        lambda d: "astroUnitsEnabled" not in d["astronomer"]["houston"]["config"]["deployments"],
    ),
    (
        "houston_delete_upsertDeploymentEnabled",
        "astronomer:\n  houston:\n    config:\n      deployments:\n        upsertDeploymentEnabled: true\n        otherKey: true\n",
        lambda d: "upsertDeploymentEnabled" not in d["astronomer"]["houston"]["config"]["deployments"],
    ),
    (
        "houston_delete_canUpsertDeploymentFromUI",
        "astronomer:\n  houston:\n    config:\n      deployments:\n        canUpsertDeploymentFromUI: true\n        otherKey: true\n",
        lambda d: "canUpsertDeploymentFromUI" not in d["astronomer"]["houston"]["config"]["deployments"],
    ),
    (
        "houston_delete_enableSystemAdminCanCreateDeprecatedAirflows",
        "astronomer:\n  houston:\n    config:\n      deployments:\n        enableSystemAdminCanCreateDeprecatedAirflows: false\n        otherKey: true\n",
        lambda d: "enableSystemAdminCanCreateDeprecatedAirflows" not in d["astronomer"]["houston"]["config"]["deployments"],
    ),
    (
        "houston_delete_resourceProvisioningStrategy",
        "astronomer:\n  houston:\n    config:\n      deployments:\n        resourceProvisioningStrategy:\n          astroUnitsEnabled: false\n        otherKey: true\n",
        lambda d: "resourceProvisioningStrategy" not in d["astronomer"]["houston"]["config"]["deployments"],
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
        assert check_fn(result), f"Rule {rule_name} did not produce the expected output"


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Verify running migration on already-migrated data is a no-op."""

    def test_idempotent_already_migrated(self, old_037x_partial_override_text: str):
        """Running migration twice produces the same result."""
        data = _load_rt(old_037x_partial_override_text)
        migrate_values(data)
        first_pass = _dump_rt(data)

        data2 = _load_rt(first_pass)
        changes = migrate_values(data2)
        second_pass = _dump_rt(data2)

        assert first_pass == second_pass
        assert len(changes) == 0

    def test_idempotent_new_schema_input(self, new_037x_schema_partial_text: str):
        """Running migration on new-schema values makes no changes."""
        data = _load_rt(new_037x_schema_partial_text)
        original = _dump_rt(data)

        changes = migrate_values(data)
        after = _dump_rt(data)

        assert original == after
        assert len(changes) == 0

    def test_idempotent_full_values(self, old_037x_full_values_text: str):
        """Running migration on full 0.37.x values twice is idempotent."""
        data = _load_rt(old_037x_full_values_text)
        migrate_values(data)
        first_pass = _dump_rt(data)

        data2 = _load_rt(first_pass)
        changes = migrate_values(data2)
        second_pass = _dump_rt(data2)

        assert first_pass == second_pass
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
        """YAML without a global key passes through unchanged for global rules."""
        text = "astronomer:\n  houston:\n    replicas: 3\n"
        data = _load_rt(text)
        migrate_values(data)

        result = _to_plain(data)
        assert result["astronomer"]["houston"]["replicas"] == 3

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
        migrate_values(data)
        result = _to_plain(data)

        assert result["global"]["rbac"]["enabled"] is True
        assert result["global"]["scc"]["enabled"] is False
        assert result["global"]["openshift"]["enabled"] is True
        assert result["global"]["networkNSLabels"]["enabled"] is True
        assert "rbacEnabled" not in result["global"]
        assert "openshiftEnabled" not in result["global"]

    def test_global_section_empty(self):
        """global section that is empty does not crash."""
        data = _load_rt("global: {}\n")
        changes = migrate_values(data)
        assert len(changes) >= 1  # AddKeyIfMissing rules still fire

    def test_global_section_null(self):
        """global section set to null does not crash.

        AddKeyIfMissing rules may still fire for top-level keys (like nats.init).
        """
        data = _load_rt("global:\n")
        changes = migrate_values(data)
        assert isinstance(changes, list)

    def test_only_unrelated_global_keys(self):
        """global section with only unrelated keys still gets AddKeyIfMissing applied."""
        text = dedent("""\
            global:
              baseDomain: example.com
              tlsSecret: my-secret
              privateCaCerts: []
        """)
        data = _load_rt(text)
        migrate_values(data)

        result = _to_plain(data)
        assert result["global"]["baseDomain"] == "example.com"
        assert "authHeaderSecretName" in result["global"]

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

    def test_only_delete_rules_apply(self):
        """File with only obsolete keys has them removed."""
        text = dedent("""\
            global:
              baseDomain: example.com
              singleNamespace: true
              veleroEnabled: false
        """)
        data = _load_rt(text)
        migrate_values(data)
        result = _to_plain(data)

        assert "singleNamespace" not in result["global"]
        assert "veleroEnabled" not in result["global"]
        assert result["global"]["baseDomain"] == "example.com"

    def test_only_top_level_delete_rules(self):
        """File with only obsolete top-level sections has them removed."""
        text = dedent("""\
            kibana:
              resources: {}
            prometheus-blackbox-exporter:
              resources: {}
        """)
        data = _load_rt(text)
        migrate_values(data)
        result = _to_plain(data)

        assert "kibana" not in result
        assert "prometheus-blackbox-exporter" not in result


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

    def test_subtree_move_keeps_new_subtree(self):
        """SubtreeMove preserves the existing new-location subtree."""
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
        migrate_values(data)
        result = _to_plain(data)

        dag = result["global"]["deployMechanisms"]["dagOnlyDeployment"]
        assert dag["enabled"] is False
        assert dag["repository"] == "new/repo"
        assert "dagOnlyDeployment" not in result["global"]

    def test_rename_conflict_keeps_existing_new_name(self):
        """RenameKey preserves the existing new-name value."""
        text = dedent("""\
            fluentd:
              resources:
                requests:
                  cpu: 100m
            vector:
              resources:
                requests:
                  cpu: 500m
        """)
        data = _load_rt(text)
        migrate_values(data)
        result = _to_plain(data)

        assert result["vector"]["resources"]["requests"]["cpu"] == "500m"
        assert "fluentd" not in result

    def test_set_value_already_at_new_value(self):
        """SetValue does nothing when value is already the new value."""
        text = dedent("""\
            global:
              pgbouncer:
                servicePort: "6543"
        """)
        data = _load_rt(text)
        rule = SetValue(["global", "pgbouncer", "servicePort"], old_value="5432", new_value="6543")
        changes = rule.apply(data)

        result = _to_plain(data)
        assert result["global"]["pgbouncer"]["servicePort"] == "6543"
        assert len(changes) == 0


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

    def test_inline_comment_on_rename(self):
        """Inline comment survives a RenameKey operation."""
        text = dedent("""\
            fluentd:  # logging collector
              resources:
                requests:
                  cpu: 100m
        """)
        data = _load_rt(text)
        migrate_values(data)
        output = _dump_rt(data)

        assert "# logging collector" in output
        assert "vector" in output
        assert "fluentd" not in output

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


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test the command-line interface of the migration script."""

    def test_stdout_output_default(self, tmp_path: Path):
        """Without output path, migrated YAML is written to stdout."""
        input_file = tmp_path / "values.yaml"
        input_file.write_text("global:\n  rbacEnabled: true\n  singleNamespace: true\n")

        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), str(input_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        yml = YAML(typ="safe")
        output = yml.load(StringIO(result.stdout))
        assert output["global"]["rbac"]["enabled"] is True
        assert "rbacEnabled" not in output["global"]
        assert "singleNamespace" not in output["global"]

    def test_dry_run_shows_changes(self, tmp_path: Path):
        """--dry-run outputs the list of changes to stderr without modifying anything."""
        input_file = tmp_path / "values.yaml"
        original_text = "global:\n  rbacEnabled: true\n  singleNamespace: true\n"
        input_file.write_text(original_text)

        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--dry-run", str(input_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "global.rbacEnabled -> global.rbac.enabled" in result.stderr
        assert "global.singleNamespace -> (deleted)" in result.stderr
        assert input_file.read_text() == original_text

    def test_dry_run_no_changes(self, tmp_path: Path):
        """--dry-run on an already-migrated file reports no changes."""
        input_file = tmp_path / "values.yaml"
        input_file.write_text(
            dedent("""\
            global:
              rbac:
                enabled: true
              authHeaderSecretName: x
              plane:
                mode: unified
              podLabels: {}
              logging:
                provider: es
            nats:
              init:
                resources:
                  requests:
                    cpu: 75m
        """)
        )

        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--dry-run", str(input_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No migrations needed" in result.stderr

    def test_in_place_modifies_file(self, tmp_path: Path):
        """--in-place writes back to the same file."""
        input_file = tmp_path / "values.yaml"
        input_file.write_text("global:\n  rbacEnabled: true\n  singleNamespace: true\n")

        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--in-place", str(input_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        yml = YAML(typ="safe")
        modified = yml.load(input_file)
        assert modified["global"]["rbac"]["enabled"] is True
        assert "rbacEnabled" not in modified["global"]
        assert "singleNamespace" not in modified["global"]

    def test_backup_creates_bak_file(self, tmp_path: Path):
        """--backup creates a .bak copy before in-place modification."""
        input_file = tmp_path / "values.yaml"
        original_text = "global:\n  rbacEnabled: true\n"
        input_file.write_text(original_text)

        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--in-place", "--backup", str(input_file)],
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
            [sys.executable, str(_SCRIPT_PATH), str(input_file), str(output_file)],
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
            [sys.executable, str(_SCRIPT_PATH), "--in-place", str(input_file), str(output_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Cannot use --in-place with an output file" in result.stderr

    def test_nonexistent_input_file(self, tmp_path: Path):
        """Referencing a non-existent input file returns an error."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), str(tmp_path / "nonexistent.yaml")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr
