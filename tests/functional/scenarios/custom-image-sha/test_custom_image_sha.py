"""Custom Astro Runtime SHA256-digest pinning, end to end on an airgapped platform.

Covers BOTH Runtime majors, since custom image SHA has to work for each on its own repo, AND
both of houston's @sha256-append paths (the config pins the repos differently on purpose):
  - Airflow 2.x: runtime 13.1.0 on quay.io/astronomer/astro-runtime, configured WITH a trailing
    @sha256 -- exercises houston's idempotency guard (.endsWith("@sha256")), which must NOT
    double-append. The final pod image is still the single-prefix quay.io/astronomer/astro-runtime
    @sha256:<hex>, NOT the ...@sha256:sha256:... an older doc warned about.
  - Airflow 3.x: runtime 3.1-2 on astrocrpublic.azurecr.io/runtime, configured WITHOUT @sha256 --
    the normal path where houston appends it.
Both must resolve to an identical valid single-prefix reference, which test_runtime_images_are_sha_pinned
asserts exactly (expected_repo is the bare repo + the config's digest in both cases).

1. (test_deployment_reaches_ready) The deployment's Airflow pods reach full readiness. This is
    the functional half: the pods can only go Running if the digest houston pinned is a real,
    pullable one. The runtime image is pulled live from the public registry (only ap-* platform
    images are preloaded into KIND, see bin/setup-kind.py), so a bogus digest would
    ImagePullBackOff -- which is exactly why the inlined runtimeReleasesConfig carries a real one.

2. (test_runtime_images_are_sha_pinned) Every Airflow runtime container references the Runtime
    image, by this deployment's major's repo, as <repo>@sha256:<64-hex>

3. (test_update_deployment_image_passes_manifest_validation) The updateDeploymentImage endpoint,
    with Docker manifest validation enabled, accepts a digest-resolved image.

4. (test_updated_runtime_images_are_sha_pinned) After the image update settles, every Airflow
    runtime container is still pinned to the single-prefix <repo>@sha256:<64-hex>.
"""

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
    update_deployment_image,
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

AF2_SHA256 = "9c57ed87a58e1822ff7b42ba824820c6372d43c2ce3876a49d8029efcd113a91"
AF3_SHA256 = "5a15c6628f4fcf8e7ce06573d98f4873c8cbede63e80ac744d448733ceae9c72"

AF2_COMPONENTS = frozenset({"scheduler", "webserver", "triggerer", "worker", "flower"})
AF3_COMPONENTS = frozenset({"scheduler", "api-server", "triggerer", "dag-processor", "worker", "flower"})

NON_RUNTIME_SIDECAR_CONTAINERS = frozenset(
    {"auth-proxy", "git-sync", "git-sync-home", "dag-server", "nginx-sidecar-conf", "sidecar-logging-consumer"}
)

RUNTIME_CASES = [
    pytest.param(
        {
            "runtime_version": "13.1.0",
            "expected_repo": AF2_REPO,
            "expected_sha256": AF2_SHA256,
            "expected_components": AF2_COMPONENTS,
            "label": "custom-image-sha-af2",
        },
        id="af2",
    ),
    pytest.param(
        {
            "runtime_version": "3.1-2",
            "expected_repo": AF3_REPO,
            "expected_sha256": AF3_SHA256,
            "expected_components": AF3_COMPONENTS,
            "label": "custom-image-sha-af3",
        },
        id="af3",
    ),
]


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
        "expected_sha256": case["expected_sha256"],
        "expected_components": case["expected_components"],
        "runtime_version": case["runtime_version"],
    }


def _runtime_containers(core_client, release_name: str, expected_components: frozenset[str]):
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    refs: dict[str, str] = {}
    found_components: set[str] = set()
    for pod in pods:
        component = (pod.metadata.labels or {}).get("component")
        if component not in expected_components:
            continue
        found_components.add(component)
        for c in list(pod.spec.init_containers or []) + list(pod.spec.containers):
            if c.name in NON_RUNTIME_SIDECAR_CONTAINERS:
                continue
            refs[f"{pod.metadata.name}/{c.name}"] = c.image
    return refs, found_components


