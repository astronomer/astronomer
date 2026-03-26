#!/usr/bin/env python3

"""Migrate Astronomer Helm chart values.yaml from 1.x to 2.x schema.

Transforms customer override values files from the old scattered feature flag
schema to the new unified domain-grouped schema introduced in chart version 2.0.

Old keys like global.rbacEnabled are moved to global.rbac.enabled, subtrees like
global.dagOnlyDeployment are moved under global.deployMechanisms.dagOnlyDeployment,
and so on. Comments and formatting are preserved via ruamel.yaml round-trip mode.

Usage:
    ./bin/migrate-helm-chart-values-1x-to-2x.py my-values.yaml
    ./bin/migrate-helm-chart-values-1x-to-2x.py --dry-run my-values.yaml
    ./bin/migrate-helm-chart-values-1x-to-2x.py --in-place --backup my-values.yaml
    ./bin/migrate-helm-chart-values-1x-to-2x.py my-values.yaml migrated-values.yaml
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


@dataclass
class MigrationChange:
    """Record of a single migration transformation applied."""

    old_path: str
    new_path: str
    description: str


class MigrationRule(ABC):
    """Base class for a values.yaml migration rule."""

    @abstractmethod
    def apply(self, global_mapping: CommentedMap) -> list[MigrationChange]:
        """Apply this migration rule to the global mapping.

        Parameters:
            global_mapping: The 'global' section of the values.yaml as a CommentedMap.

        Returns:
            A list of MigrationChange records describing what was changed.
        """


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


@dataclass
class BoolToNested(MigrationRule):
    """Migrate a flat boolean key to a nested .enabled structure.

    Example: global.rbacEnabled: true -> global.rbac.enabled: true
    """

    old_key: str
    new_path: list[str] = field(default_factory=list)

    def apply(self, global_mapping: CommentedMap) -> list[MigrationChange]:
        """Apply the boolean-to-nested migration rule.

        If the destination path already exists the new-schema value is preserved
        and the stale old key is removed without overwriting.

        Parameters:
            global_mapping: The 'global' section of the values.yaml.

        Returns:
            A list of changes made; empty if the old key was not present or already migrated.
        """
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


@dataclass
class SubtreeMove(MigrationRule):
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


MIGRATIONS: list[MigrationRule] = [
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

    global_section = data.get("global")
    if global_section is None or not isinstance(global_section, CommentedMap):
        return []

    all_changes: list[MigrationChange] = []
    for rule in MIGRATIONS:
        changes = rule.apply(global_section)
        all_changes.extend(changes)

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


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        The configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Migrate Astronomer Helm chart values.yaml from 1.x to 2.x schema.",
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
                print(f"  {change.old_path} -> {change.new_path}", file=sys.stderr)
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
