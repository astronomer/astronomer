"""Drive an OWASP ZAP (https://www.zaproxy.org/) Automation Framework scan against a
running APC install.

Used by tests/functional/scenarios/zap-scan. ZAP itself runs as a sibling Docker
container (not inside the kind cluster), so it reaches houston-api/astro-ui the same
way a real external client would: over the network, not via `kubectl exec` like every
other fixture in tests/functional/conftest.py. That means it needs an actual route into
the cluster's pod network, which `kubectl port-forward` provides -- see port_forward()
below.
"""

import contextlib
import os
import shlex
import socket
import subprocess
import time
from pathlib import Path

import yaml

# https://hub.docker.com/r/zaproxy/zap-stable/tags
ZAP_IMAGE = "zaproxy/zap-stable:2.16.1"

HOUSTON_SERVICE = "astronomer-houston"
HOUSTON_REMOTE_PORT = 8871
HOUSTON_LOCAL_PORT = 18871
ASTRO_UI_SERVICE = "astronomer-astro-ui"
ASTRO_UI_REMOTE_PORT = 8080
ASTRO_UI_LOCAL_PORT = 18080

KUBECTL_EXE = str(Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "kubectl")
if not Path(KUBECTL_EXE).exists():
    KUBECTL_EXE = "kubectl"  # local run outside reset-local-dev's own PATH export


