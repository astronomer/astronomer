#!/usr/bin/env python3

"""Migrate Astronomer Helm chart values.yaml from 0.37.x to 2.x schema.

Transforms customer override values files from the 0.37.x schema to the new
2.x schema introduced in chart version 2.0. This migration is a superset of
the 1.x-to-2.x migration: it includes the same feature-flag restructuring
plus additional deletions of obsolete keys (stan, kibana, fluentd, blackbox),
renames (fluentd -> vector, pgbouncer secret), value updates, and injection
of new required keys.

Usage:
    ./bin/migrate-helm-chart-values-037x-to-2x.py my-values.yaml
    ./bin/migrate-helm-chart-values-037x-to-2x.py --dry-run my-values.yaml
    ./bin/migrate-helm-chart-values-037x-to-2x.py --in-place --backup my-values.yaml
    ./bin/migrate-helm-chart-values-037x-to-2x.py my-values.yaml migrated-values.yaml
"""

from __future__ import annotations

import argparse
import sys
from abc import ABC, abstractmethod
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _resolve_parent(mapping: CommentedMap, keys: list[str]) -> tuple[CommentedMap | None, str]:
    """Resolve a dotted path to its parent mapping and leaf key.

    Parameters:
        mapping: The root mapping.
        keys: List of key segments forming the path.

    Returns:
        Tuple of (parent CommentedMap, leaf key string), or (None, "") if the
        parent path does not exist.
    """
    if not keys:
        return None, ""
    parent: Any = mapping
    for key in keys[:-1]:
        if not isinstance(parent, CommentedMap) or key not in parent:
            return None, ""
        parent = parent[key]
    if not isinstance(parent, CommentedMap):
        return None, ""
    return parent, keys[-1]


# ---------------------------------------------------------------------------
# Rule base class
# ---------------------------------------------------------------------------


@dataclass
class MigrationChange:
    """Record of a single migration transformation applied."""

    old_path: str
    new_path: str
    description: str


class MigrationRule(ABC):
    """Base class for a values.yaml migration rule."""

    @abstractmethod
    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply this migration rule to the full document root.

        Parameters:
            root: The parsed YAML document root as a CommentedMap.

        Returns:
            A list of MigrationChange records describing what was changed.
        """


# ---------------------------------------------------------------------------
# Rule: BoolToNested (operates on global section)
# ---------------------------------------------------------------------------


@dataclass
class BoolToNested(MigrationRule):
    """Migrate a flat boolean key to a nested .enabled structure under global.

    Example: global.rbacEnabled: true -> global.rbac.enabled: true
    """

    old_key: str
    new_path: list[str] = field(default_factory=list)

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the boolean-to-nested migration rule.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made.
        """
        global_mapping = root.get("global")
        if not isinstance(global_mapping, CommentedMap):
            return []

        if self.old_key not in global_mapping:
            return []

        value = global_mapping[self.old_key]
        if isinstance(value, CommentedMap):
            return []

        if _path_exists(global_mapping, self.new_path):
            _delete_key(global_mapping, self.old_key)
            old_path = f"global.{self.old_key}"
            new_path = "global." + ".".join(self.new_path)
            return [MigrationChange(old_path, new_path, f"Removed stale {old_path} (kept existing {new_path})")]

        inline_comment = _extract_inline_comment(global_mapping, self.old_key)

        parent_keys = self.new_path[:-1]
        leaf_key = self.new_path[-1]

        if parent_keys and parent_keys[0] == self.old_key:
            new_map = CommentedMap()
            inner = _ensure_nested_key(new_map, parent_keys[1:]) if len(parent_keys) > 1 else new_map
            inner[leaf_key] = value
            global_mapping[self.old_key] = new_map
        else:
            parent = _ensure_nested_key(global_mapping, parent_keys)
            parent[leaf_key] = value
            if inline_comment:
                _attach_inline_comment(parent, leaf_key, inline_comment)
            _delete_key(global_mapping, self.old_key)

        old_path = f"global.{self.old_key}"
        new_path = "global." + ".".join(self.new_path)
        return [MigrationChange(old_path, new_path, f"Moved {old_path} -> {new_path}")]


# ---------------------------------------------------------------------------
# Rule: InvertedBoolToNested (operates on global section)
# ---------------------------------------------------------------------------


