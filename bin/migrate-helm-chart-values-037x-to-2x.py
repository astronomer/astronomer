#!/usr/bin/env python3

"""Migrate Astronomer Helm chart values.yaml from 0.37.x to 2.x schema.

Transforms customer override values files from the 0.37.x schema to the new
2.x schema introduced in chart version 2.0. This migration is a superset of
the 1.x-to-2.x migration: it includes the same feature-flag restructuring
(see ``helm_chart_values_migration_shared``) plus additional deletions of
obsolete keys (stan, kibana, fluentd, blackbox), renames (fluentd -> vector,
pgbouncer secret), value updates, and injection of new required keys.

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
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

_BIN = Path(__file__).resolve().parent
if str(_BIN) not in sys.path:
    sys.path.insert(0, str(_BIN))

import helm_chart_values_migration_shared as _shared  # noqa: E402
from helm_chart_values_migration_shared import (  # noqa: E402
    HOUSTON_DEPLOYMENTS_PREFIX,
    MigrationChange,
    apply_global_feature_flag_rules,
    apply_houston_config_flag_migrations,
    apply_houston_deployment_migrations,
    apply_nginx_csp_policy_migrations,
    dump_yaml,
    load_yaml,
)


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


class MigrationRule(ABC):
    """Base class for a values.yaml migration rule that operates on the document root."""

    @abstractmethod
    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply this migration rule to the full document root.

        Parameters:
            root: The parsed YAML document root as a CommentedMap.

        Returns:
            A list of MigrationChange records describing what was changed.
        """


@dataclass
class BoolToNested(MigrationRule):
    """Applies shared boolean-to-nested migration on ``root['global']``."""

    old_key: str
    new_path: list[str] = field(default_factory=list)
    _inner: _shared.BoolToNested = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_inner", _shared.BoolToNested(self.old_key, self.new_path))

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the boolean-to-nested migration rule under ``global``."""
        global_mapping = root.get("global")
        if not isinstance(global_mapping, CommentedMap):
            return []
        return self._inner.apply(global_mapping)


@dataclass
class SubtreeMove(MigrationRule):
    """Applies shared subtree move on ``root['global']``."""

    old_path: list[str] = field(default_factory=list)
    new_path: list[str] = field(default_factory=list)
    _inner: _shared.SubtreeMove = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_inner", _shared.SubtreeMove(self.old_path, self.new_path))

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the subtree-move migration rule under ``global``."""
        global_mapping = root.get("global")
        if not isinstance(global_mapping, CommentedMap):
            return []
        return self._inner.apply(global_mapping)


@dataclass
class DeleteKey(MigrationRule):
    """Delete a key at an arbitrary dotted path in the document.

    Example: DeleteKey(["global", "singleNamespace"]) removes global.singleNamespace
    Example: DeleteKey(["kibana"]) removes the top-level kibana section
    """

    path: list[str] = field(default_factory=list)

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the delete-key rule."""
        parent, leaf = _resolve_parent(root, self.path)
        if parent is None or leaf not in parent:
            return []

        _shared._delete_key(parent, leaf)

        path_str = ".".join(self.path)
        return [MigrationChange(path_str, "(deleted)", f"Deleted obsolete key {path_str}")]


@dataclass
class RenameKey(MigrationRule):
    """Rename a key in-place, preserving its value and position.

    The path identifies the parent + old key name; new_name is the replacement.

    Example: RenameKey(["fluentd"], "vector") renames the top-level Fluentd config subtree.
    The logging feature flag migration is separate:
    global.fluentdEnabled -> global.daemonsetLogging.enabled
    Example: RenameKey(["global", "pgbouncer", "krb5ConfSecretName"], "secretName")
    """

    path: list[str] = field(default_factory=list)
    new_name: str = ""

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the rename-key rule."""
        parent, old_leaf = _resolve_parent(root, self.path)
        if parent is None or old_leaf not in parent:
            return []

        if self.new_name in parent:
            _shared._delete_key(parent, old_leaf)
            old_str = ".".join(self.path)
            new_path = [*list(self.path[:-1]), self.new_name]
            new_str = ".".join(new_path)
            return [MigrationChange(old_str, new_str, f"Removed stale {old_str} (kept existing {new_str})")]

        value = parent[old_leaf]
        inline_comment = _shared._extract_inline_comment(parent, old_leaf)

        items = list(parent.keys())
        idx = items.index(old_leaf)

        _shared._delete_key(parent, old_leaf)

        new_items = list(parent.items())
        new_items.insert(idx, (self.new_name, value))
        parent.clear()
        for k, v in new_items:
            parent[k] = v

        if inline_comment:
            _shared._attach_inline_comment(parent, self.new_name, inline_comment)

        old_str = ".".join(self.path)
        new_path = [*list(self.path[:-1]), self.new_name]
        new_str = ".".join(new_path)
        return [MigrationChange(old_str, new_str, f"Renamed {old_str} -> {new_str}")]


