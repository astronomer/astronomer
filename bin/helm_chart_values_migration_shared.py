"""Shared migration helpers and rules for 1.x / 0.37.x -> 2.x Helm values.

Used by `migrate-helm-chart-values-1x-to-2x.py` and
`migrate-helm-chart-values-037x-to-2x.py` so feature-flag restructuring stays
in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Final

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def create_yaml() -> YAML:
    """Create a YAML instance configured for round-trip (comment-preserving) mode."""
    yml = YAML(typ="rt")
    yml.preserve_quotes = True
    yml.default_flow_style = False
    yml.best_map_representor = True
    return yml


@dataclass
class MigrationChange:
    """Record of a single migration transformation applied."""

    old_path: str
    new_path: str
    description: str


def _ensure_nested_key(mapping: CommentedMap, keys: list[str]) -> CommentedMap:
    """Walk into a CommentedMap creating intermediate mappings as needed.

    Parameters:
        mapping: The root mapping to walk into.
        keys: List of key segments to traverse/create.

    Returns:
        The deepest CommentedMap reached after traversing all keys.
    """
    current = mapping
    for key in keys:
        if key not in current or not isinstance(current[key], CommentedMap):
            current[key] = CommentedMap()
        current = current[key]
    return current


def _delete_key(mapping: CommentedMap, key: str) -> None:
    """Delete a key from a CommentedMap if it exists.

    Parameters:
        mapping: The mapping to delete from.
        key: The key to delete.
    """
    if key in mapping:
        del mapping[key]


def _extract_inline_comment(mapping: CommentedMap, key: str) -> Any | None:
    """Extract the inline comment token attached to a key, if any.

    Parameters:
        mapping: The CommentedMap containing the key.
        key: The key whose inline comment to extract.

    Returns:
        The CommentToken for the inline comment, or None.
    """
    tokens = mapping.ca.items.get(key)
    if tokens and len(tokens) > 2:
        return tokens[2]
    return None


def _attach_inline_comment(mapping: CommentedMap, key: str, comment: Any) -> None:
    """Attach an inline comment token to a key in a CommentedMap.

    Parameters:
        mapping: The CommentedMap to attach the comment to.
        key: The key to attach the comment to.
        comment: The CommentToken to attach.
    """
    mapping.ca.items[key] = [None, None, comment, None]


def _get_nested_mapping(mapping: CommentedMap, keys: list[str]) -> CommentedMap | None:
    """Walk into a CommentedMap and return the mapping at the given path, or None.

    Parameters:
        mapping: The root mapping to walk into.
        keys: List of key segments to traverse.

    Returns:
        The CommentedMap at the end of the path, or None if any segment is missing.
    """
    current: Any = mapping
    for key in keys:
        if not isinstance(current, CommentedMap) or key not in current:
            return None
        current = current[key]
    if isinstance(current, CommentedMap):
        return current
    return None


def _path_exists(mapping: CommentedMap, keys: list[str]) -> bool:
    """Check whether a dotted key path already exists in a mapping.

    Parameters:
        mapping: The root mapping to check.
        keys: List of key segments forming the path.

    Returns:
        True if the full path resolves to an existing value.
    """
    current: Any = mapping
    for key in keys:
        if not isinstance(current, CommentedMap) or key not in current:
            return False
        current = current[key]
    return True


def _path_to_str(path_segments: list[str]) -> str:
    """Convert path segments into a dotted string path.

    Parameters:
        path_segments: Path segments to join.

    Returns:
        A dotted path string.
    """
    return ".".join(path_segments)


def iter_global_mappings(node: Any, path: list[str] | None = None) -> list[tuple[list[str], CommentedMap]]:
    """Find all mappings stored under keys named ``global``.

    Parameters:
        node: The current YAML node to inspect.
        path: The path to ``node`` from the document root.

    Returns:
        A list of ``(path_segments, mapping)`` tuples for every ``global`` mapping.
    """
    current_path = [] if path is None else path
    matches: list[tuple[list[str], CommentedMap]] = []

    match node:
        case CommentedMap():
            for key, value in node.items():
                child_path = [*current_path, str(key)]
                if key == "global" and isinstance(value, CommentedMap):
                    matches.append((child_path, value))
                matches.extend(iter_global_mappings(value, child_path))
        case list():
            for idx, item in enumerate(node):
                matches.extend(iter_global_mappings(item, [*current_path, f"[{idx}]"]))
        case _:
            return matches

    return matches


@dataclass
class BoolToNested:
    """Migrate a flat boolean key to a nested .enabled structure.

    Example: global.rbacEnabled: true -> global.rbac.enabled: true
    """

    old_key: str
    new_path: list[str] = field(default_factory=list)
    path_prefix: str = "global"

    def apply(self, mapping: CommentedMap) -> list[MigrationChange]:
        """Apply the boolean-to-nested migration rule.

        If the destination path already exists the new-schema value is preserved
        and the stale old key is removed without overwriting.

        Parameters:
            mapping: The mapping section containing the key to migrate.

        Returns:
            A list of changes made; empty if the old key was not present or already migrated.
        """
        if self.old_key not in mapping:
            return []

        value = mapping[self.old_key]

        if isinstance(value, CommentedMap):
            return []

        if _path_exists(mapping, self.new_path):
            _delete_key(mapping, self.old_key)
            old_path = f"{self.path_prefix}.{self.old_key}"
            new_path = self.path_prefix + "." + ".".join(self.new_path)
            return [MigrationChange(old_path, new_path, f"Removed stale {old_path} (kept existing {new_path})")]

        inline_comment = _extract_inline_comment(mapping, self.old_key)

        parent_keys = self.new_path[:-1]
        leaf_key = self.new_path[-1]

        if parent_keys and parent_keys[0] == self.old_key:
            new_map = CommentedMap()
            inner = _ensure_nested_key(new_map, parent_keys[1:]) if len(parent_keys) > 1 else new_map
            inner[leaf_key] = value
            mapping[self.old_key] = new_map
        else:
            parent = _ensure_nested_key(mapping, parent_keys)
            parent[leaf_key] = value
            if inline_comment:
                _attach_inline_comment(parent, leaf_key, inline_comment)
            _delete_key(mapping, self.old_key)

        old_path = f"{self.path_prefix}.{self.old_key}"
        new_path = self.path_prefix + "." + ".".join(self.new_path)
        return [MigrationChange(old_path, new_path, f"Moved {old_path} -> {new_path}")]


@dataclass
class InvertedBoolToNested:
    """Migrate a flat boolean key to a nested .enabled structure with inverted value.

    Example: global.disableManageClusterScopedResources: false
          -> global.manageClusterScopedResources.enabled: true
    """

    old_key: str
    new_path: list[str] = field(default_factory=list)
    path_prefix: str = "global"

    def apply(self, mapping: CommentedMap) -> list[MigrationChange]:
        """Apply the inverted boolean-to-nested migration rule.

        Parameters:
            mapping: The mapping section containing the key to migrate.

        Returns:
            A list of changes made; empty if the old key was not present or already migrated.
        """
        if self.old_key not in mapping:
            return []

        value = mapping[self.old_key]

        if isinstance(value, CommentedMap):
            return []

        if _path_exists(mapping, self.new_path):
            _delete_key(mapping, self.old_key)
            old_path = f"{self.path_prefix}.{self.old_key}"
            new_path = self.path_prefix + "." + ".".join(self.new_path)
            return [MigrationChange(old_path, new_path, f"Removed stale {old_path} (kept existing {new_path})")]

        inverted = not value if isinstance(value, bool) else value

        parent_keys = self.new_path[:-1]
        leaf_key = self.new_path[-1]

        parent = _ensure_nested_key(mapping, parent_keys)
        parent[leaf_key] = inverted
        _delete_key(mapping, self.old_key)

        old_path = f"{self.path_prefix}.{self.old_key}"
        new_path = self.path_prefix + "." + ".".join(self.new_path)
        return [MigrationChange(old_path, new_path, f"Moved (inverted) {old_path} -> {new_path}")]


@dataclass
class SubtreeMove:
    """Move an entire subtree from one location to another under global.

    Example: global.dagOnlyDeployment.* -> global.deployMechanisms.dagOnlyDeployment.*
    """

    old_path: list[str] = field(default_factory=list)
    new_path: list[str] = field(default_factory=list)
    path_prefix: str = "global"

    def apply(self, global_mapping: CommentedMap) -> list[MigrationChange]:
        """Apply the subtree-move migration rule.

        If the destination path already exists the new-schema subtree is preserved
        and the stale old subtree is removed without overwriting.

        Parameters:
            global_mapping: The 'global' section of the values.yaml.

        Returns:
            A list of changes made; empty if the source path was not found.
        """
        source = global_mapping
        source_parents: list[tuple[CommentedMap, str]] = []
        for key in self.old_path:
            if not isinstance(source, CommentedMap) or key not in source:
                return []
            source_parents.append((source, key))
            source = source[key]

        old_str = self.path_prefix + "." + ".".join(self.old_path)
        new_str = self.path_prefix + "." + ".".join(self.new_path)

        if _path_exists(global_mapping, self.new_path):
            parent_map, key_to_delete = source_parents[-1]
            _delete_key(parent_map, key_to_delete)
            for parent_map, key in reversed(source_parents[:-1]):
                if key in parent_map and isinstance(parent_map[key], CommentedMap) and len(parent_map[key]) == 0:
                    _delete_key(parent_map, key)
            return [MigrationChange(old_str, new_str, f"Removed stale {old_str} (kept existing {new_str})")]

        subtree = source

        dest_parent_keys = self.new_path[:-1]
        dest_leaf = self.new_path[-1]
        dest_parent = _ensure_nested_key(global_mapping, dest_parent_keys)
        dest_parent[dest_leaf] = subtree

        parent_map, key_to_delete = source_parents[-1]
        _delete_key(parent_map, key_to_delete)

        for parent_map, key in reversed(source_parents[:-1]):
            if key in parent_map and isinstance(parent_map[key], CommentedMap) and len(parent_map[key]) == 0:
                _delete_key(parent_map, key)

        return [MigrationChange(old_str, new_str, f"Moved subtree {old_str}.* -> {new_str}.*")]


@dataclass
class AddKeyIfMissing:
    """Add a key with a default value only if it does not already exist.

    Example: AddKeyIfMissing(["global", "plane"], {"mode": "unified", "domainPrefix": ""})
    """

    path: list[str] = field(default_factory=list)
    value: Any = None

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the add-key-if-missing rule."""
        if _path_exists(root, self.path):
            return []

        parent_keys = self.path[:-1]
        leaf = self.path[-1]

        parent = _ensure_nested_key(root, parent_keys) if parent_keys else root

        if isinstance(self.value, dict):
            cm = CommentedMap()
            for k, v in self.value.items():
                if isinstance(v, dict):
                    inner = CommentedMap()
                    for ik, iv in v.items():
                        inner[ik] = iv
                    cm[k] = inner
                else:
                    cm[k] = v
            parent[leaf] = cm
        else:
            parent[leaf] = self.value

        path_str = ".".join(self.path)
        return [MigrationChange("(new)", path_str, f"Added {path_str} with default value")]