@dataclass
class InvertedBoolToNested(MigrationRule):
    """Migrate a flat boolean key to a nested .enabled structure with inverted value.

    Example: global.disableManageClusterScopedResources: false
          -> global.manageClusterScopedResources.enabled: true
    """

    old_key: str
    new_path: list[str] = field(default_factory=list)

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the inverted boolean-to-nested migration rule.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made.
        """
        global_mapping = root.get("global")
        if not isinstance(global_mapping, CommentedMap):
            return []

        if self.old_key not in global_mapping:
            return []

        value = global_mapping[self.old_key]
        if isinstance(value, CommentedMap):
            return []

        if _path_exists(global_mapping, self.new_path):
            _delete_key(global_mapping, self.old_key)
            old_path = f"global.{self.old_key}"
            new_path = "global." + ".".join(self.new_path)
            return [MigrationChange(old_path, new_path, f"Removed stale {old_path} (kept existing {new_path})")]

        inverted = not value if isinstance(value, bool) else value

        parent_keys = self.new_path[:-1]
        leaf_key = self.new_path[-1]

        parent = _ensure_nested_key(global_mapping, parent_keys)
        parent[leaf_key] = inverted
        _delete_key(global_mapping, self.old_key)

        old_path = f"global.{self.old_key}"
        new_path = "global." + ".".join(self.new_path)
        return [MigrationChange(old_path, new_path, f"Moved (inverted) {old_path} -> {new_path}")]


# ---------------------------------------------------------------------------
# Rule: SubtreeMove (operates on global section)
# ---------------------------------------------------------------------------


@dataclass
class SubtreeMove(MigrationRule):
    """Move an entire subtree from one location to another under global.

    Example: global.dagOnlyDeployment.* -> global.deployMechanisms.dagOnlyDeployment.*
    """

    old_path: list[str] = field(default_factory=list)
    new_path: list[str] = field(default_factory=list)

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the subtree-move migration rule.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made.
        """
        global_mapping = root.get("global")
        if not isinstance(global_mapping, CommentedMap):
            return []

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


# ---------------------------------------------------------------------------
# Rule: DeleteKey (operates on full document)
# ---------------------------------------------------------------------------


@dataclass
class DeleteKey(MigrationRule):
    """Delete a key at an arbitrary dotted path in the document.

    Example: DeleteKey(["global", "singleNamespace"]) removes global.singleNamespace
    Example: DeleteKey(["kibana"]) removes the top-level kibana section
    """

    path: list[str] = field(default_factory=list)

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the delete-key rule.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made; empty if the key was not found.
        """
        parent, leaf = _resolve_parent(root, self.path)
        if parent is None or leaf not in parent:
            return []

        _delete_key(parent, leaf)

        path_str = ".".join(self.path)
        return [MigrationChange(path_str, "(deleted)", f"Deleted obsolete key {path_str}")]


# ---------------------------------------------------------------------------
# Rule: RenameKey (operates on full document)
# ---------------------------------------------------------------------------


@dataclass
class RenameKey(MigrationRule):
    """Rename a key in-place, preserving its value and position.

    The path identifies the parent + old key name; new_name is the replacement.

    Example: RenameKey(["fluentd"], "vector") renames the top-level fluentd key.
    Example: RenameKey(["global", "pgbouncer", "krb5ConfSecretName"], "secretName")
    """

    path: list[str] = field(default_factory=list)
    new_name: str = ""

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the rename-key rule.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made; empty if the old key was not found.
        """
        parent, old_leaf = _resolve_parent(root, self.path)
        if parent is None or old_leaf not in parent:
            return []

        if self.new_name in parent:
            _delete_key(parent, old_leaf)
            old_str = ".".join(self.path)
            new_path = [*list(self.path[:-1]), self.new_name]
            new_str = ".".join(new_path)
            return [MigrationChange(old_str, new_str, f"Removed stale {old_str} (kept existing {new_str})")]

        value = parent[old_leaf]
        inline_comment = _extract_inline_comment(parent, old_leaf)

        items = list(parent.keys())
        idx = items.index(old_leaf)

        _delete_key(parent, old_leaf)

        new_items = list(parent.items())
        new_items.insert(idx, (self.new_name, value))
        parent.clear()
        for k, v in new_items:
            parent[k] = v

        if inline_comment:
            _attach_inline_comment(parent, self.new_name, inline_comment)

        old_str = ".".join(self.path)
        new_path = [*list(self.path[:-1]), self.new_name]
        new_str = ".".join(new_path)
        return [MigrationChange(old_str, new_str, f"Renamed {old_str} -> {new_str}")]


