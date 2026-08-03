"""git-sync-private-ca (PINF-1109): git-sync-relay cloning over HTTPS+PAT from a Git host
whose TLS cert is signed by a private CA the platform trusts via global.privateCaCerts
(the PINF-774 fix).

Structure mirrors auth-sidecar's scenario: module-scoped fixtures bootstrap one admin +
one Airflow Deployment (a fresh Deployment per test would be far too slow and would blow
the CI node's CPU budget). The forgejo-ca / forgejo-tls Secrets and the git-forgejo
namespace are created before install by bin/setup-forgejo-ca.py (a pre_helm_script); this
file deploys Forgejo itself (forgejo.yaml), seeds a private repo + read-only PAT, and then
points a git_sync HTTPS_PAT Deployment at it.

The headline assertion is deployment readiness: git-sync-relay's git-daemon container's
probes only pass once it has actually cloned the repo (they check for a post-clone marker
file), so the deployment reaching ready IS proof the relay completed a real HTTPS clone
against the private-CA host with full TLS validation -- the core PINF-774 regression.
"""

import base64
import contextlib
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests
import testinfra
import urllib3
from kubernetes import client, config

from tests.utils.houston_graphql import (
    HoustonError,
    create_user,
    create_workspace,
    dump_pod_logs,
    get_cluster_id,
    upsert_deployment,
    wait_for_release_ready,
)
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector

# See bin/setup-forgejo-ca.py -- these identifiers MUST match it and forgejo.yaml.
PLATFORM_NAMESPACE = "astronomer"
FORGEJO_NAMESPACE = "git-forgejo"
FORGEJO_FQDN = "forgejo.git-forgejo.svc.cluster.local"
FORGEJO_PORT = 3000
CA_SECRET_NAME = "forgejo-ca"
FORGEJO_MANIFEST = Path(__file__).parent / "forgejo.yaml"

FORGEJO_ADMIN = "astro"
FORGEJO_ADMIN_PASSWORD = "astro-test-pw"
FORGEJO_REPO = "dags"
# The in-cluster URL the relay clones from (private repo, so cloned with the PAT).
CLONE_URL = f"https://{FORGEJO_FQDN}:{FORGEJO_PORT}/{FORGEJO_ADMIN}/{FORGEJO_REPO}.git"

# Same PINF-1049 JWKS-cold-start flake auth-sidecar guards against (commander's first JWKS
# fetch can race Houston's readiness gate). Rerun only on that exact upsertDeployment error.
JWKS_COLD_START_ERROR = "13 INTERNAL: failed to validate token"

ADMIN_EMAIL = "pinf-1109-git-sync-private-ca@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "pinf-1109-git-sync-private-ca"
DEPLOYMENT_LABEL = "pinf-1109-git-sync-private-ca"