def _wait_for_port(port: int, timeout: int = 30) -> None:
    """Block until something is accepting TCP connections on localhost:port."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError), socket.create_connection(("localhost", port), timeout=1):
            return
        time.sleep(0.5)
    raise RuntimeError(f"Nothing answered on localhost:{port} within {timeout}s")


@contextlib.contextmanager
def port_forward(kubeconfig_file: str, service: str, local_port: int, remote_port: int, namespace: str = "astronomer"):
    """Run `kubectl port-forward` to a Service for the life of the `with` block.

    This is the only way for a sibling process (ZAP, running as its own Docker
    container, not a pod in this cluster) to reach houston-api/astro-ui at all: the
    kind cluster here has no extraPortMappings (tests/kind/calico-config.yaml) and
    `global.baseDomain`'s `localtest.me` resolves to 127.0.0.1 with nothing listening
    on it, so there is no path in short of this.
    """
    command = [
        KUBECTL_EXE,
        f"--kubeconfig={kubeconfig_file}",
        f"--namespace={namespace}",
        "port-forward",
        f"service/{service}",
        f"{local_port}:{remote_port}",
    ]
    print(f"Starting port-forward: {shlex.join(command)}")
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_for_port(local_port)
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def build_automation_plan(token: str, report_dir: str, error_level: str = "High") -> dict:
    """The ZAP Automation Framework plan (see tests/utils/zap.py module docstring).

    Auth is a `replacer` job injecting a static `Authorization: Bearer <token>` header
    on every request -- not ZAP's `authentication`/`sessionManagement` context
    machinery, which is for driving a real login flow. We already have a valid token
    (minted out-of-band via tests/utils/houston_graphql.create_user, the same
    ADMIN_EMAIL/ADMIN_PASSWORD pattern deployment-lifecycle/auth-sidecar use), so there
    is no login for ZAP to perform. Schema confirmed against this exact pinned image
    version via `zap.sh -cmd -autogenmax` (the `authentication`/`sessionManagement`
    method lists do not include a static-header option; `replacer` does what we need).
    v1 scope per PLA-614: scripting ZAP to drive astro-ui's actual login form is
    explicitly deferred, not done here.
    """
    houston_url = f"http://localhost:{HOUSTON_LOCAL_PORT}"
    astro_ui_url = f"http://localhost:{ASTRO_UI_LOCAL_PORT}"
    return {
        "env": {
            "contexts": [
                {
                    "name": "apc",
                    "urls": [houston_url, astro_ui_url],
                }
            ],
            "parameters": {
                "failOnError": True,
                "progressToStdout": True,
            },
        },
        "jobs": [
            {
                "type": "replacer",
                "rules": [
                    {
                        "description": "inject bearer token minted via houston_graphql.create_user",
                        "matchType": "req_header",
                        "matchString": "Authorization",
                        "replacementString": f"Bearer {token}",
                    }
                ],
            },
            # Schema-aware API scan: imports houston-api's GraphQL schema via
            # introspection, then the activeScan job below attacks every query/mutation
            # it generates from that schema. No `context` param here: confirmed against
            # a real run that ZAP's graphql job doesn't accept one ("Unrecognised
            # parameter for job graphql : context") -- it associates with whatever
            # context already matches the endpoint's URL (we only ever have one).
            {
                "type": "graphql",
                "parameters": {
                    "endpoint": f"{houston_url}/v1",
                },
            },
            {
                "type": "spider",
                "parameters": {"url": astro_ui_url, "context": "apc"},
            },
            {
                "type": "spiderAjax",
                # numberOfBrowsers defaults to the host's core count -- bounded here so a
                # big CI executor doesn't launch a pile of concurrent headless-Firefox
                # instances, each already fighting the same shm pressure (see
                # --shm-size in run_zap_scan() below).
                "parameters": {"url": astro_ui_url, "context": "apc", "numberOfBrowsers": 2},
            },
            {"type": "passiveScan-wait", "parameters": {"maxDuration": 10}},
            {"type": "activeScan", "parameters": {"context": "apc"}},
            {
                "type": "report",
                "parameters": {
                    "template": "risk-confidence-html",
                    "reportDir": report_dir,
                    "reportFile": "zap-report",
                },
                "risks": ["high", "medium", "low", "info"],
            },
            {
                "type": "outputSummary",
                "parameters": {"format": "Long", "summaryFile": f"{report_dir}/zap-summary.json"},
            },
            # Only High-risk alerts fail the job -- PLA-614 left exact thresholds TBD,
            # this is a deliberate starting point so Low/Info noise doesn't hard-fail
            # CI. Medium/Low/Info still show up in the report either way.
            {"type": "exitStatus", "parameters": {"errorLevel": error_level}},
        ],
    }


def run_zap_scan(token: str, work_dir: Path, error_level: str = "High") -> subprocess.CompletedProcess:
    """Write the automation plan into work_dir and run it via the official ZAP Docker image.

    `--network host`: ZAP (in its own container) needs to reach the `kubectl
    port-forward` processes' listening sockets on localhost, which only works if it
    shares the host's network namespace -- CircleCI's machine executor (and a local
    dev workstation running Docker directly) both support this.

    `--shm-size=2g`: spiderAjax drives a real headless Firefox against astro-ui's real
    SPA. Docker's default /dev/shm is 64MB, which headless Chrome/Firefox reliably
    hangs or silently stalls on under any real page load -- confirmed live: a run
    against astro-ui produced zero further output for 48+ minutes (vs. ~20s total for
    every job combined in validation against a trivial static page), with no error, no
    crash, just silence until CircleCI's no_output_timeout killed it.

    work_dir must be world-writable: the image runs as its own unprivileged `zap`
    user, which can't write into a bind-mounted directory owned by the invoking root
    user otherwise (confirmed experimentally -- `zap.sh -autogenmax` silently fails to
    write its output file without this).
    """
    os.chmod(work_dir, 0o777)  # noqa: S103 -- must be world-writable: the image runs as its own unprivileged `zap` user
    plan_path = work_dir / "automation.yaml"
    plan_path.write_text(yaml.safe_dump(build_automation_plan(token, "/zap/wrk", error_level), sort_keys=False))

    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "--shm-size",
        "2g",
        "--volume",
        f"{work_dir}:/zap/wrk:rw",
        ZAP_IMAGE,
        "zap.sh",
        "-cmd",
        "-autorun",
        "/zap/wrk/automation.yaml",
    ]
    print(f"Running ZAP scan: {shlex.join(command)}")
    return subprocess.run(command, capture_output=True, text=True)