# ---------------------------------------------------------------------------
# Rule: SetValue (operates on full document)
# ---------------------------------------------------------------------------


@dataclass
class SetValue(MigrationRule):
    """Update a value at a path only if it currently matches the expected old value.

    Example: SetValue(["global", "pgbouncer", "servicePort"], "5432", "6543")
    """

    path: list[str] = field(default_factory=list)
    old_value: Any = None
    new_value: Any = None

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the set-value rule.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made; empty if the key was not found or the value
            did not match the expected old value.
        """
        parent, leaf = _resolve_parent(root, self.path)
        if parent is None or leaf not in parent:
            return []

        current = parent[leaf]
        if current != self.old_value:
            return []

        inline_comment = _extract_inline_comment(parent, leaf)
        parent[leaf] = self.new_value
        if inline_comment:
            _attach_inline_comment(parent, leaf, inline_comment)

        path_str = ".".join(self.path)
        return [
            MigrationChange(
                path_str,
                path_str,
                f"Updated {path_str}: {self.old_value!r} -> {self.new_value!r}",
            )
        ]


# ---------------------------------------------------------------------------
# Rule: AddKeyIfMissing (operates on full document)
# ---------------------------------------------------------------------------


@dataclass
class AddKeyIfMissing(MigrationRule):
    """Add a key with a default value only if it does not already exist.

    Example: AddKeyIfMissing(["global", "plane"], {"mode": "unified", "domainPrefix": ""})
    """

    path: list[str] = field(default_factory=list)
    value: Any = None

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the add-key-if-missing rule.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made; empty if the key already exists.
        """
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


# ---------------------------------------------------------------------------
# Rule: HoustonDeploymentBoolToNested (operates on astronomer.houston.config.deployments)
# ---------------------------------------------------------------------------

_HOUSTON_PREFIX = "astronomer.houston.config.deployments"


@dataclass
class HoustonDeploymentBoolToNested(MigrationRule):
    """Migrate a flat boolean key under astronomer.houston.config.deployments to nested .enabled.

    Example: astronomer.houston.config.deployments.dagProcessorEnabled: true
          -> astronomer.houston.config.deployments.airflowComponents.dagProcessor.enabled: true
    """

    old_key: str
    new_path: list[str] = field(default_factory=list)

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the boolean-to-nested migration on the Houston deployments config section.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made.
        """
        deployments = _get_nested_mapping(root, ["astronomer", "houston", "config", "deployments"])
        if deployments is None:
            return []

        if self.old_key not in deployments:
            return []

        value = deployments[self.old_key]
        if isinstance(value, CommentedMap):
            return []

        if _path_exists(deployments, self.new_path):
            _delete_key(deployments, self.old_key)
            old_path = f"{_HOUSTON_PREFIX}.{self.old_key}"
            new_path = _HOUSTON_PREFIX + "." + ".".join(self.new_path)
            return [MigrationChange(old_path, new_path, f"Removed stale {old_path} (kept existing {new_path})")]

        inline_comment = _extract_inline_comment(deployments, self.old_key)

        parent_keys = self.new_path[:-1]
        leaf_key = self.new_path[-1]

        parent = _ensure_nested_key(deployments, parent_keys)
        parent[leaf_key] = value
        if inline_comment:
            _attach_inline_comment(parent, leaf_key, inline_comment)
        _delete_key(deployments, self.old_key)

        old_path = f"{_HOUSTON_PREFIX}.{self.old_key}"
        new_path = _HOUSTON_PREFIX + "." + ".".join(self.new_path)
        return [MigrationChange(old_path, new_path, f"Moved {old_path} -> {new_path}")]


# ---------------------------------------------------------------------------
# Rule: HoustonDeploymentDeleteKey (operates on astronomer.houston.config.deployments)
# ---------------------------------------------------------------------------


@dataclass
class HoustonDeploymentDeleteKey(MigrationRule):
    """Delete a key from astronomer.houston.config.deployments.

    Example: HoustonDeploymentDeleteKey("astroUnitsEnabled") removes the deprecated flag.
    """

    key: str

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the delete-key rule on the Houston deployments config section.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made; empty if the key was not found.
        """
        deployments = _get_nested_mapping(root, ["astronomer", "houston", "config", "deployments"])
        if deployments is None or self.key not in deployments:
            return []

        _delete_key(deployments, self.key)
        path_str = f"{_HOUSTON_PREFIX}.{self.key}"
        return [MigrationChange(path_str, "(deleted)", f"Deleted obsolete key {path_str}")]


