"""Shared migration helpers and rules for 1.x / 0.37.x -> 2.x Helm values.

Used by ``migrate-helm-chart-values-1x-to-2x.py`` and
``migrate-helm-chart-values-037x-to-2x.py`` so feature-flag restructuring stays
in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

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

        old_str = "global." + ".".join(self.old_path)
        new_str = "global." + ".".join(self.new_path)

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
    BoolToNested("vectorEnabled", ["vector", "enabled"]),
]

HOUSTON_DEPLOYMENTS_PREFIX = "astronomer.houston.config.deployments"

HOUSTON_DEPLOYMENT_BOOL_RULES: list[BoolToNested] = [
    BoolToNested("dagProcessorEnabled", ["airflowComponents", "dagProcessor", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX),
    BoolToNested("triggererEnabled", ["airflowComponents", "triggerer", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX),
    BoolToNested(
        "configureDagDeployment", ["deployMechanisms", "configureDagDeployment", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX
    ),
    BoolToNested(
        "gitSyncDagDeployment", ["deployMechanisms", "gitSyncDagDeployment", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX
    ),
    BoolToNested(
        "nfsMountDagDeployment", ["deployMechanisms", "nfsMountDagDeployment", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX
    ),
    BoolToNested(
        "enableListAllRuntimeVersions",
        ["runtimeManagement", "listAllRuntimeVersions", "enabled"],
        path_prefix=HOUSTON_DEPLOYMENTS_PREFIX,
    ),
    BoolToNested(
        "enableUpdateDeploymentImageEndpoint",
        ["deploymentImagesRegistry", "updateDeploymentImageEndpoint", "enabled"],
        path_prefix=HOUSTON_DEPLOYMENTS_PREFIX,
    ),
    BoolToNested("grafanaUIEnabled", ["metricsReporting", "grafana", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX),
    BoolToNested(
        "hardDeleteDeployment", ["deploymentLifecycle", "hardDeleteDeployment", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX
    ),
    BoolToNested("logHelmValues", ["logHelmValues", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX),
    BoolToNested(
        "manualReleaseNames", ["namespaceManagement", "manualReleaseNames", "enabled"], path_prefix=HOUSTON_DEPLOYMENTS_PREFIX
    ),
]

HOUSTON_DEPLOYMENT_MOVE_KEYS: list[tuple[str, list[str]]] = [
    ("pgBouncerResourceCalculationStrategy", ["databaseManagement", "pgBouncerResourceCalculationStrategy"]),
    ("serviceAccountAnnotationKey", ["deploymentImagesRegistry", "serviceAccountAnnotationKey"]),
]

HOUSTON_DEPLOYMENT_DELETE_KEYS: list[str] = [
    "astroUnitsEnabled",
    "resourceProvisioningStrategy",
    "maxPodAu",
    "upsertDeploymentEnabled",
    "canUpsertDeploymentFromUI",
    "enableSystemAdminCanCreateDeprecatedAirflows",
]


def apply_global_feature_flag_rules(global_mapping: CommentedMap | None) -> list[MigrationChange]:
    """Apply global-section feature-flag migrations (1.x / 0.37.x -> 2.x).

    Parameters:
        global_mapping: The ``global`` key from values.yaml, or None.

    Returns:
        All migration changes applied under ``global``.
    """
    if global_mapping is None or not isinstance(global_mapping, CommentedMap):
        return []
    changes: list[MigrationChange] = []
    for rule in GLOBAL_FEATURE_FLAG_RULES:
        changes.extend(rule.apply(global_mapping))
    return changes


def apply_houston_deployment_migrations(root: CommentedMap) -> list[MigrationChange]:
    """Apply Houston ``config.deployments`` bool, move, and delete migrations.

    Parameters:
        root: The parsed YAML document root.

    Returns:
        All migration changes applied under ``astronomer.houston.config.deployments``.
    """
    all_changes: list[MigrationChange] = []
    deployments = _get_nested_mapping(root, ["astronomer", "houston", "config", "deployments"])
    if deployments is None:
        return all_changes

    for rule in HOUSTON_DEPLOYMENT_BOOL_RULES:
        all_changes.extend(rule.apply(deployments))

    for old_key, new_path in HOUSTON_DEPLOYMENT_MOVE_KEYS:
        if old_key not in deployments:
            continue
        if _path_exists(deployments, new_path):
            _delete_key(deployments, old_key)
        else:
            value = deployments[old_key]
            parent = _ensure_nested_key(deployments, new_path[:-1])
            parent[new_path[-1]] = value
            _delete_key(deployments, old_key)
        old_str = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{old_key}"
        new_str = HOUSTON_DEPLOYMENTS_PREFIX + "." + ".".join(new_path)
        all_changes.append(MigrationChange(old_str, new_str, f"Moved {old_str} -> {new_str}"))

    for key in HOUSTON_DEPLOYMENT_DELETE_KEYS:
        if key in deployments:
            _delete_key(deployments, key)
            path_str = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{key}"
            all_changes.append(MigrationChange(path_str, "(deleted)", f"Deleted obsolete key {path_str}"))

    return all_changes


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