GLOBAL_FEATURE_FLAG_RULES: list[BoolToNested | InvertedBoolToNested | SubtreeMove] = [
    BoolToNested("rbacEnabled", ["rbac", "enabled"]),
    BoolToNested("sccEnabled", ["scc", "enabled"]),
    BoolToNested("openshiftEnabled", ["openshift", "enabled"]),
    BoolToNested("networkNSLabels", ["networkNSLabels", "enabled"]),
    BoolToNested("namespaceFreeFormEntry", ["namespaceManagement", "namespaceFreeFormEntry", "enabled"]),
    BoolToNested("taskUsageMetricsEnabled", ["metricsReporting", "taskUsageMetrics", "enabled"]),
    BoolToNested("deployRollbackEnabled", ["deploymentLifecycle", "deployRollback", "enabled"]),
    SubtreeMove(["features", "namespacePools"], ["namespaceManagement", "namespacePools"]),
    SubtreeMove(["dagOnlyDeployment"], ["deployMechanisms", "dagOnlyDeployment"]),
    SubtreeMove(["loggingSidecar"], ["logging", "loggingSidecar"]),
    BoolToNested("podDisruptionBudgetsEnabled", ["podDisruptionBudgets", "enabled"]),
    BoolToNested("postgresqlEnabled", ["postgresql", "enabled"]),
    BoolToNested("prometheusPostgresExporterEnabled", ["prometheusPostgresExporter", "enabled"]),
    BoolToNested("nodeExporterEnabled", ["nodeExporter", "enabled"]),
    BoolToNested("manualNamespaceNamesEnabled", ["namespaceManagement", "manualNamespaceNames", "enabled"]),
    BoolToNested("enablePerHostIngress", ["perHostIngress", "enabled"]),
    BoolToNested("enableArgoCDAnnotation", ["argoCD", "annotation", "enabled"]),
    InvertedBoolToNested("disableManageClusterScopedResources", ["manageClusterScopedResources", "enabled"]),
    BoolToNested("astronomerEnabled", ["astronomer", "enabled"]),
    BoolToNested("nginxEnabled", ["nginx", "enabled"]),
    BoolToNested("alertmanagerEnabled", ["alertmanager", "enabled"]),
    BoolToNested("grafanaEnabled", ["grafana", "enabled"]),
    BoolToNested("kubeStateEnabled", ["kubeState", "enabled"]),
    BoolToNested("prometheusEnabled", ["prometheus", "enabled"]),
    BoolToNested("elasticsearchEnabled", ["elasticsearch", "enabled"]),
    BoolToNested("vectorEnabled", ["daemonsetLogging", "enabled"]),
    BoolToNested("fluentdEnabled", ["daemonsetLogging", "enabled"]),
]

