"""Tests for bin/audit-gate.py."""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
UV_AUDIT_REPORT = Path(__file__).resolve().parent / "test_data" / "uv-audit.json"
_SCRIPT_PATH = REPO_ROOT / "bin" / "audit-gate.py"
_spec = importlib.util.spec_from_file_location("audit_gate", _SCRIPT_PATH)
audit_gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = audit_gate
_spec.loader.exec_module(audit_gate)

TODAY = datetime.date(2026, 11, 5)


class FakeOSV:
    """Stands in for the OSV session: returns `payload` or raises `error`, and records each URL."""

    def __init__(self):
        self.payload = {}
        self.error = None
        self.requested = []

    def get(self, url, timeout):
        self.requested.append(url)
        if self.error:
            raise self.error
        return self

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


@pytest.fixture
def osv(monkeypatch):
    fake = FakeOSV()
    monkeypatch.setattr(audit_gate, "osv_session", lambda: fake)
    audit_gate.ghsa_severity.cache_clear()
    yield fake
    audit_gate.ghsa_severity.cache_clear()


@pytest.fixture
def severities(monkeypatch):
    """Severity per advisory id, returned by a stubbed ghsa_severity so nothing calls OSV."""
    table = {}
    monkeypatch.setattr(audit_gate, "ghsa_severity", lambda advisory_id: table.get(advisory_id, "UNKNOWN"))
    return table


def _write_report(tmp_path, report):
    path = tmp_path / "uv-audit.json"
    path.write_text(json.dumps(report))
    return path


def _advisory(severity, fix_versions=("1.0.1",), ids=("GHSA-aaaa-bbbb-cccc", "PYSEC-2026-1")):
    """An advisory as parse_advisories returns it."""
    return {
        "id": ids[0],
        "package": "examplepkg",
        "version": "1.0.0",
        "ids": set(ids),
        "summary": "examplepkg request smuggling",
        "link": None,
        "fix_versions": list(fix_versions),
        "severity": severity,
    }


def _allowlist(tmp_path, entries):
    path = tmp_path / "audit-allowlist.json"
    path.write_text(json.dumps(entries))
    return audit_gate.load_allowlist(path)


# ---- parse_advisories ----------------------------------------------------


def test_parse_merges_pysec_and_ghsa_entries_under_the_ghsa_id(severities):
    severities["GHSA-aaaa-bbbb-cccc"] = "HIGH"
    advisories = {a["id"]: a for a in audit_gate.parse_advisories(UV_AUDIT_REPORT)}

    assert sorted(advisories) == ["GHSA-aaaa-bbbb-cccc", "PYSEC-2026-2"]
    merged = advisories["GHSA-aaaa-bbbb-cccc"]
    assert merged["ids"] == {"GHSA-aaaa-bbbb-cccc", "PYSEC-2026-1", "CVE-2026-0001"}
    assert merged["severity"] == "HIGH"
    # The PYSEC entry comes first with a null summary and link; the GHSA entry fills them in.
    assert merged["summary"] == "examplepkg request smuggling"
    assert merged["link"] == "https://github.com/advisories/GHSA-aaaa-bbbb-cccc"


def test_parse_keeps_an_advisory_without_a_ghsa_alias_under_its_own_id(severities):
    advisories = {a["id"]: a for a in audit_gate.parse_advisories(UV_AUDIT_REPORT)}

    assert advisories["PYSEC-2026-2"]["ids"] == {"PYSEC-2026-2", "CVE-2026-0002"}
    assert advisories["PYSEC-2026-2"]["fix_versions"] == []


def test_parse_report_without_vulnerabilities_key(tmp_path, severities):
    report = _write_report(tmp_path, {"schema": {"version": "preview"}, "adverse_statuses": []})
    assert audit_gate.parse_advisories(report) == []


def test_parse_rejects_output_that_is_not_json(tmp_path):
    report = tmp_path / "uv-audit.json"
    report.write_text("error: Failed to fetch https://api.osv.dev\n")
    with pytest.raises(SystemExit, match="is not uv audit JSON"):
        audit_gate.parse_advisories(report)


def test_format_advisory_without_summary_or_link():
    text = audit_gate.format_advisory(_advisory("HIGH") | {"summary": None}, {}, TODAY)
    assert "Summary:    no summary" in text
    assert "Advisory:   no link" in text


# ---- ghsa_severity ---------------------------------------------------------


def test_ghsa_severity_is_unknown_without_a_ghsa_id(osv):
    assert audit_gate.ghsa_severity("PYSEC-2026-2") == "UNKNOWN"
    assert osv.requested == []


def test_ghsa_severity_reads_githubs_rating(osv):
    osv.payload = {"database_specific": {"severity": "high"}}
    assert audit_gate.ghsa_severity("GHSA-aaaa-bbbb-cccc") == "HIGH"
    assert osv.requested == ["https://api.osv.dev/v1/vulns/GHSA-aaaa-bbbb-cccc"]


@pytest.mark.parametrize("payload", [{}, {"database_specific": None}, {"database_specific": {"severity": None}}])
def test_ghsa_severity_is_unknown_when_github_has_no_rating(osv, payload):
    osv.payload = payload
    assert audit_gate.ghsa_severity("GHSA-aaaa-bbbb-cccc") == "UNKNOWN"


