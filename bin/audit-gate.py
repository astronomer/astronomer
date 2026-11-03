#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#     "requests>=2.34",
# ]
# ///
"""Parse `uv audit --output-format json` output and gate on fixable HIGH/CRITICAL CVEs.

Exit 1 if any HIGH/CRITICAL advisory has a fixed version and isn't in bin/audit-allowlist.json.
Exit 0 otherwise, printing every other advisory under its own (non-blocking) banner.

uv audit reports no severity, so it comes from the advisory's GitHub (GHSA) record on OSV, the
rating Dependabot uses. uv lists an advisory's PYSEC and GHSA ids as separate entries; they are
merged under the GHSA id. Allowlist entries look like {"GHSA-...": {"reason": "...", "ticket": "..."}}.
"""

import json
import sys
from functools import cache
from pathlib import Path

import requests

HIGH_CRITICAL = {"HIGH", "CRITICAL"}
SEP = "=" * 64
ALLOWLIST_PATH = Path(__file__).resolve().parent / "audit-allowlist.json"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{}"


def load_allowlist():
    if not ALLOWLIST_PATH.exists():
        return {}
    return json.loads(ALLOWLIST_PATH.read_text())


@cache
def ghsa_severity(advisory_id):
    """Return GitHub's severity rating for a GHSA advisory, or UNKNOWN."""
    if not advisory_id.startswith("GHSA-"):
        return "UNKNOWN"
    try:
        response = requests.get(OSV_VULN_URL.format(advisory_id), timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemExit(f"ERROR: could not fetch the severity of {advisory_id} from OSV: {e}") from e
    return (response.json().get("database_specific") or {}).get("severity", "UNKNOWN").upper()


def parse_advisories(audit_file):
    try:
        report = json.loads(audit_file.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"ERROR: {audit_file} is not uv audit JSON ({e}). See the uv audit output above.") from e

    advisories = {}
    for vuln in report["vulnerabilities"]:
        ids = [vuln["id"], *vuln["aliases"]]
        advisory_id = next((i for i in ids if i.startswith("GHSA-")), vuln["id"])
        package, version = vuln["dependency"]["name"], vuln["dependency"]["version"]
        advisory = advisories.setdefault(
            (package, version, advisory_id),
            {
                "id": advisory_id,
                "package": package,
                "version": version,
                "ids": set(),
                "summary": vuln["summary"],
                "link": vuln["link"],
                "fix_versions": vuln["fix_versions"],
                "severity": ghsa_severity(advisory_id),
            },
        )
        advisory["ids"].update(ids)
    return sorted(advisories.values(), key=lambda a: (a["package"], a["id"]))


def allowlist_entry(advisory, allowlist):
    return next((allowlist[i] for i in sorted(advisory["ids"]) if i in allowlist), None)


def format_advisory(advisory, allowlist):
    entry = allowlist_entry(advisory, allowlist)
    lines = [
        f"  Package:    {advisory['package']} {advisory['version']}",
        f"  Severity:   {advisory['severity']}",
        f"  IDs:        {', '.join(sorted(advisory['ids']))}",
        f"  Summary:    {advisory['summary']}",
        f"  Advisory:   {advisory['link']}",
        f"  Fixed in:   {', '.join(advisory['fix_versions']) or 'no upstream fix available'}",
    ]
    if entry:
        lines.append(f"  Accepted:   {entry['reason']}")
        if entry.get("ticket"):
            lines.append(f"  Ticket:     {entry['ticket']}")
    return "\n".join(lines)


def print_section(title, advisories, allowlist):
    print(f"\n{SEP}\n{title}\n{SEP}\n")
    for advisory in advisories:
        print(format_advisory(advisory, allowlist))
        print()


def report_and_gate(advisories, allowlist):
    if not advisories:
        print("No advisories found.")
        return 0

    high_critical = [a for a in advisories if a["severity"] in HIGH_CRITICAL]
    lower = [a for a in advisories if a["severity"] not in HIGH_CRITICAL]

    if lower:
        print_section("MODERATE/LOW/UNKNOWN advisories (informational, not blocking):", lower, allowlist)

    if not high_critical:
        print("No HIGH or CRITICAL advisories found.")
        return 0

    accepted = [a for a in high_critical if allowlist_entry(a, allowlist)]
    remaining = [a for a in high_critical if not allowlist_entry(a, allowlist)]

    if accepted:
        print_section("ACCEPTED RISK (allowlisted in bin/audit-allowlist.json, not blocking):", accepted, allowlist)

    fixable = [a for a in remaining if a["fix_versions"]]
    unfixable = [a for a in remaining if not a["fix_versions"]]

    if unfixable:
        print_section("Known HIGH/CRITICAL CVEs with no upstream fix yet (not blocking):", unfixable, allowlist)

    if fixable:
        print_section("BLOCKING: HIGH/CRITICAL CVEs with an available fix:", fixable, allowlist)
        print(
            f"{len(fixable)} HIGH/CRITICAL advisory(ies) have upstream fixes. Run 'uv lock --upgrade-package <package>' "
            "to resolve; 'uv tree --invert --package <package>' shows what pulls a package in."
        )
        return 1

    print("\nAll HIGH/CRITICAL advisories are either allowlisted or lack upstream fixes. Pipeline continues.")
    return 0


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: bin/audit-gate.py <uv-audit.json>")
    audit_file = Path(sys.argv[1])
    if not audit_file.exists():
        raise SystemExit(f"ERROR: file not found: {audit_file}")
    return report_and_gate(parse_advisories(audit_file), load_allowlist())


if __name__ == "__main__":
    sys.exit(main())
