#!/usr/bin/env python3

import sys

# List of [refused_string, suggested_string] pairs
BLOCKED_PAIRS = [
    ["authsidecar", "auth-sidecar"],
    # Add more pairs as needed
]


def main(filenames):
    for file in filenames:
        for refused, suggested in BLOCKED_PAIRS:
            if refused in file:
                print(
                    f"Error: Filename '{file}' contains the blocked string '{refused}' which should probably be '{suggested}'.",
                    file=sys.stderr,
                )
                sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
