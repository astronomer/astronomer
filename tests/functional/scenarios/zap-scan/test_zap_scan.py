"""PLA-614: on-demand ZAP DAST scan of a running APC install.

See tests/functional/scenarios/zap-scan/test_profile.yaml and tests/utils/zap.py for
why this scenario is manual-only and how the scan itself works. Scans houston-api's
GraphQL API (schema-aware, via introspection) and astro-ui (spider + ajaxSpider),
authenticated as a freshly created admin user, with ZAP's active scanner enabled.
"""

import json
import shutil
from pathlib import Path

import pytest
import testinfra

from tests.utils.houston_graphql import create_user
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector
from tests.utils.zap import (
    ASTRO_UI_LOCAL_PORT,
    ASTRO_UI_REMOTE_PORT,
    ASTRO_UI_SERVICE,
    HOUSTON_LOCAL_PORT,
    HOUSTON_REMOTE_PORT,
    HOUSTON_SERVICE,
    port_forward,
    run_zap_scan,
)

NAMESPACE = "astronomer"
ADMIN_EMAIL = "admin@astronomer.io"
ADMIN_PASSWORD = "Zap-Scan-Password1!"  # throwaway -- this scenario's cluster is disposable; must satisfy houston-api's password policy (upper/lower/digit/special)


@pytest.fixture(scope="module")
def _houston_api_module():
    """Module-scoped counterpart to conftest.py's function-scoped houston_api fixture,
    for the same reason deployment-lifecycle/auth-sidecar need one: minting the token
    once for the whole module, not once per test."""
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


# Fixed, not a self-cleaning tempfile.TemporaryDirectory: CircleCI's store_artifacts
# step (.circleci/config.yml.j2's zap-scan job) runs *after* this whole pytest process
# exits, so the report has to still be on disk at that point, not deleted the moment
# this fixture's generator resumes.
REPORT_DIR = Path("/tmp/zap-scan-report")  # noqa: S108


@pytest.fixture(scope="module")
def zap_scan_result(_houston_api_module):
    """Run the actual scan once per module: mint an admin token, port-forward
    houston-api + astro-ui so ZAP (a sibling Docker container, not a pod in this
    cluster) can reach them, then run ZAP's Automation Framework against both."""
    token = create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)

    shutil.rmtree(REPORT_DIR, ignore_errors=True)
    REPORT_DIR.mkdir(parents=True)
    with (
        port_forward(KUBECONFIG_UNIFIED, HOUSTON_SERVICE, HOUSTON_LOCAL_PORT, HOUSTON_REMOTE_PORT),
        port_forward(KUBECONFIG_UNIFIED, ASTRO_UI_SERVICE, ASTRO_UI_LOCAL_PORT, ASTRO_UI_REMOTE_PORT),
    ):
        result = run_zap_scan(token, REPORT_DIR)
    print("--- ZAP stdout ---")
    print(result.stdout)
    print("--- ZAP stderr ---")
    print(result.stderr)
    yield result, REPORT_DIR


def test_zap_scan_produced_a_report(zap_scan_result):
    """This test intentionally does not assert on ZAP's own exit code or on alert risk
    levels: those encode "did the scan find High-risk issues", which is the whole
    point of running it, not "did the test suite pass". There is no automated trigger
    for this scenario at all (manual-only, see test_profile.yaml) -- a human reads the
    report regardless of whether this test is green. The useful thing to assert is
    that the tool actually ran and produced output, since the automation.yaml plan's
    `exitStatus` job (tests/utils/zap.py::build_automation_plan) means a non-zero
    return code is ambiguous between "High alert found" and "a job in the plan
    errored" -- distinguishing those is only possible by reading the report/summary,
    not the return code alone.
    """
    result, work_dir = zap_scan_result
    assert result.returncode in (0, 1, 2), (
        f"ZAP exited {result.returncode}, outside its documented range (0=ok, 1=errorLevel "
        f"alerts/job error, 2=warnLevel alerts) -- treat as a real crash, not scan findings"
    )
    report_path = work_dir / "zap-report.html"
    assert report_path.exists(), f"Expected ZAP's report job to write {report_path}"

    summary_path = work_dir / "zap-summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        print(f"--- ZAP summary ---\n{json.dumps(summary, indent=2)}")