# ---------------------------------------------------------------------------
# Rule: HoustonDeploymentMove (operates on astronomer.houston.config.deployments)
# ---------------------------------------------------------------------------


@dataclass
class HoustonDeploymentMove(MigrationRule):
    """Move a key to a new nested path under astronomer.houston.config.deployments.

    Example: HoustonDeploymentMove("serviceAccountAnnotationKey",
                                   ["deploymentImagesRegistry", "serviceAccountAnnotationKey"])
    """

    old_key: str
    new_path: list[str] = field(default_factory=list)

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the move rule on the Houston deployments config section.

        Parameters:
            root: The parsed YAML document root.

        Returns:
            A list of changes made; empty if the key was not found.
        """
        deployments = _get_nested_mapping(root, ["astronomer", "houston", "config", "deployments"])
        if deployments is None or self.old_key not in deployments:
            return []

        old_str = f"{_HOUSTON_PREFIX}.{self.old_key}"
        new_str = _HOUSTON_PREFIX + "." + ".".join(self.new_path)

        if _path_exists(deployments, self.new_path):
            _delete_key(deployments, self.old_key)
        else:
            value = deployments[self.old_key]
            parent = _ensure_nested_key(deployments, self.new_path[:-1])
            parent[self.new_path[-1]] = value
            _delete_key(deployments, self.old_key)

        return [MigrationChange(old_str, new_str, f"Moved {old_str} -> {new_str}")]


# ---------------------------------------------------------------------------
# Migration rule list
# ---------------------------------------------------------------------------


MIGRATIONS: list[MigrationRule] = [
    # --- A. Restructuring (same as 1.x->2.x) ---
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
    # --- A2. Global flat boolean flags restructuring ---
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
    # --- B. Delete obsolete global keys ---
    DeleteKey(["global", "singleNamespace"]),
    DeleteKey(["global", "veleroEnabled"]),
    DeleteKey(["global", "enableHoustonInternalAuthorization"]),
    DeleteKey(["global", "nodeExporterSccEnabled"]),
    DeleteKey(["global", "stan"]),
    # --- C. Delete obsolete top-level / tags keys ---
    DeleteKey(["tags", "stan"]),
    DeleteKey(["stan"]),
    DeleteKey(["kibana"]),
    DeleteKey(["prometheus-blackbox-exporter"]),
    # --- D. Renames ---
    RenameKey(["fluentd"], "vector"),
    RenameKey(["global", "pgbouncer", "krb5ConfSecretName"], "secretName"),
    # --- E. Value updates ---
    SetValue(["global", "pgbouncer", "servicePort"], old_value="5432", new_value="6543"),
    SetValue(["global", "nats", "jetStream", "enabled"], old_value=False, new_value=True),
    # --- F. Add new keys with defaults ---
    AddKeyIfMissing(["global", "authHeaderSecretName"], value=None),
    AddKeyIfMissing(["global", "plane"], value={"mode": "unified", "domainPrefix": ""}),
    AddKeyIfMissing(["global", "podLabels"], value={}),
    AddKeyIfMissing(["global", "logging", "provider"], value=None),
    AddKeyIfMissing(
        ["nats", "init"],
        value={
            "resources": {
                "requests": {"cpu": "75m", "memory": "30Mi"},
                "limits": {"cpu": "250m", "memory": "100Mi"},
            },
        },
    ),
    # --- G. Houston config deployments boolean-to-enabled restructuring ---
    HoustonDeploymentBoolToNested("dagProcessorEnabled", ["airflowComponents", "dagProcessor", "enabled"]),
    HoustonDeploymentBoolToNested("triggererEnabled", ["airflowComponents", "triggerer", "enabled"]),
    HoustonDeploymentBoolToNested("configureDagDeployment", ["deployMechanisms", "configureDagDeployment", "enabled"]),
    HoustonDeploymentBoolToNested("gitSyncDagDeployment", ["deployMechanisms", "gitSyncDagDeployment", "enabled"]),
    HoustonDeploymentBoolToNested("nfsMountDagDeployment", ["deployMechanisms", "nfsMountDagDeployment", "enabled"]),
    HoustonDeploymentBoolToNested("enableListAllRuntimeVersions", ["runtimeManagement", "listAllRuntimeVersions", "enabled"]),
    HoustonDeploymentBoolToNested(
        "enableUpdateDeploymentImageEndpoint", ["deploymentImagesRegistry", "updateDeploymentImageEndpoint", "enabled"]
    ),
    HoustonDeploymentBoolToNested("grafanaUIEnabled", ["metricsReporting", "grafana", "enabled"]),
    HoustonDeploymentBoolToNested("hardDeleteDeployment", ["deploymentLifecycle", "hardDeleteDeployment", "enabled"]),
    HoustonDeploymentBoolToNested("logHelmValues", ["logHelmValues", "enabled"]),
    HoustonDeploymentBoolToNested("manualReleaseNames", ["namespaceManagement", "manualReleaseNames", "enabled"]),
    # --- H. Houston config deployments key moves ---
    HoustonDeploymentMove("pgBouncerResourceCalculationStrategy", ["databaseManagement", "pgBouncerResourceCalculationStrategy"]),
    HoustonDeploymentMove("serviceAccountAnnotationKey", ["deploymentImagesRegistry", "serviceAccountAnnotationKey"]),
    # --- I. Houston config deployments obsolete keys ---
    HoustonDeploymentDeleteKey("astroUnitsEnabled"),
    HoustonDeploymentDeleteKey("resourceProvisioningStrategy"),
    HoustonDeploymentDeleteKey("maxPodAu"),
    HoustonDeploymentDeleteKey("upsertDeploymentEnabled"),
    HoustonDeploymentDeleteKey("canUpsertDeploymentFromUI"),
    HoustonDeploymentDeleteKey("enableSystemAdminCanCreateDeprecatedAirflows"),
]


# ---------------------------------------------------------------------------
# Migration entry point
# ---------------------------------------------------------------------------


def migrate_values(data: Any) -> list[MigrationChange]:
    """Apply all migration rules to a parsed YAML document.

    Parameters:
        data: The parsed YAML document (CommentedMap or None).

    Returns:
        A list of all MigrationChange records for transformations applied.
    """
    if data is None or not isinstance(data, CommentedMap):
        return []

    all_changes: list[MigrationChange] = []
    for rule in MIGRATIONS:
        changes = rule.apply(data)
        all_changes.extend(changes)

    return all_changes


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        The configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Migrate Astronomer Helm chart values.yaml from 0.37.x to 2.x schema.",
        epilog="Run with --dry-run first to preview changes before modifying files.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the customer values.yaml file to migrate.",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="Path for migrated output. Defaults to stdout if not specified.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify the input file directly.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a .bak backup before in-place modification.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing any files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the migration script.

    Parameters:
        argv: Command-line arguments. Defaults to sys.argv[1:] if None.

    Returns:
        Exit code: 0 for success, 1 for errors.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path: Path = args.input
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    if args.in_place and args.output:
        print("Error: Cannot use --in-place with an output file argument.", file=sys.stderr)
        return 1

    yml, data = load_yaml(input_path)
    changes = migrate_values(data)

    if args.dry_run:
        if not changes:
            print("No migrations needed. Values file is already up to date.", file=sys.stderr)
        else:
            print(f"Found {len(changes)} migration(s) to apply:", file=sys.stderr)
            for change in changes:
                print(f"  {change.old_path} -> {change.new_path}: {change.description}", file=sys.stderr)
        return 0

    if args.in_place:
        if args.backup:
            backup_path = input_path.with_suffix(input_path.suffix + ".bak")
            backup_path.write_text(input_path.read_text())
            print(f"Backup saved to {backup_path}", file=sys.stderr)
        dump_yaml(yml, data, input_path)
        if changes:
            print(f"Applied {len(changes)} migration(s) to {input_path}", file=sys.stderr)
        else:
            print("No migrations needed. File unchanged.", file=sys.stderr)
    elif args.output:
        dump_yaml(yml, data, args.output)
        if changes:
            print(f"Applied {len(changes)} migration(s). Output written to {args.output}", file=sys.stderr)
        else:
            print("No migrations needed. Output written unchanged.", file=sys.stderr)
    else:
        result = dump_yaml(yml, data)
        sys.stdout.write(result or "")

    return 0


if __name__ == "__main__":
    sys.exit(main())