@pytest.fixture(scope="module")
def image_updated_deployment(deployment, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """
    Drive updateDeploymentImage on the ready deployment with a digest-resolved image.
    """
    start = time.monotonic()
    release_name = deployment["release_name"]
    runtime_version = deployment["runtime_version"]
    image = f"{deployment['expected_repo']}:{runtime_version}"

    def _log(step: str) -> None:
        print(f"[image-update fixture: {release_name}] {step} ({time.monotonic() - start:.1f}s elapsed)")

    _log(f"calling updateDeploymentImage (image={image!r}, runtimeVersion={runtime_version})")
    try:
        update_deployment_image(
            _houston_api_module,
            deployment["token"],
            release_name=release_name,
            image=image,
            runtime_version=runtime_version,
        )
    except HoustonError:
        _log("updateDeploymentImage raised a HoustonError, dumping houston/commander logs")
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    _log("updateDeploymentImage accepted the image, waiting for readiness")
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, release_name)
    _log("release is ready after image update")
    return deployment


def test_deployment_reaches_ready(deployment):
    assert deployment["release_name"]


def test_runtime_images_are_sha_pinned(deployment, _k8s_core_v1_client_module):
    expected_components = deployment["expected_components"]
    refs, found_components = _runtime_containers(_k8s_core_v1_client_module, deployment["release_name"], expected_components)

    missing = expected_components - found_components
    assert not missing, (
        f"Release {deployment['release_name']!r} ({deployment['runtime_version']}) is missing expected "
        f"Airflow component pod(s): {sorted(missing)} (found {sorted(found_components)}). "
        f"A missing component would hide its Runtime container from the image check."
    )

    assert refs, (
        f"Found no Runtime containers for release {deployment['release_name']!r} across components "
        f"{sorted(expected_components)} -- selector/label drift?"
    )
    expected_ref = f"{deployment['expected_repo']}@sha256:{deployment['expected_sha256']}"
    print(f"[sha check: {deployment['runtime_version']}] asserting {len(refs)} Runtime container(s) == {expected_ref}:")
    for ref, image in sorted(refs.items()):
        print(f"  {ref} -> {image}")
    bad = {ref: image for ref, image in refs.items() if image != expected_ref}
    assert not bad, (
        f"These Runtime containers for {deployment['runtime_version']} are not pinned to the "
        f"expected immutable reference {expected_ref} (mutable tag, wrong repo, wrong digest, or the "
        f"invalid double-prefixed @sha256:sha256:... form the doc warns about): {bad}"
    )


def test_update_deployment_image_passes_manifest_validation(image_updated_deployment):
    """The image_updated_deployment fixture raises if updateDeploymentImage was rejected -- which,
    with Docker manifest validation enabled, is exactly the regression: Houston would have fetched
    the manifest at the invalid <repo>@sha256/manifests/<hex> URL, gotten a 404, and raised
    DockerRetrieveManifestError. Reaching this assertion means validation hit the correct
    <repo>/manifests/sha256:<hex> URL and the update was accepted.
    """
    assert image_updated_deployment["release_name"]


def test_updated_runtime_images_are_sha_pinned(image_updated_deployment, _k8s_core_v1_client_module):
    """
    After the registry-path image update settles, pods are still single-prefix digest-pinned.
    """
    deployment = image_updated_deployment
    expected_components = deployment["expected_components"]
    refs, found_components = _runtime_containers(_k8s_core_v1_client_module, deployment["release_name"], expected_components)

    missing = expected_components - found_components
    assert not missing, (
        f"Release {deployment['release_name']!r} ({deployment['runtime_version']}) is missing expected "
        f"Airflow component pod(s) after image update: {sorted(missing)} (found {sorted(found_components)})."
    )
    assert refs, (
        f"Found no Runtime containers for release {deployment['release_name']!r} after image update "
        f"across components {sorted(expected_components)} -- selector/label drift?"
    )
    expected_ref = f"{deployment['expected_repo']}@sha256:{deployment['expected_sha256']}"
    print(
        f"[sha check after update: {deployment['runtime_version']}] asserting {len(refs)} Runtime container(s) == {expected_ref}:"
    )
    for ref, image in sorted(refs.items()):
        print(f"  {ref} -> {image}")
    bad = {ref: image for ref, image in refs.items() if image != expected_ref}
    assert not bad, (
        f"After updateDeploymentImage, these Runtime containers for {deployment['runtime_version']} are "
        f"not pinned to the expected immutable reference {expected_ref}: {bad}"
    )
