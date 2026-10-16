"""Custom Astro Runtime SHA256-digest pinning, end to end on an airgapped platform.

Covers BOTH Runtime majors, since custom image SHA has to work for each on its own repo:
  - Airflow 2.x: runtime 13.1.0 on quay.io/astronomer/astro-runtime (helm.runtimeImages)
  - Airflow 3.x: runtime 3.1-2 on astrocrpublic.azurecr.io/runtime (helm.runtimeImagesV3)

1. (test_deployment_reaches_ready) The deployment's Airflow pods reach full readiness. This is
    the functional half: the pods can only go Running if the digest houston pinned is a real,
    pullable one. The runtime image is pulled live from the public registry (only ap-* platform
    images are preloaded into KIND, see bin/setup-kind.py), so a bogus digest would
    ImagePullBackOff -- which is exactly why the inlined runtimeReleasesConfig carries a real one.

2. (test_runtime_images_are_sha_pinned) Every Airflow runtime container references the Runtime
    image, by this deployment's major's repo, as <repo>@sha256:<64-hex>
"""

import re
import time

import pytest
import testinfra
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

NAMESPACE = "astronomer"
ADMIN_EMAIL = "custom-image-sha-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "custom-image-sha"

AF2_REPO = "quay.io/astronomer/astro-runtime"
AF3_REPO = "astrocrpublic.azurecr.io/runtime"
RUNTIME_REPOS = (AF2_REPO, AF3_REPO)

RUNTIME_CASES = [
    pytest.param({"runtime_version": "13.1.0", "expected_repo": AF2_REPO, "label": "custom-image-sha-af2"}, id="af2"),
    pytest.param({"runtime_version": "3.1-2", "expected_repo": AF3_REPO, "label": "custom-image-sha-af3"}, id="af3"),
]

SHA_PINNED_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module() -> client.AppsV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _k8s_core_v1_client_module() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def _houston_api_module():
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def _admin_token(_houston_api_module):
    token = create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)
    workspace_id = create_workspace(_houston_api_module, token, WORKSPACE_LABEL)
    return {"token": token, "workspace_id": workspace_id}


@pytest.fixture(scope="module", params=RUNTIME_CASES)
def deployment(request, _admin_token, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    case = request.param
    token = _admin_token["token"]
    start = time.monotonic()

    def _log(step: str) -> None:
        print(f"[deployment fixture: {case['label']}] {step} ({time.monotonic() - start:.1f}s elapsed)")

    _log("looking up default cluster id")
    cluster_id = get_cluster_id(_houston_api_module, token)
    _log(f"calling upsertDeployment (runtimeVersion={case['runtime_version']})")
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="CeleryExecutor",
            label=case["label"],
            workspace_id=_admin_token["workspace_id"],
            cluster_id=cluster_id,
            runtime_version=case["runtime_version"],
        )
    except HoustonError:
        _log("upsertDeployment raised a HoustonError, dumping houston/commander logs")
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    _log(f"upsertDeployment returned releaseName={created['releaseName']!r}, waiting for readiness")
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    _log("release is ready")
    return {
        "token": token,
        "id": created["id"],
        "release_name": created["releaseName"],
        "expected_repo": case["expected_repo"],
        "runtime_version": case["runtime_version"],
    }


def _runtime_image_refs(core_client, release_name: str) -> dict[str, str]:
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    refs: dict[str, str] = {}
    for pod in pods:
        containers = list(pod.spec.containers) + list(pod.spec.init_containers or [])
        for c in containers:
            if c.image and c.image.startswith(RUNTIME_REPOS):
                refs[f"{pod.metadata.name}/{c.name}"] = c.image
    return refs


def test_deployment_reaches_ready(deployment):
    assert deployment["release_name"]


def test_runtime_images_are_sha_pinned(deployment, _k8s_core_v1_client_module):
    refs = _runtime_image_refs(_k8s_core_v1_client_module, deployment["release_name"])
    assert refs, (
        f"Found no Runtime-image containers for release {deployment['release_name']!r} "
        f"(expected images under one of {RUNTIME_REPOS}). Selector/label drift?"
    )
    print(f"[sha check: {deployment['runtime_version']}] asserting {len(refs)} Runtime container(s):")
    for ref, image in sorted(refs.items()):
        print(f"  {ref} -> {image}")
    expected_repo = deployment["expected_repo"]
    bad = {}
    for ref, image in refs.items():
        if not SHA_PINNED_RE.match(image):
            bad[ref] = f"{image} (not a bare @sha256:<64-hex> digest)"
        elif not image.startswith(expected_repo + "@"):
            bad[ref] = f"{image} (wrong repo, expected {expected_repo})"
    assert not bad, (
        f"These Runtime containers for {deployment['runtime_version']} are not pinned to "
        f"{expected_repo}@sha256:<64-hex> (mutable tag, wrong repo, or the invalid double-prefixed "
        f"@sha256:sha256:... form the doc warns about): {bad}"
    )