def test_ghsa_severity_fails_when_osv_stays_unreachable(osv):
    osv.error = requests.ConnectionError("connection refused")
    with pytest.raises(SystemExit, match="could not fetch the severity of GHSA-aaaa-bbbb-cccc"):
        audit_gate.ghsa_severity("GHSA-aaaa-bbbb-cccc")


def test_osv_session_retries_rate_limits_and_server_errors():
    retry = audit_gate.osv_session().get_adapter(audit_gate.OSV_VULN_URL).max_retries
    assert {429, 500, 502, 503, 504} <= set(retry.status_forcelist)
    assert retry.total >= 3
    assert retry.backoff_factor > 0


# ---- report_and_gate ---------------------------------------------------------


@pytest.mark.parametrize(
    ("severity", "fix_versions", "exit_code"),
    [
        ("CRITICAL", ["1.0.1"], 1),
        ("HIGH", ["1.0.1"], 1),
        ("UNKNOWN", ["1.0.1"], 1),
        ("MODERATE", ["1.0.1"], 0),
        ("LOW", ["1.0.1"], 0),
        ("CRITICAL", [], 0),
        ("HIGH", [], 0),
        ("UNKNOWN", [], 0),
    ],
)
def test_gate_blocks_only_fixable_high_critical_or_unknown(severity, fix_versions, exit_code):
    assert audit_gate.report_and_gate([_advisory(severity, fix_versions)], {}, TODAY) == exit_code


def test_gate_passes_with_no_advisories(capsys):
    assert audit_gate.report_and_gate([], {}, TODAY) == 0
    assert "No advisories found." in capsys.readouterr().out


# ---- allowlist -------------------------------------------------------------


def test_allowlist_entry_matches_any_of_the_advisorys_ids(tmp_path, capsys):
    allowlist = _allowlist(tmp_path, {"PYSEC-2026-1": {"reason": "Not reachable from our code", "expires": "2026-12-31"}})

    assert audit_gate.report_and_gate([_advisory("HIGH")], allowlist, TODAY) == 0
    assert "ACCEPTED RISK" in capsys.readouterr().out


def test_allowlist_entry_is_accepted_on_its_expiry_date(tmp_path):
    allowlist = _allowlist(tmp_path, {"GHSA-aaaa-bbbb-cccc": {"reason": "Not reachable", "expires": TODAY.isoformat()}})
    assert audit_gate.report_and_gate([_advisory("HIGH")], allowlist, TODAY) == 0


def test_expired_allowlist_entry_blocks_again(tmp_path, capsys):
    allowlist = _allowlist(tmp_path, {"GHSA-aaaa-bbbb-cccc": {"reason": "Not reachable", "expires": "2026-11-04"}})

    assert audit_gate.report_and_gate([_advisory("HIGH")], allowlist, TODAY) == 1
    out = capsys.readouterr().out
    assert "BLOCKING" in out
    assert "EXPIRED" in out


def test_load_allowlist_without_a_file(tmp_path):
    assert audit_gate.load_allowlist(tmp_path / "missing.json") == {}


@pytest.mark.parametrize(
    ("entry", "error"),
    [
        ({"expires": "2026-12-31"}, "needs a reason"),
        ({"reason": "Not reachable"}, "needs an expires date"),
        ({"reason": "Not reachable", "expires": "next year"}, "needs an expires date"),
        ({"reason": "Not reachable", "expires": None}, "needs an expires date"),
    ],
)
def test_load_allowlist_rejects_incomplete_entries(tmp_path, entry, error):
    with pytest.raises(SystemExit, match=error):
        _allowlist(tmp_path, {"GHSA-aaaa-bbbb-cccc": entry})


def test_shipped_allowlist_is_valid():
    audit_gate.load_allowlist()


# ---- main: uv audit's exit code ----------------------------------------------


def _main(monkeypatch, report, uv_exit_code):
    monkeypatch.setattr(sys, "argv", ["audit-gate.py", "--uv-exit-code", str(uv_exit_code), str(report)])
    return audit_gate.main()


def test_main_fails_when_uv_audit_errors(monkeypatch, tmp_path):
    # A stale lockfile under --locked exits 2 and writes no report.
    report = tmp_path / "uv-audit.json"
    report.write_text("")
    with pytest.raises(SystemExit, match="uv audit failed with exit code 2"):
        _main(monkeypatch, report, 2)


def test_main_fails_when_uv_audit_exits_1_without_findings(monkeypatch, tmp_path):
    report = _write_report(tmp_path, {"vulnerabilities": []})
    with pytest.raises(SystemExit, match="reported no vulnerabilities"):
        _main(monkeypatch, report, 1)


def test_main_gates_the_findings_when_uv_audit_exits_1(monkeypatch, tmp_path, severities):
    severities["GHSA-aaaa-bbbb-cccc"] = "HIGH"
    monkeypatch.setattr(audit_gate, "ALLOWLIST_PATH", tmp_path / "missing.json")
    assert _main(monkeypatch, UV_AUDIT_REPORT, 1) == 1


def test_main_passes_a_clean_report(monkeypatch, tmp_path):
    report = _write_report(tmp_path, {"vulnerabilities": []})
    monkeypatch.setattr(audit_gate, "ALLOWLIST_PATH", tmp_path / "missing.json")
    assert _main(monkeypatch, report, 0) == 0
