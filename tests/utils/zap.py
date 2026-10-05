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
import tempfile
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
    with tempfile.TemporaryDirectory() as log_dir:
        log_path = Path(log_dir) / "kubectl-port-forward.log"
        # A file, not DEVNULL or an unread PIPE: readiness is checked via
        # _wait_for_port's own socket connect, not by watching this output, but a real
        # kubectl failure (RBAC, missing service) should still be visible if the port
        # never comes up -- DEVNULL would silently swallow it behind a generic timeout,
        # and an unread PIPE risks the deadlock this replaced in the first place.
        log_file = log_path.open("w")
        proc = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)
        try:
            try:
                _wait_for_port(local_port)
            except RuntimeError as exc:
                log_file.flush()
                raise RuntimeError(f"{exc}\nkubectl port-forward output:\n{log_path.read_text()}") from None
            yield
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            log_file.close()


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
                        # Without this, the token would go out on every request ZAP
                        # makes, including ones to unrelated third-party hosts (e.g.
                        # spiderAjax's headless Firefox making its own background
                        # requests). Scoped to exactly the two origins in this plan's
                        # "apc" context above.
                        "url": rf"^http://localhost:({HOUSTON_LOCAL_PORT}|{ASTRO_UI_LOCAL_PORT})(/|$)",
                    }
                ],
            },
            # Schema-aware API scan: imports houston-api's GraphQL schema via
            # introspection; `activeScan` below then attacks every query/mutation it
            # generates from that schema. No `context` param -- this ZAP version's
            # graphql job doesn't accept one, it just uses whichever context matches
            # the endpoint URL (we only ever have one).
            #
            # Query-gen params tuned down from ZAP's defaults (maxQueryDepth 5,
            # maxAdditionalQueryDepth 5, optionalArgsEnabled true, argsType both,
            # querySplitType leaf): generating queries isn't pure local computation --
            # GraphQlGenerator.generate() sends a real HTTP request per leaf while
            # building the query tree, so the defaults mean hundreds of real
            # round-trips to Houston's live resolvers, each one a chance for a slow
            # response or a port-forward hiccup to stall the whole single-threaded job.
            # Fewer, shallower, per-operation requests avoids that.
            {
                "type": "graphql",
                "parameters": {
                    "endpoint": f"{houston_url}/v1",
                    "maxQueryDepth": 2,
                    "maxAdditionalQueryDepth": 0,
                    "optionalArgsEnabled": False,
                    "argsType": "variables",
                    "querySplitType": "operation",
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
                # --shm-size in run_zap_scan() below). maxDuration defaults to unlimited;
                # bounded for the same reason activeScan is below.
                "parameters": {"url": astro_ui_url, "context": "apc", "numberOfBrowsers": 2, "maxDuration": 10},
            },
            {"type": "passiveScan-wait", "parameters": {"maxDuration": 10}},
            # threadPerHost defaults to 2x core count (15-28 here) -- too many concurrent
            # threads for the single `kubectl port-forward` tunnel (see port_forward()
            # above) to handle: it starts failing to establish new connections rather
            # than just answering slowly. Dropped to 2 so it isn't overwhelmed.
            # maxScanDurationInMins/maxRuleDurationInMins (both default unlimited) bound
            # worst case regardless of root cause.
            # defaultStrength/defaultThreshold dropped Medium->Low to cut total payload
            # volume, reducing connection churn independent of concurrency.
            {
                "type": "activeScan",
                "parameters": {
                    "context": "apc",
                    "threadPerHost": 2,
                    "maxScanDurationInMins": 30,
                    "maxRuleDurationInMins": 10,
                },
                "policyDefinition": {
                    "defaultStrength": "Low",
                    "defaultThreshold": "Low",
                },
            },
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
    """Write the automation plan into a scratch directory and run it via the official
    ZAP Docker image, writing the report into work_dir.

    The plan and the report live in two separate bind mounts, not one shared
    directory: the plan embeds the bearer token (see build_automation_plan's
    `replacer` job), and work_dir is what CI uploads wholesale as the scan's report
    artifact. Keeping the plan out of work_dir means that upload can never include
    the token, without having to scrub or allowlist individual files in it.

    `--network host`: ZAP (in its own container) needs to reach the `kubectl
    port-forward` processes' listening sockets on localhost, which only works if it
    shares the host's network namespace -- CircleCI's machine executor (and a local
    dev workstation running Docker directly) both support this.

    `--shm-size=2g`: spiderAjax drives a real headless Firefox against astro-ui's real
    SPA. Docker's default /dev/shm (64MB) is too small for headless Chrome/Firefox to
    render a real page reliably -- it hangs or silently stalls rather than erroring.

    `--init`: spiderAjax's headless Firefox leaves behind child processes
    (crashhelper/RDD Process/Utility Process) that the image's own entrypoint (plain
    `java`, as PID 1) never reaps. A real init process reaps them properly.

    Both mounted directories must be world-writable/readable: the image runs as its
    own unprivileged `zap` user, which can't access a bind-mounted directory owned by
    the invoking root user otherwise.
    """
    os.chmod(work_dir, 0o777)  # noqa: S103 -- see docstring: the image's `zap` user needs to write the report here
    with tempfile.TemporaryDirectory() as plan_dir:
        os.chmod(plan_dir, 0o777)  # noqa: S103 -- see docstring: the image's `zap` user needs to read the plan here
        plan_path = Path(plan_dir) / "automation.yaml"
        plan_path.write_text(yaml.safe_dump(build_automation_plan(token, "/zap/wrk", error_level), sort_keys=False))

        command = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--network",
            "host",
            "--shm-size",
            "2g",
            "--volume",
            f"{plan_dir}:/zap/plan:ro",
            "--volume",
            f"{work_dir}:/zap/wrk:rw",
            ZAP_IMAGE,
            "zap.sh",
            "-cmd",
            "-autorun",
            "/zap/plan/automation.yaml",
        ]
        print(f"Running ZAP scan: {shlex.join(command)}")
        # Stream output live instead of subprocess.run(capture_output=True): that would
        # buffer everything -- including ZAP's own progressToStdout job-by-job lines --
        # until the process exits, giving CircleCI's no_output_timeout nothing to see no
        # matter how long a legitimately-healthy scan takes.
        #
        # Tee to a log file in work_dir rather than an in-memory list: ZAP's own output
        # has no size bound we control, and work_dir is already the directory CI uploads
        # as the scan's artifacts, so the full log becomes downloadable right alongside
        # the HTML/JSON report instead of only living in the CI job's console output.
        log_path = work_dir / "zap-scan.log"
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        with log_path.open("w") as log_file:
            for line in process.stdout:
                print(line, end="")
                log_file.write(line)
        process.wait()
        return subprocess.CompletedProcess(command, process.returncode, stdout="", stderr="")