HOUSTON_DEPLOYMENTS_PREFIX = "astronomer.houston.config.deployments"

# Renders houston-api ``DEPLOYMENTS_PATH_MIGRATIONS`` for Helm
# (``src/lib/deployments-config-path-migration/index.js``). Order is significant.
HOUSTON_DEPLOYMENT_PATH_MIGRATIONS: list[tuple[str, str | None, str]] = [
    ("performanceOptimizationModeEnabled", "performanceOptimization.enabled", "boolean-to-enabled"),
    ("upsertExtraIniAllowed", "upsertDeployment.extraIniAllowed", "move"),
    ("logHelmValues", "logHelmValues.enabled", "boolean-to-enabled"),
    ("airflowV3", "runtimeManagement.airflowV3", "boolean-to-airflowV3"),
    ("customImageShaEnabled", "runtimeManagement.customImageSha.enabled", "boolean-to-enabled"),
    (
        "enableListAllRuntimeVersions",
        "runtimeManagement.listAllRuntimeVersions.enabled",
        "boolean-to-enabled",
    ),
    (
        "runtimeEnvOverideSemverCheck",
        "runtimeManagement.runtimeEnvOverrideSemverCheck",
        "move",
    ),
    ("astroRuntimeReleasesFile", "runtimeManagement.astroRuntimeReleasesFile", "move"),
    (
        "airflowMinimumAstroRuntimeVersion",
        "runtimeManagement.airflowMinimumAstroRuntimeVersion",
        "move",
    ),
    ("loggingSidecar", "logging.loggingSidecar", "move"),
    ("elasticsearch", "logging.elasticsearch", "move"),
    (
        "configureDagDeployment",
        "deployMechanisms.configureDagDeployment.enabled",
        "boolean-to-enabled",
    ),
    ("dagOnlyDeployment", "deployMechanisms.dagOnlyDeployment.enabled", "boolean-to-enabled"),
    (
        "nfsMountDagDeployment",
        "deployMechanisms.nfsMountDagDeployment.enabled",
        "boolean-to-enabled",
    ),
    (
        "gitSyncDagDeployment",
        "deployMechanisms.gitSyncDagDeployment.enabled",
        "boolean-to-enabled",
    ),
    ("gitSyncRelay", "deployMechanisms.gitSyncRelay", "move"),
    ("triggererEnabled", "airflowComponents.triggerer.enabled", "boolean-to-enabled"),
    ("dagProcessorEnabled", "airflowComponents.dagProcessor.enabled", "boolean-to-enabled"),
    (
        "disableManageResourceQuotasAndLimitRanges",
        "resourceManagement.resourceQuotas.enabled",
        "invert-to-enabled",
    ),
    ("components", "resourceManagement.components", "move"),
    ("executors", "resourceManagement.executors", "move"),
    ("astroUnit", "resourceManagement.astroUnit", "move"),
    ("maxExtraCapacity", "resourceManagement.maxExtraCapacity", "move"),
    ("maxPodCapacity", "resourceManagement.maxPodCapacity", "move"),
    ("sidecars", "resourceManagement.sidecars", "move"),
    (
        "overProvisioningFactorMem",
        "resourceManagement.overProvisioningFactorMem",
        "move",
    ),
    (
        "overProvisioningFactorCPU",
        "resourceManagement.overProvisioningFactorCPU",
        "move",
    ),
    (
        "overProvisioningComponents",
        "resourceManagement.overProvisioningComponents",
        "move",
    ),
    (
        "manualReleaseNames",
        "namespaceManagement.manualReleaseNames.enabled",
        "boolean-to-enabled",
    ),
    (
        "manualNamespaceNames",
        "namespaceManagement.manualNamespaceNames.enabled",
        "boolean-to-enabled",
    ),
    (
        "namespaceFreeFormEntry",
        "namespaceManagement.namespaceFreeFormEntry",
        "object-or-boolean-to-nested",
    ),
    (
        "preDeploymentValidationHook",
        "namespaceManagement.namespaceFreeFormEntry.preDeploymentValidationHook",
        "move",
    ),
    (
        "preDeploymentValidationHookTimeout",
        "namespaceManagement.namespaceFreeFormEntry.preDeploymentValidationHookTimeout",
        "move",
    ),
    ("namespaceLabels", "namespaceManagement.namespaceLabels", "move"),
    (
        "preCreatedNamespaces",
        "namespaceManagement.preCreatedNamespaces",
        "move",
    ),
    (
        "deployRollback",
        "deploymentLifecycle.deployRollback",
        "object-or-boolean-to-nested",
    ),
    (
        "hardDeleteDeployment",
        "deploymentLifecycle.hardDeleteDeployment.enabled",
        "boolean-to-enabled",
    ),
    (
        "cleanupAirflowDb",
        "deploymentLifecycle.cleanupAirflowDb",
        "object-or-boolean-to-nested",
    ),
    ("database", "databaseManagement.database", "move"),
    (
        "manualConnectionStrings",
        "databaseManagement.manualConnectionStrings.enabled",
        "boolean-to-enabled",
    ),
    (
        "pgBouncerResourceCalculationStrategy",
        "databaseManagement.pgBouncerResourceCalculationStrategy",
        "move",
    ),
    (
        "exposeDockerWebhookEndpoint",
        "deploymentImagesRegistry.exposeDockerWebhookEndpoint.enabled",
        "boolean-to-enabled",
    ),
    (
        "enableUpdateDeploymentImageEndpoint",
        "deploymentImagesRegistry.updateDeploymentImageEndpoint.enabled",
        "boolean-to-enabled",
    ),
    (
        "enableUpdateDeploymentImageEndpointDockerValidation",
        "deploymentImagesRegistry.updateDeploymentImageEndpointDockerValidation.enabled",
        "boolean-to-enabled",
    ),
    (
        "serviceAccountAnnotationKey",
        "deploymentImagesRegistry.serviceAccountAnnotationKey",
        "move",
    ),
    ("grafanaUIEnabled", "metricsReporting.grafana.enabled", "boolean-to-enabled"),
    ("taskUsageReport", "metricsReporting.taskUsageMetrics", "taskUsageReport-to-taskUsageMetrics"),
    ("pagination", "metricsReporting.pagination", "move"),
    ("upsertDeploymentEnabled", None, "deprecated-unset"),
    (
        "canUpsertDeploymentFromUI",
        "upsertDeployment.allowFromUi.enabled",
        "boolean-to-enabled",
    ),
    ("enableSystemAdminCanCreateDeprecatedAirflows", None, "deprecated-unset"),
    ("defaultDistribution", None, "deprecated-unset"),
]

