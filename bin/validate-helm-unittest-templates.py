#!/usr/bin/env python3
"""Validate that all referenced templates in helm unittest files exist."""

from pathlib import Path, PosixPath
import yaml
import sys


this_script = Path(__file__)
git_root = this_script.resolve().parent.parent


def validate_test_file(file: PosixPath) -> None:
    """Validate that each template file referenced in the given helm unittest
    file exists on disk."""
    with open(file) as f:
        try:
            for test_suite in yaml.safe_load_all(f):
                validate_test_suite(test_suite, file)
        except yaml.scanner.ScannerError as err:
            sys.stderr.write(f"ERROR: {file} could not be parsed\n{err}\n")
        except KeyboardInterrupt:
            sys.exit(1)


def validate_test_suite(test_suite: dict, file: PosixPath) -> None:
    """Validate all templates within a given test suite."""

    for template_file in test_suite["templates"]:
        validate_template_file(Path(file.parent.parent) / "templates" / template_file)

    for test in test_suite["tests"]:
        if "template" in test:
            validate_template_file(
                Path(file.parent.parent) / "templates" / test["template"]
            )


def validate_template_file(file: PosixPath) -> None:
    """Validate that the template file exists."""
    if not file.exists():
        print(f"Missing: {file}")


def validate_all_unittest_files() -> None:
    """Find all helm unittest files in the repo and validate all template files
    found within them."""
    for test_file in git_root.glob("charts/*/tests/*_test.yaml"):
        validate_test_file(test_file)


if __name__ == "__main__":
    validate_all_unittest_files()
