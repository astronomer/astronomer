#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#     "requests>=2.34",
# ]
# ///
"""Parse `uv audit --output-format json` output and gate on fixable HIGH/CRITICAL CVEs.

Exit 1 if any HIGH, CRITICAL or UNKNOWN advisory has a fixed version and isn't accepted in
bin/audit-allowlist.json. Exit 0 otherwise, printing every other advisory under its own
(non-blocking) banner.

uv audit reports no severity, so it comes from the advisory's GitHub (GHSA) record on OSV, the
rating Dependabot uses. An advisory with no GHSA rating is UNKNOWN and blocks like a HIGH one, so a
HIGH can't pass unrated. uv lists an advisory's PYSEC and GHSA ids as separate entries; they are
merged under the GHSA id.

Allowlist entries look like {"GHSA-...": {"reason": "...", "ticket": "...", "expires": "2027-01-31"}}.
An entry stops being accepted after its expiry date.
"""

import argparse
import datetime
import json
import sys
from functools import cache
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry

HIGH_CRITICAL = {"HIGH", "CRITICAL"}
BLOCKING_SEVERITIES = HIGH_CRITICAL | {"UNKNOWN"}
SEP = "=" * 64
ALLOWLIST_PATH = Path(__file__).resolve().parent / "audit-allowlist.json"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{}"


def load_allowlist(path=None):
    """Load the allowlist, failing on any entry without a reason or a valid expiry date."""
    path = path or ALLOWLIST_PATH
    if not path.exists():
        return {}
    allowlist = json.loads(path.read_text())
    for advisory_id, entry in allowlist.items():
        if not entry.get("reason"):
            raise SystemExit(f"ERROR: {path.name}: {advisory_id} needs a reason.")
        try:
            entry["expires"] = datetime.date.fromisoformat(entry["expires"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"ERROR: {path.name}: {advisory_id} needs an expires date like 2027-01-31.") from None
    return allowlist


@cache
def osv_session():
    """Return a session that retries OSV rate limits and server errors with backoff."""
    retry = Retry(total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


@cache
def ghsa_severity(advisory_id):
    """Return GitHub's severity rating for a GHSA advisory, or UNKNOWN."""
    if not advisory_id.startswith("GHSA-"):
        return "UNKNOWN"
    try:
        response = osv_session().get(OSV_VULN_URL.format(advisory_id), timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemExit(f"ERROR: could not fetch the severity of {advisory_id} from OSV: {e}") from e
    return ((response.json().get("database_specific") or {}).get("severity") or "UNKNOWN").upper()


def parse_advisories(audit_file):
    try:
        report = json.loads(audit_file.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"ERROR: {audit_file} is not uv audit JSON ({e}). See the uv audit output above.") from e

    advisories = {}
    for vuln in report.get("vulnerabilities", []):
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
                "summary": None,
                "link": None,
                "fix_versions": vuln["fix_versions"],
                "severity": ghsa_severity(advisory_id),
            },
        )
        advisory["ids"].update(ids)
        # summary and link can be null on one of the entries uv lists for the same advisory.
        advisory["summary"] = advisory["summary"] or vuln.get("summary")
        advisory["link"] = advisory["link"] or vuln.get("link")
    return sorted(advisories.values(), key=lambda a: (a["package"], a["id"]))


def allowlist_entry(advisory, allowlist):
    return next((allowlist[i] for i in sorted(advisory["ids"]) if i in allowlist), None)


def is_accepted(advisory, allowlist, today):
    entry = allowlist_entry(advisory, allowlist)
    return entry is not None and today <= entry["expires"]


def format_advisory(advisory, allowlist, today):
    entry = allowlist_entry(advisory, allowlist)
    lines = [
        f"  Package:    {advisory['package']} {advisory['version']}",
        f"  Severity:   {advisory['severity']}",
        f"  IDs:        {', '.join(sorted(advisory['ids']))}",
        f"  Summary:    {advisory['summary'] or 'no summary'}",
        f"  Advisory:   {advisory['link'] or 'no link'}",
        f"  Fixed in:   {', '.join(advisory['fix_versions']) or 'no upstream fix available'}",
    ]
    if entry:
        lines.append(f"  Accepted:   {entry['reason']}")
        if entry.get("ticket"):
            lines.append(f"  Ticket:     {entry['ticket']}")
        expired = " (EXPIRED, no longer accepted)" if today > entry["expires"] else ""
        lines.append(f"  Expires:    {entry['expires']}{expired}")
    return "\n".join(lines)


def print_section(title, advisories, allowlist, today):
    print(f"\n{SEP}\n{title}\n{SEP}\n")
    for advisory in advisories:
        print(format_advisory(advisory, allowlist, today))
        print()


def report_and_gate(advisories, allowlist, today=None):
    today = today or datetime.datetime.now(datetime.UTC).date()
    if not advisories:
        print("No advisories found.")
        return 0

    blocking_severity = [a for a in advisories if a["severity"] in BLOCKING_SEVERITIES]
    lower = [a for a in advisories if a["severity"] not in BLOCKING_SEVERITIES]

    if lower:
        print_section("MODERATE/LOW advisories (informational, not blocking):", lower, allowlist, today)

    if not blocking_severity:
        print("No HIGH, CRITICAL or UNKNOWN advisories found.")
        return 0

    accepted = [a for a in blocking_severity if is_accepted(a, allowlist, today)]
    remaining = [a for a in blocking_severity if not is_accepted(a, allowlist, today)]

    if accepted:
        print_section("ACCEPTED RISK (allowlisted in bin/audit-allowlist.json, not blocking):", accepted, allowlist, today)

    fixable = [a for a in remaining if a["fix_versions"]]
    unfixable = [a for a in remaining if not a["fix_versions"]]

    if unfixable:
        print_section("Known HIGH/CRITICAL/UNKNOWN CVEs with no upstream fix yet (not blocking):", unfixable, allowlist, today)

    if fixable:
        print_section("BLOCKING: HIGH/CRITICAL/UNKNOWN CVEs with an available fix:", fixable, allowlist, today)
        print(
            f"{len(fixable)} HIGH/CRITICAL/UNKNOWN advisory(ies) have upstream fixes. Run 'uv lock --upgrade-package <package>' "
            "to resolve; 'uv tree --invert --package <package>' shows what pulls a package in."
        )
        return 1

    print("\nAll HIGH/CRITICAL/UNKNOWN advisories are either allowlisted or lack upstream fixes. Pipeline continues.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audit_file", type=Path, help="JSON written by `uv audit --output-format json`")
    parser.add_argument("--uv-exit-code", type=int, help="uv audit's exit code, so that uv failing fails the gate")
    args = parser.parse_args()

    # uv audit exits 1 when it finds vulnerabilities, but also on some resolver errors, and 2 on
    # other errors such as a stale lockfile. Exit 1 only counts as a finding if the report has one.
    if args.uv_exit_code not in (None, 0, 1):
        raise SystemExit(f"ERROR: uv audit failed with exit code {args.uv_exit_code}. See its output above.")
    if not args.audit_file.exists():
        raise SystemExit(f"ERROR: file not found: {args.audit_file}")
    advisories = parse_advisories(args.audit_file)
    if args.uv_exit_code == 1 and not advisories:
        raise SystemExit("ERROR: uv audit exited 1 but reported no vulnerabilities. See its output above.")
    return report_and_gate(advisories, load_allowlist())


if __name__ == "__main__":
    sys.exit(main())
