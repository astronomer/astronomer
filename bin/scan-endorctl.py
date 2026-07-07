#!/usr/bin/env python3
"""Scan Docker images with endorctl and filter findings.

For each image, runs `endorctl container scan` and post-processes the JSON
output. A finding fails the build when ALL of these are true:
  - severity is at or above --severity (default: high)
  - its CVE ID is not in the optional endorignore file
  - a fix version is available for the finding

Findings at or above the severity threshold are always printed, even when no
fix version is available — those are reported as informational and do not fail
the build.

Devs triage findings by adding the CVE ID to the endorignore file after
reviewing it in the Endor UI.

If --ignorefile is provided and points to a file, each non-blank, non-comment
line is treated as a CVE ID to ignore.

Images are scanned concurrently (--jobs, default 2x CPU count) since each scan
is network-bound. Per-image logs are captured and printed contiguously. The
build fails if any image has actionable findings; every image is scanned before
exiting so the full report is visible.

Images can be passed with repeated --image flags, or piped/generated from
`bin/show-docker-images.py` and passed via --images-from-stdin. Use --skip to
exclude images whose ref contains a given substring (repeatable).

If --csv is provided, every finding at or above the severity threshold (across
all images) is written to that path so CI can store it as a downloadable
artifact. Columns: Image URI, Tag, CVE, Severity, CVSS, Dependency Name,
Dependency Version, Fix Version, Fixable.

Usage:
    uv run bin/scan-endorctl.py --image <name:tag> [--image <name:tag> ...] \
        [--ignorefile .circleci/endorignore] [--csv findings.csv] \
        [--severity {critical,high,medium,low}]

    bin/show-docker-images.py --with-houston | uv run bin/scan-endorctl.py \
        --images-from-stdin [--ignorefile .circleci/endorignore] [--csv findings.csv]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tabulate import tabulate

_GIT_HASH_RE = re.compile(r"[0-9a-f]{40}")


def _is_git_hash(value: str) -> bool:
    return bool(_GIT_HASH_RE.fullmatch(value))


def _extract_web_url(stderr: str) -> str | None:
    for line in stderr.splitlines():
        match = re.search(r"(https://app\.endorlabs\.com/\S+)", line)
        if match:
            return match.group(1)
    return None


def run_endorctl(image: str) -> tuple[dict, str | None]:
    """Run endorctl container scan and return parsed JSON + web URL."""
    cmd = ["endorctl", "container", "scan", "--image", image, "-o", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"Error: endorctl timed out after 300 seconds scanning {image}", file=sys.stderr)
        sys.exit(2)
    for line in result.stderr.splitlines():
        if "WARNING vulnerability-error: Unable to map severity" in line:
            continue
        print(line, file=sys.stderr)
    stdout = result.stdout
    if not stdout.strip():
        # endorctl uploads container-scan results to the backend and only emits
        # JSON on stdout when there are findings to format. A clean scan (zero
        # findings) exits 0 with empty stdout — that is a pass, not an error.
        if result.returncode == 0:
            print("endorctl produced no JSON output (clean scan, results uploaded to Endor API).")
            return {"all_findings": []}, _extract_web_url(result.stderr)
        print(f"Error: endorctl exited {result.returncode} with no JSON output.", file=sys.stderr)
        sys.exit(2)
    web_url = _extract_web_url(result.stderr)
    try:
        return json.loads(stdout), web_url
    except json.JSONDecodeError as e:
        print(f"Error: endorctl produced invalid JSON: {e}", file=sys.stderr)
        print(f"First 500 chars of stdout: {stdout[:500]}", file=sys.stderr)
        sys.exit(2)


def load_ignored_cves(path: Path | None) -> set[str]:
    if path is None:
        return set()
    try:
        text = path.read_text()
    except FileNotFoundError:
        return set()
    cves: set[str] = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            cves.add(line)
    return cves


def get_vuln_id(finding: dict) -> str:
    return finding.get("spec", {}).get("extra_key", "") or finding.get("meta", {}).get("name", "unknown")


def get_severity(finding: dict) -> str:
    level = finding.get("spec", {}).get("level", "")
    return level.removeprefix("FINDING_LEVEL_").capitalize()


def get_package_info(finding: dict) -> tuple[str, str, str]:
    spec = finding.get("spec", {})
    pkg_name = spec.get("target_dependency_name", "?")
    current_ver = spec.get("target_dependency_version", "?")
    proposed = spec.get("proposed_version", "?")
    if _is_git_hash(proposed):
        fix_ver = proposed[:12] + " (commit)"
    else:
        fix_ver = proposed
    return pkg_name, current_ver, fix_ver


def has_fix_version(finding: dict) -> bool:
    proposed = finding.get("spec", {}).get("proposed_version", "")
    return bool(proposed) and proposed != "?"


def get_description(finding: dict) -> str:
    return finding.get("meta", {}).get("description", "")


def get_cvss(finding: dict) -> str:
    """Return the CVSS score as a string, or "" if not present.

    The exact key emitted by `endorctl container scan -o json` is not documented,
    so this tries the REST-API-style nested path and a few flat variants and
    falls back to empty. Wire the confirmed path here once a real scan sample is
    available.
    """
    spec = finding.get("spec", {})
    cvss = spec.get("finding_metadata", {}).get("vulnerability", {}).get("spec", {}).get("cvss_v3_severity", {}).get("score")
    if cvss is None:
        for key in ("cvss_score", "cvss_v3_score", "cvss"):
            if spec.get(key) is not None:
                cvss = spec[key]
                break
    return "" if cvss is None else str(cvss)


def split_image(image: str) -> tuple[str, str]:
    """Split an image reference into (uri, tag). Tag is "" if none is present.

    Splits on the last ":" only when it belongs to the tag (not a registry
    port), i.e. the part after it contains no "/".
    """
    uri, sep, tag = image.rpartition(":")
    if sep and "/" not in tag:
        return uri, tag
    return image, ""


_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
_SEVERITY_CHOICES = ["critical", "high", "medium", "low"]


def severity_at_or_above(finding: dict, threshold: str) -> bool:
    """True iff finding's severity is at or above the threshold."""
    finding_sev = get_severity(finding)
    finding_rank = _SEVERITY_ORDER.get(finding_sev)
    if finding_rank is None:
        return False
    threshold_rank = _SEVERITY_ORDER[threshold.capitalize()]
    return finding_rank <= threshold_rank