def _kubectl(*args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["kubectl", f"--kubeconfig={KUBECONFIG_UNIFIED}", *args], text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"kubectl {' '.join(args)} failed (exit {result.returncode}):\n{result.stdout}{result.stderr}")
    return result


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module() -> client.AppsV1Api:
    """Module-scoped (conftest's is function-scoped and can't back a module-scoped fixture)."""
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _k8s_core_v1_client_module() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def _houston_api_module():
    pod = get_pod_by_label_selector(PLATFORM_NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={PLATFORM_NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def _admin_token(_houston_api_module):
    """The cluster's one-and-only admin (createUser's unauthenticated signup only works once)."""
    return create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)


def _wait_for_deployment_ready(apps_client: client.AppsV1Api, name: str, namespace: str, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dep = apps_client.read_namespaced_deployment(name, namespace)
        if (dep.status.ready_replicas or 0) >= (dep.spec.replicas or 1):
            return
        time.sleep(5)
    raise AssertionError(f"Deployment {namespace}/{name} never became ready within {timeout}s")


@contextlib.contextmanager
def _port_forward(service: str, namespace: str, remote_port: int):
    """Port-forward a Service to a free local port; yields that local port. Seeding-only."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        local_port = s.getsockname()[1]
    proc = subprocess.Popen(
        [
            "kubectl",
            f"--kubeconfig={KUBECONFIG_UNIFIED}",
            "port-forward",
            f"svc/{service}",
            f"{local_port}:{remote_port}",
            "-n",
            namespace,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for the tunnel to accept connections.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", local_port), timeout=1):
                break
            time.sleep(0.5)
        yield local_port
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture(scope="module")
def forgejo(_k8s_apps_v1_client_module):
    """Deploy the in-cluster Forgejo host, then seed an admin, a private repo, and a read-only PAT.

    Returns the clone URL + credentials for a git_sync HTTPS_PAT deployment. TLS verification
    is intentionally OFF for these seeding calls (verify=False): the relay's in-cluster trust
    of the private CA is what's under test, not the test runner's path to the Forgejo API.
    """
    _kubectl("apply", "-f", str(FORGEJO_MANIFEST))
    _wait_for_deployment_ready(_k8s_apps_v1_client_module, "forgejo", FORGEJO_NAMESPACE)
    forgejo_pod = get_pod_by_label_selector(FORGEJO_NAMESPACE, "app=forgejo", KUBECONFIG_UNIFIED)

    def forgejo_cli(*args: str) -> str:
        # Forgejo refuses to run as root, and the container's default exec user is root, so drop
        # to the git user (uid 1000) with su-exec -- matching the docker-compose fixture's -u 1000.
        return _kubectl("exec", forgejo_pod, "-n", FORGEJO_NAMESPACE, "--", "su-exec", "git", "forgejo", *args).stdout.strip()

    forgejo_cli(
        "admin",
        "user",
        "create",
        "--username",
        FORGEJO_ADMIN,
        "--password",
        FORGEJO_ADMIN_PASSWORD,
        "--email",
        f"{FORGEJO_ADMIN}@example.com",
        "--admin",
        "--must-change-password=false",
    )
    pat = forgejo_cli(
        "admin",
        "user",
        "generate-access-token",
        "--username",
        FORGEJO_ADMIN,
        "--scopes",
        "read:repository",
        "--token-name",
        "git-sync",
        "--raw",
    )
    assert pat, "Forgejo generate-access-token returned an empty PAT"

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    with _port_forward("forgejo", FORGEJO_NAMESPACE, FORGEJO_PORT) as local_port:
        resp = requests.post(
            f"https://127.0.0.1:{local_port}/api/v1/user/repos",
            auth=(FORGEJO_ADMIN, FORGEJO_ADMIN_PASSWORD),
            json={"name": FORGEJO_REPO, "private": True, "auto_init": True},
            verify=False,  # noqa: S501 -- seeding path, not the private-CA trust under test
            timeout=30,
        )
    assert resp.status_code in (201, 409), f"Forgejo repo create failed: {resp.status_code} {resp.text}"

    return {"clone_url": CLONE_URL, "username": FORGEJO_ADMIN, "pat": pat}


@pytest.fixture(scope="module")
def git_sync_deployment(forgejo, _admin_token, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """One Airflow Deployment (git_sync, HTTPS_PAT) pointed at the private-CA Forgejo repo."""
    token = _admin_token
    workspace_id = create_workspace(_houston_api_module, token, WORKSPACE_LABEL)
    cluster_id = get_cluster_id(_houston_api_module, token)
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="CeleryExecutor",
            label=DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
            dag_deployment_type="git_sync",
            repository_url=forgejo["clone_url"],
            auth_type="HTTPS_PAT",
            https_username=forgejo["username"],
            https_token=forgejo["pat"],
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


@pytest.mark.flaky(reruns=5, reruns_delay=5, only_rerun=[JWKS_COLD_START_ERROR])
def test_git_sync_deployment_reaches_ready(git_sync_deployment):
    """TC-CA-03 / TC-CA-07: the headline. git-sync-relay's git-daemon probes only pass once it
    has cloned the repo, so readiness here == a real HTTPS+PAT clone against the private-CA host
    succeeded with full TLS validation (no GIT_SSL_NO_VERIFY). This is the core PINF-774 case,
    and coexisting with HTTPS+PAT auth is TC-CA-07."""
    assert git_sync_deployment["release_name"]


def _relay_pod(core_client, release_name):
    """The git-sync-relay pod for a release. Read its namespace off pod.metadata.namespace --
    the Airflow Deployment namespace is astronomer-<release>, not the release name.

    Filter by pod NAME containing 'git-sync-relay', not by a git-sync *container* name: the
    Airflow component pods (scheduler/worker/webserver/...) each carry a git-sync *sidecar*
    container, so a container-name match would also hit them. The relay is <release>-git-sync-relay-*.
    """
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    relay = [p for p in pods if "git-sync-relay" in p.metadata.name]
    assert relay, f"No git-sync-relay pod for release {release_name!r} (pods: {[p.metadata.name for p in pods]})"
    return relay[0]


def test_relay_has_private_ca_wiring(git_sync_deployment, _k8s_core_v1_client_module):
    """TC-CA-01: the deployed git-sync-relay pod carries the CA wiring derived from
    global.privateCaCerts -- the etc-ssl-certs-copier initContainer, the private-ca-* volume,
    and UPDATE_CA_CERTS=true on the git-sync container."""
    pod = _relay_pod(_k8s_core_v1_client_module, git_sync_deployment["release_name"])
    init_names = [c.name for c in (pod.spec.init_containers or [])]
    assert "etc-ssl-certs-copier" in init_names, f"Expected the CA-copier initContainer, got: {init_names}"
    volume_names = [v.name for v in pod.spec.volumes]
    assert any(v.startswith("private-ca-") for v in volume_names), f"Expected a private-ca-* volume, got: {volume_names}"
    git_sync = next(c for c in pod.spec.containers if "git-sync" in c.name)
    env = {e.name: e.value for e in (git_sync.env or [])}
    assert env.get("UPDATE_CA_CERTS") == "true", f"Expected UPDATE_CA_CERTS=true on the git-sync container, got: {env}"


def test_forgejo_ca_synced_to_deployment_namespace(git_sync_deployment, _k8s_core_v1_client_module):
    """TC-CA-10: commander synced the (commander-sync-annotated) forgejo-ca Secret from the
    platform namespace into the Airflow Deployment namespace, where the relay mounts it -- the
    houston->commander->chart contract that makes the relay trust the CA."""
    namespace = _relay_pod(_k8s_core_v1_client_module, git_sync_deployment["release_name"]).metadata.namespace
    secret = _k8s_core_v1_client_module.read_namespaced_secret(CA_SECRET_NAME, namespace)
    assert "cert.pem" in (secret.data or {}), (
        f"Expected commander to sync Secret {namespace}/{CA_SECRET_NAME} with a cert.pem key, got: "
        f"{list((secret.data or {}).keys())}"
    )
    base64.b64decode(secret.data["cert.pem"])  # sanity: it's valid base64 cert data


def test_relay_trusts_ca_in_system_store(git_sync_deployment, _k8s_core_v1_client_module):
    """TC-CA-02: the forgejo-ca is installed into the git-sync container's system trust store
    (update-ca-certificates ran over /etc/ssl/certs), matched by SHA-256 fingerprint against
    the mounted CA -- not by symlink name, which is hash-derived."""
    pod = _relay_pod(_k8s_core_v1_client_module, git_sync_deployment["release_name"])
    namespace, relay_pod = pod.metadata.namespace, pod.metadata.name
    git_sync_container = next(c.name for c in pod.spec.containers if "git-sync" in c.name)

    def relay_exec(script: str) -> str:
        return _kubectl("exec", relay_pod, "-n", namespace, "-c", git_sync_container, "--", "sh", "-c", script).stdout

    # Fingerprint of the CA the chart mounted for the relay.
    mounted_fp = relay_exec("openssl x509 -in /usr/local/share/ca-certificates/private-ca-*.pem -noout -fingerprint -sha256")
    fp = mounted_fp.split("=", 1)[-1].strip()
    assert fp, f"Could not read the mounted CA fingerprint from the relay pod: {mounted_fp!r}"
    # Assert that exact fingerprint is present in the system trust bundle git uses.
    present = relay_exec(
        "awk '/BEGIN CERT/{n++} {print > (\"/tmp/c\" n)}' /etc/ssl/certs/ca-certificates.crt; "
        'for f in /tmp/c*; do openssl x509 -in "$f" -noout -fingerprint -sha256 2>/dev/null; done'
    )
    assert fp in present, f"Forgejo CA fingerprint {fp} not found in the relay's /etc/ssl/certs bundle"
