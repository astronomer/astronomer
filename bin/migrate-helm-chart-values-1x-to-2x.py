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
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

_BIN = Path(__file__).resolve().parent
if str(_BIN) not in sys.path:
    sys.path.insert(0, str(_BIN))

from helm_chart_values_migration_shared import (  # noqa: E402
    GLOBAL_FEATURE_FLAG_RULES,
    HOUSTON_DEPLOYMENT_BOOL_RULES,
    BoolToNested,  # noqa: F401
    InvertedBoolToNested,  # noqa: F401
    MigrationChange,
    SubtreeMove,  # noqa: F401
    apply_global_feature_flag_rules,
    apply_houston_config_flag_migrations,
    apply_houston_deployment_migrations,
    apply_nginx_csp_policy_migrations,
    dump_yaml,
    load_yaml,
)

MIGRATIONS = GLOBAL_FEATURE_FLAG_RULES
HOUSTON_DEPLOYMENT_MIGRATIONS = HOUSTON_DEPLOYMENT_BOOL_RULES


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