def print_table(findings: list[dict], title: str) -> None:
    if not findings:
        return
    rows = []
    for f in findings:
        severity = get_severity(f)
        pkg, current, fix = get_package_info(f)
        desc = get_description(f)
        if len(desc) > 80:
            desc = desc[:77] + "..."
        rows.append((_SEVERITY_ORDER.get(severity, 99), get_vuln_id(f), severity, pkg, current, fix, desc))
    rows.sort()
    headers = ["CVE ID", "Severity", "Package", "Version", "Fix Version", "Description"]
    print(f"\n{title} ({len(findings)} findings)")
    print(tabulate([r[1:] for r in rows], headers=headers, tablefmt="simple"))
    print()


def scan_image(image: str, ignored_cves: set[str], severity: str) -> dict[str, list[dict]]:
    """Scan a single image.

    Return the findings at or above the severity threshold, categorized into
    "action_required", "no_fix", and "ignored" buckets.
    """
    print(f"\n{'=' * 100}")
    print(f"Scanning image: {image}")
    print(f"Scan yourself with: endorctl container scan --image={image}")
    data, web_url = run_endorctl(image)

    if web_url:
        print(f"Full results: {web_url}")

    findings = data.get("all_findings", [])
    at_severity = [f for f in findings if severity_at_or_above(f, severity)]

    actionable: list[dict] = []
    ignored: list[dict] = []
    no_fix: list[dict] = []
    for f in at_severity:
        if get_vuln_id(f) in ignored_cves:
            ignored.append(f)
        elif not has_fix_version(f):
            no_fix.append(f)
        else:
            actionable.append(f)

    print(f"\nGate: fail on severity >= {severity} when a fix version is available")
    if actionable:
        print_table(actionable, "Vulnerabilities (action required)")
    if no_fix:
        print_table(no_fix, "Vulnerabilities without a fix version (informational, does not fail build)")
    if ignored:
        print_table(ignored, "Ignored vulnerabilities (in endorignore)")
    if not actionable:
        print(f"No actionable vulnerabilities at or above {severity}.")

    return {"action_required": actionable, "no_fix": no_fix, "ignored": ignored}


def _default_jobs() -> int:
    """Default concurrency: 2x CPU count (scans are network-bound), min 2."""
    return max(2, (os.cpu_count() or 1) * 2)


def scan_image_captured(image: str, ignored_cves: set[str], severity: str) -> tuple[str, dict[str, list[dict]] | None, str]:
    """Run scan_image with stdout/stderr captured into one buffer.

    Returns (image, categorized, captured_output). Capturing keeps each image's
    log contiguous when scans run concurrently, instead of interleaving.

    categorized is None if the scan errored (e.g. endorctl called sys.exit or
    raised). The error is captured in the buffer rather than aborting the whole
    run, so other images still get scanned; main() exits non-zero afterwards.
    """
    buf = io.StringIO()
    categorized: dict[str, list[dict]] | None = None
    with redirect_stdout(buf), redirect_stderr(buf):
        try:
            categorized = scan_image(image, ignored_cves, severity)
        except SystemExit as e:
            print(f"Error: scan of {image} exited early ({e.code}); see log above.")
        except Exception as e:  # noqa: BLE001 - surface any scan failure without killing siblings
            print(f"Error: scan of {image} raised {type(e).__name__}: {e}")
    return image, categorized, buf.getvalue()