@dataclass
class SetValue(MigrationRule):
    """Update a value at a path only if it currently matches the expected old value.

    Example: SetValue(["global", "pgbouncer", "servicePort"], "5432", "6543")
    """

    path: list[str] = field(default_factory=list)
    old_value: Any = None
    new_value: Any = None

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the set-value rule."""
        parent, leaf = _resolve_parent(root, self.path)
        if parent is None or leaf not in parent:
            return []

        current = parent[leaf]
        if current != self.old_value:
            return []

        inline_comment = _shared._extract_inline_comment(parent, leaf)
        parent[leaf] = self.new_value
        if inline_comment:
            _shared._attach_inline_comment(parent, leaf, inline_comment)

        path_str = ".".join(self.path)
        return [
            MigrationChange(
                path_str,
                path_str,
                f"Updated {path_str}: {self.old_value!r} -> {self.new_value!r}",
            )
        ]


@dataclass
class AddKeyIfMissing(MigrationRule):
    """Add a key with a default value only if it does not already exist.

    Example: AddKeyIfMissing(["global", "plane"], {"mode": "unified", "domainPrefix": ""})
    """

    path: list[str] = field(default_factory=list)
    value: Any = None

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the add-key-if-missing rule."""
        if _shared._path_exists(root, self.path):
            return []

        parent_keys = self.path[:-1]
        leaf = self.path[-1]

        parent = _shared._ensure_nested_key(root, parent_keys) if parent_keys else root

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


@dataclass
class HoustonDeploymentBoolToNested(MigrationRule):
    """Migrate a flat boolean under ``astronomer.houston.config.deployments`` to nested ``.enabled``."""

    old_key: str
    new_path: list[str] = field(default_factory=list)
    _inner: _shared.BoolToNested = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_inner",
            _shared.BoolToNested(self.old_key, self.new_path, path_prefix=HOUSTON_DEPLOYMENTS_PREFIX),
        )

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the boolean-to-nested migration on the Houston deployments config section."""
        deployments = _shared._get_nested_mapping(root, ["astronomer", "houston", "config", "deployments"])
        if deployments is None:
            return []
        return self._inner.apply(deployments)


@dataclass
class HoustonDeploymentDeleteKey(MigrationRule):
    """Delete a key from astronomer.houston.config.deployments."""

    key: str

    def apply(self, root: CommentedMap) -> list[MigrationChange]:
        """Apply the delete-key rule on the Houston deployments config section."""
        deployments = _shared._get_nested_mapping(root, ["astronomer", "houston", "config", "deployments"])
        if deployments is None or self.key not in deployments:
            return []

        _shared._delete_key(deployments, self.key)
        path_str = f"{HOUSTON_DEPLOYMENTS_PREFIX}.{self.key}"
        return [MigrationChange(path_str, "(deleted)", f"Deleted obsolete key {path_str}")]


# Rules applied after shared global feature-flag restructuring, before Houston (shared) migrations.
MIGRATIONS: list[MigrationRule] = [
    DeleteKey(["global", "singleNamespace"]),
    DeleteKey(["global", "veleroEnabled"]),
    DeleteKey(["global", "enableHoustonInternalAuthorization"]),
    DeleteKey(["global", "nodeExporterSccEnabled"]),
    DeleteKey(["global", "stan"]),
    DeleteKey(["tags", "stan"]),
    DeleteKey(["stan"]),
    DeleteKey(["kibana"]),
    DeleteKey(["prometheus-blackbox-exporter"]),
    RenameKey(["fluentd"], "vector"),
    RenameKey(["global", "pgbouncer", "krb5ConfSecretName"], "secretName"),
    SetValue(["global", "pgbouncer", "servicePort"], old_value="5432", new_value="6543"),
    SetValue(["global", "nats", "jetStream", "enabled"], old_value=False, new_value=True),
    AddKeyIfMissing(["global", "authHeaderSecretName"], value=None),
    AddKeyIfMissing(["global", "plane"], value={"mode": "unified", "domainPrefix": ""}),
    AddKeyIfMissing(["global", "podLabels"], value={}),
    AddKeyIfMissing(
        ["nats", "init"],
        value={
            "resources": {
                "requests": {"cpu": "75m", "memory": "30Mi"},
                "limits": {"cpu": "250m", "memory": "100Mi"},
            },
        },
    ),
]


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

    global_section = data.get("global")
    global_cm = global_section if isinstance(global_section, CommentedMap) else None
    all_changes.extend(apply_global_feature_flag_rules(global_cm))

    for rule in MIGRATIONS:
        all_changes.extend(rule.apply(data))

    all_changes.extend(apply_houston_config_flag_migrations(data))
    all_changes.extend(apply_houston_deployment_migrations(data))
    all_changes.extend(apply_nginx_csp_policy_migrations(data))

    return all_changes


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