HOUSTON_DEPLOYMENT_CHART_ONLY_DELETE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "astroUnitsEnabled",
        "resourceProvisioningStrategy",
        "maxPodAu",
    }
)


def _cfg_get(obj: Any, key: str) -> Any:
    """Read a key from a ``dict`` or ``CommentedMap`` if present; else ``None``."""
    if isinstance(obj, (dict, CommentedMap)) and key in obj:
        return obj[key]
    return None


def _set_dotted_path_in_mapping(root: CommentedMap, dotted: str, value: Any) -> None:
    """Set ``value`` at a dotted key path, creating ``CommentedMap`` parents and replacing
    non-mapping intermediates, mirroring lodash ``set`` behavior.
    """
    parts = dotted.split(".")
    if not parts:
        return
    current: Any = root
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        if is_last:
            if not isinstance(current, CommentedMap):
                return
            current[part] = value
        else:
            if not isinstance(current, CommentedMap) or part not in current or not isinstance(current[part], CommentedMap):
                if not isinstance(current, CommentedMap):
                    return
                current[part] = CommentedMap()
            current = current[part]


def _tdv_boolean_to_enabled(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (dict, CommentedMap)) and "enabled" in value:
        return value["enabled"]
    return value


def _tdv_invert_to_enabled(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if value is not None and isinstance(value, (dict, CommentedMap)) and "enabled" in value:
        return not value["enabled"]
    return (not value) if value is not None else True


def _tdv_boolean_to_airflow_v3(value: Any) -> Any:
    if isinstance(value, bool):
        m = CommentedMap()
        m["enabled"] = value
        m["minimumAstroRuntimeVersion"] = "3.1-2"
        return m
    if value is not None and isinstance(value, (dict, CommentedMap)):
        e = _cfg_get(value, "enabled")
        mv = _cfg_get(value, "minimumAstroRuntimeVersion")
        out = CommentedMap()
        out["enabled"] = True if e is None else e
        out["minimumAstroRuntimeVersion"] = "3.1-2" if mv is None else mv
        return out
    m2 = CommentedMap()
    m2["enabled"] = bool(value)
    m2["minimumAstroRuntimeVersion"] = "3.1-2"
    return m2


def _tdv_object_or_boolean_to_nested(value: Any) -> Any:
    if isinstance(value, bool):
        o = CommentedMap()
        o["enabled"] = value
        return o
    if value is not None and isinstance(value, (dict, CommentedMap)):
        o2 = CommentedMap()
        for k, v in value.items():
            o2[k] = v
        e = _cfg_get(value, "enabled")
        o2["enabled"] = True if e is None else e
        return o2
    o3 = CommentedMap()
    o3["enabled"] = bool(value)
    return o3


def _tdv_task_usage_report_to_metrics(value: Any) -> Any:
    if isinstance(value, bool):
        t = CommentedMap()
        t["enabled"] = value
        t["reportNumberOfDays"] = 90
        return t
    if value is not None and isinstance(value, (dict, CommentedMap)):
        tme = _cfg_get(value, "taskUsageMetricsEnabled")
        en = _cfg_get(value, "enabled")
        tdays = _cfg_get(value, "taskUsageReportNumberOfDays")
        rdays = _cfg_get(value, "reportNumberOfDays")
        out2 = CommentedMap()
        out2["enabled"] = tme if tme is not None else (en if en is not None else True)
        out2["reportNumberOfDays"] = tdays if tdays is not None else (rdays if rdays is not None else 90)
        return out2
    t2 = CommentedMap()
    t2["enabled"] = bool(value)
    t2["reportNumberOfDays"] = 90
    return t2


def _transform_houston_deployment_value(value: Any, transform: str) -> Any:
    """Mirror ``transformValue`` in ``deployments-config-path-migration/index.js``."""
    match transform:
        case "boolean-to-enabled":
            return _tdv_boolean_to_enabled(value)
        case "invert-to-enabled":
            return _tdv_invert_to_enabled(value)
        case "move":
            return value
        case "boolean-to-airflowV3":
            return _tdv_boolean_to_airflow_v3(value)
        case "object-or-boolean-to-nested":
            return _tdv_object_or_boolean_to_nested(value)
        case "taskUsageReport-to-taskUsageMetrics":
            return _tdv_task_usage_report_to_metrics(value)
        case "deprecated-unset":
            return None
        case _:
            return value


def _apply_houston_deployments_path_migrations(
    deployments: CommentedMap,
) -> list[MigrationChange]:
    """Rewrite flat ``deployments`` keys the same as ``migrateDeploymentsConfig`` in houston-api."""
    changes: list[MigrationChange] = []
    for old_key, new_dotted, transform in HOUSTON_DEPLOYMENT_PATH_MIGRATIONS:
        if old_key not in deployments:
            continue
        if transform == "deprecated-unset":
            _delete_key(deployments, old_key)
            p = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{old_key}"
            changes.append(MigrationChange(p, "(deleted)", f"Deprecated key removed: {p}"))
            continue
        if not new_dotted:
            continue
        if _path_exists(deployments, new_dotted.split(".")):
            if not new_dotted.startswith(f"{old_key}."):
                _delete_key(deployments, old_key)
                p_old = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{old_key}"
                p_new = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{new_dotted}"
                changes.append(MigrationChange(p_old, p_new, f"Removed stale {p_old} (kept existing {p_new})"))
            continue
        old_value = deployments[old_key]
        new_value = _transform_houston_deployment_value(old_value, transform)
        _set_dotted_path_in_mapping(deployments, new_dotted, new_value)
        p_old = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{old_key}"
        p_new = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{new_dotted}"
        if not new_dotted.startswith(f"{old_key}."):
            _delete_key(deployments, old_key)
        changes.append(MigrationChange(p_old, p_new, f"Migrated {p_old} -> {p_new}"))
    return changes


HOUSTON_CONFIG_PREFIX = "astronomer.houston.config"

_OIDC_PREFIX = f"{HOUSTON_CONFIG_PREFIX}.auth.openidConnect"
_WS_PREFIX = f"{HOUSTON_CONFIG_PREFIX}.webserver"
_NATS_PREFIX = f"{HOUSTON_CONFIG_PREFIX}.nats"
_DPLINK_PREFIX = f"{HOUSTON_CONFIG_PREFIX}.workers.dplink"
_APOLLO_PREFIX = f"{HOUSTON_CONFIG_PREFIX}.apollo"
_MOCK_WH_PREFIX = f"{HOUSTON_CONFIG_PREFIX}.deployments.mockWebhook"
_HELM_PREFIX = f"{HOUSTON_CONFIG_PREFIX}.helm"

HOUSTON_CONFIG_RULES: list[tuple[list[str], BoolToNested | InvertedBoolToNested]] = [
    ([], BoolToNested("emailConfirmation", ["emailConfirmation", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX)),
    ([], BoolToNested("publicSignups", ["publicSignups", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX)),
    ([], BoolToNested("updateRuntimeCheckEnabled", ["updateRuntimeCheck", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX)),
    ([], BoolToNested("updateAirflowCheckEnabled", ["updateAirflowCheck", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX)),
    ([], BoolToNested("subdomainHttpsEnabled", ["subdomainHttps", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX)),
    (
        [],
        BoolToNested(
            "useAutoCompleteForSensitiveFields", ["autoCompleteForSensitiveFields", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX
        ),
    ),
    ([], BoolToNested("shouldLogUsername", ["logUsername", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX)),
    ([], InvertedBoolToNested("disableSSLVerify", ["sslVerification", "enabled"], path_prefix=HOUSTON_CONFIG_PREFIX)),
    (["auth", "openidConnect"], BoolToNested("idpGroupsImportEnabled", ["idpGroupsImport", "enabled"], path_prefix=_OIDC_PREFIX)),
    (["auth", "openidConnect"], BoolToNested("idpGroupsRefreshEnabled", ["idpGroupsRefresh", "enabled"], path_prefix=_OIDC_PREFIX)),
    (["auth", "openidConnect"], BoolToNested("insecureIDPTokenLog", ["insecureIDPTokenLog", "enabled"], path_prefix=_OIDC_PREFIX)),
    (["webserver"], BoolToNested("graphqlPlaygroundEnabled", ["graphqlPlayground", "enabled"], path_prefix=_WS_PREFIX)),
    (["nats"], BoolToNested("tlsEnabled", ["tls", "enabled"], path_prefix=_NATS_PREFIX)),
    (["workers", "dplink"], BoolToNested("debugEnabled", ["debug", "enabled"], path_prefix=_DPLINK_PREFIX)),
    (["apollo"], BoolToNested("auditMiddlewareEnabled", ["auditMiddleware", "enabled"], path_prefix=_APOLLO_PREFIX)),
    (["deployments", "mockWebhook"], BoolToNested("krbEnabled", ["krb", "enabled"], path_prefix=_MOCK_WH_PREFIX)),
    (["helm"], BoolToNested("rbacEnabled", ["rbac", "enabled"], path_prefix=_HELM_PREFIX)),
]

HOUSTON_CONFIG_MOVE_KEYS: list[tuple[list[str], str, list[str]]] = [
    (["deployments", "mockWebhook"], "krbRealm", ["krb", "realm"]),
]


def _clone_global_feature_flag_rule(
    rule: BoolToNested | InvertedBoolToNested | SubtreeMove,
    path_prefix: str,
) -> BoolToNested | InvertedBoolToNested | SubtreeMove:
    """Clone a global feature-flag rule with a different path prefix.

    Parameters:
        rule: The rule to clone.
        path_prefix: The dotted path prefix for change reporting.

    Returns:
        A cloned rule instance targeting the provided path prefix.
    """
    match rule:
        case BoolToNested(old_key=old_key, new_path=new_path):
            return BoolToNested(old_key, list(new_path), path_prefix=path_prefix)
        case InvertedBoolToNested(old_key=old_key, new_path=new_path):
            return InvertedBoolToNested(old_key, list(new_path), path_prefix=path_prefix)
        case SubtreeMove(old_path=old_path, new_path=new_path):
            return SubtreeMove(list(old_path), list(new_path), path_prefix=path_prefix)
        case _:
            raise TypeError(f"Unsupported global feature flag rule type: {type(rule)!r}")


def apply_global_feature_flag_rules(
    global_mapping: CommentedMap | None,
    *,
    path_prefix: str = "global",
) -> list[MigrationChange]:
    """Apply global-section feature-flag migrations (1.x / 0.37.x -> 2.x).

    Parameters:
        global_mapping: The `global` key from values.yaml, or None.
        path_prefix: The dotted path prefix used for change reporting.

    Returns:
        All migration changes applied under `global`.
    """
    if global_mapping is None or not isinstance(global_mapping, CommentedMap):
        return []
    changes: list[MigrationChange] = []
    for rule in GLOBAL_FEATURE_FLAG_RULES:
        cloned_rule = _clone_global_feature_flag_rule(rule, path_prefix)
        changes.extend(cloned_rule.apply(global_mapping))
    return changes


def apply_global_feature_flag_rules_to_all(root: CommentedMap) -> list[MigrationChange]:
    """Apply shared global feature-flag migrations to all ``*.global`` mappings.

    Parameters:
        root: The parsed YAML document root.

    Returns:
        All migration changes applied across every discovered ``global`` mapping.
    """
    changes: list[MigrationChange] = []
    for path_segments, global_mapping in iter_global_mappings(root):
        changes.extend(apply_global_feature_flag_rules(global_mapping, path_prefix=_path_to_str(path_segments)))
    return changes


def apply_houston_deployment_migrations(root: CommentedMap) -> list[MigrationChange]:
    """Apply Houston `config.deployments` path rewrites and chart-only deletions.

    Renders the same key order and transforms as
    `migrateDeploymentsConfig` in houston-api, plus deletions of keys
    that do not have a 2.x equivalent in Helm (see chart-only set).

    Parameters:
        root: The parsed YAML document root.

    Returns:
        All migration changes applied under `astronomer.houston.config.deployments`.
    """
    all_changes: list[MigrationChange] = []
    deployments = _get_nested_mapping(root, ["astronomer", "houston", "config", "deployments"])
    if deployments is None:
        return all_changes

    all_changes.extend(_apply_houston_deployments_path_migrations(deployments))

    for key in HOUSTON_DEPLOYMENT_CHART_ONLY_DELETE_KEYS:
        if key in deployments:
            _delete_key(deployments, key)
            path_str = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{key}"
            all_changes.append(MigrationChange(path_str, "(deleted)", f"Deleted obsolete key {path_str}"))

    return all_changes


def apply_nginx_csp_policy_migrations(root: CommentedMap) -> list[MigrationChange]:
    """Migrate `nginx.cspPolicy.cdnEnabled` to `nginx.cspPolicy.enabled`.

    Parameters:
        root: The parsed YAML document root.

    Returns:
        Migration changes applied under `nginx.cspPolicy`, if any.
    """
    nginx = _get_nested_mapping(root, ["nginx"])
    if nginx is None:
        return []
    csp_policy = _get_nested_mapping(nginx, ["cspPolicy"])
    if csp_policy is None:
        return []
    rule = BoolToNested("cdnEnabled", ["enabled"], path_prefix="nginx.cspPolicy")
    return rule.apply(csp_policy)


def apply_houston_config_flag_migrations(root: CommentedMap) -> list[MigrationChange]:
    """Apply Houston `config` flag migrations (flat booleans -> nested `.enabled`).

    Handles passthrough config keys under `astronomer.houston.config` that
    Houston PR #2417 migrated to nested `.enabled` paths, including keys in
    nested sub-sections like `auth.openidConnect` and `webserver`.

    Parameters:
        root: The parsed YAML document root.

    Returns:
        All migration changes applied under `astronomer.houston.config`.
    """
    config = _get_nested_mapping(root, ["astronomer", "houston", "config"])
    if config is None:
        return []

    changes: list[MigrationChange] = []

    for section_path, rule in HOUSTON_CONFIG_RULES:
        section = _get_nested_mapping(config, section_path) if section_path else config
        if section is None:
            continue
        changes.extend(rule.apply(section))

    for section_path, old_key, new_path in HOUSTON_CONFIG_MOVE_KEYS:
        section = _get_nested_mapping(config, section_path) if section_path else config
        if section is None or old_key not in section:
            continue
        prefix = HOUSTON_CONFIG_PREFIX + ("." + ".".join(section_path) if section_path else "")
        old_str = f"{prefix}.{old_key}"
        new_str = f"{prefix}.{'.'.join(new_path)}"
        if _path_exists(section, new_path):
            _delete_key(section, old_key)
            changes.append(MigrationChange(old_str, new_str, f"Removed stale {old_str} (kept existing {new_str})"))
        else:
            value = section[old_key]
            parent = _ensure_nested_key(section, new_path[:-1])
            parent[new_path[-1]] = value
            _delete_key(section, old_key)
            changes.append(MigrationChange(old_str, new_str, f"Moved {old_str} -> {new_str}"))

    return changes


def load_yaml(input_path: Path) -> tuple[YAML, Any]:
    """Load a YAML file using round-trip mode.

    Parameters:
        input_path: Path to the YAML file.

    Returns:
        A tuple of (YAML instance, parsed document).
    """
    yml = create_yaml()
    data = yml.load(input_path)
    return yml, data


def dump_yaml(yml: YAML, data: Any, output: Path | None = None) -> str | None:
    """Dump YAML data to a file or return as string.

    Parameters:
        yml: The YAML instance to use for dumping.
        data: The parsed YAML document.
        output: Optional output path. If None, returns the YAML as a string.

    Returns:
        The YAML string if output is None, otherwise None.
    """
    if output is not None:
        yml.dump(data, output)
        return None

    stream = StringIO()
    yml.dump(data, stream)
    return stream.getvalue()