_CSV_HEADERS = [
    "Image URI",
    "Tag",
    "CVE",
    "Severity",
    "CVSS",
    "Dependency Name",
    "Dependency Version",
    "Fix Version",
    "Fixable",
]


def write_csv(csv_path: Path, rows_by_image: list[tuple[str, dict[str, list[dict]]]]) -> None:
    """Write every at-severity finding across all images to a CSV artifact."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(_CSV_HEADERS)
        rows = []
        for image, categorized in rows_by_image:
            uri, tag = split_image(image)
            for findings in categorized.values():
                for f in findings:
                    severity = get_severity(f)
                    pkg, current, fix = get_package_info(f)
                    fixable = "Yes" if has_fix_version(f) else "No"
                    rows.append(
                        (
                            uri,
                            _SEVERITY_ORDER.get(severity, 99),
                            tag,
                            get_vuln_id(f),
                            severity,
                            get_cvss(f),
                            pkg,
                            current,
                            fix,
                            fixable,
                        )
                    )
        rows.sort(key=lambda r: (r[0], r[1]))
        for r in rows:
            writer.writerow((r[0], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]))
    print(f"\nWrote findings CSV to {csv_path}")


def collect_images(args: argparse.Namespace) -> list[str]:
    """Collect the list of images to scan from --image flags and/or stdin.

    stdin is expected in the `bin/show-docker-images.py` format:
    `https://<image>  <image>:<tag>` — the second whitespace-separated column
    is the pullable image reference.
    """
    images: list[str] = list(args.image or [])
    if args.images_from_stdin:
        for raw in sys.stdin.read().splitlines():
            line = raw.strip()
            if not line:
                continue
            images.append(line.split()[-1])
    images = sorted(set(images))

    skips = args.skip or []
    if skips:
        kept = []
        for image in images:
            matched = next((s for s in skips if s in image), None)
            if matched is not None:
                print(f"Skipping image (matched --skip {matched!r}): {image}")
            else:
                kept.append(image)
        images = kept
    return images


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan Docker images with endorctl and filter findings.")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Image name:tag to scan (repeatable)",
    )
    parser.add_argument(
        "--images-from-stdin",
        action="store_true",
        help="Read images from stdin in `bin/show-docker-images.py` format (last column is the image:tag)",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Substring of an image ref to exclude from scanning (repeatable), e.g. airflow-operator-dev",
    )
    parser.add_argument(
        "--ignorefile",
        type=Path,
        default=None,
        help="File of CVE IDs to ignore (one per line, # comments allowed)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Write all at-severity findings (across all images) to this CSV path for CI to store as an artifact",
    )
    parser.add_argument(
        "--severity",
        choices=_SEVERITY_CHOICES,
        default="high",
        help="Minimum severity that fails the build (default: high)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=_default_jobs(),
        help="Number of images to scan concurrently (default: 2x CPU count, since scans are network-bound)",
    )
    args = parser.parse_args()

    images = collect_images(args)
    if not images:
        parser.error("no images to scan: pass --image and/or --images-from-stdin")

    ignored_cves = load_ignored_cves(args.ignorefile)

    workers = max(1, min(args.jobs, len(images)))
    print(f"Scanning {len(images)} image(s), {workers} at a time:")
    for image in images:
        print(f"  - {image}")

    # Scans run concurrently (network-bound), but each image's log is captured
    # and flushed contiguously, and results are re-sorted to keep output stable.
    results_by_image: dict[str, dict[str, list[dict]] | None] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(scan_image_captured, image, ignored_cves, args.severity) for image in images]
        for future in futures:
            image, categorized, output = future.result()
            results_by_image[image] = categorized
            print(output, end="")

    errored_images = [image for image in images if results_by_image[image] is None]
    results = [(image, results_by_image[image]) for image in images if results_by_image[image] is not None]

    if args.csv is not None:
        write_csv(args.csv, results)

    failed_images = [image for image, categorized in results if categorized["action_required"]]

    print(f"\n{'=' * 100}")
    if errored_images:
        print(f"ERRORED: {len(errored_images)} of {len(images)} image(s) could not be scanned:")
        for image in errored_images:
            print(f"  - {image}")
    if failed_images:
        print(f"FAILED: {len(failed_images)} of {len(images)} image(s) have actionable vulnerabilities:")
        for image in failed_images:
            print(f"  - {image}")
    if errored_images:
        sys.exit(2)
    if failed_images:
        sys.exit(1)
    print(f"PASSED: all {len(images)} image(s) clear of actionable vulnerabilities.")
    sys.exit(0)


if __name__ == "__main__":
    main()
