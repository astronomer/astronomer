#!/usr/bin/env python3

from os import environ
from pathlib import Path
import yaml
from time import sleep, time
from subprocess import check_output
from packaging.version import parse as semver
import git

# The top-level path of this repository
git_repo = git.Repo(__file__, search_parent_directories=True)
git_root_dir = Path(git_repo.git.rev_parse("--show-toplevel"))


def test_upgrade():
    """
    Functional test for the LTS to LTS upgrade (0.23 to 0.25)
    """
    print("Checking current chart version")

    with open(Path(git_root_dir / "Chart.yaml")) as f:
        astro_chart_dot_yaml = yaml.safe_load(f.read())
    major, minor, patch = semver(astro_chart_dot_yaml["version"]).release

    assert major == 0 and minor == 25, "This test is only applicable for 0.25"

    upgrade_manifest_path = Path(
        git_root_dir
        / "migrations/scripts/lts-to-lts/0.23-to-0.25/manifests/upgrade-0.23-to-0.25.yaml"
    )
    rollback_manifest_path = Path(
        git_root_dir
        / "migrations/scripts/lts-to-lts/0.23-to-0.25/manifests/rollback-0.23-to-0.25.yaml"
    )

    namespace = environ.get("NAMESPACE")
    release_name = environ.get("RELEASE_NAME")
    print("Checking NAMESPACE")
    if not namespace:
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = "astronomer"
    print("Checking RELEASE_NAME")
    if not release_name:
        print(
            "RELEASE_NAME env var is not present, assuming 'astronomer' is the release name"
        )
        release_name = "astronomer"

    print("Checking installed version")
    helm_history = check_output(
        f"helm3 history { release_name } -n { namespace }", shell=True
    ).decode("utf8")
    print(f"Helm history: (pre-upgrade)\n{helm_history}")

    assert (
        "0.23" in helm_history.split("\n")[-2]
    ), "Expected 0.23 to be installed before upgrade"
    assert (
        "deployed" in helm_history.split("\n")[-2]
    ), "Expected state to be deployed before upgrade"

    upgrade_manifest_data = rewrite_manifest_for_local_testing(upgrade_manifest_path)
    upgrade_manifest_yaml = [doc for doc in yaml.safe_load_all(upgrade_manifest_data)]
    for i, doc in enumerate(upgrade_manifest_yaml):
        if doc.get("kind") == "Job":
            try:
                containers = doc["spec"]["template"]["spec"]["containers"]
                for container in containers:
                    if not container.get("env"):
                        container["env"] = []
                    container["env"].append(
                        {"name": "USE_INTERNAL_HELM_REPO", "value": "True"}
                    )
                    print("Modified test env with USE_INTERNAL_HELM_REPO=True")
                upgrade_manifest_yaml[i] = doc
            except KeyError:
                pass

    upgrade_manifest_data = yaml.safe_dump_all(upgrade_manifest_yaml)

    modified_upgrade_manifest_path = f"{upgrade_manifest_path}.test.yaml"
    with open(modified_upgrade_manifest_path, "w") as f:
        f.write(upgrade_manifest_data)
    print("Performing upgrade from 0.23 to 0.25")
    check_output(f"kubectl apply -f {modified_upgrade_manifest_path}", shell=True)
    timeout = 800
    start_time = time()
    while True:
        sleep(5)
        result = check_output(
            "kubectl get pods -n default | grep upgrade-astronomer", shell=True
        ).decode("utf8")
        if "Completed" in result:
            print("Upgrade pod finished in success")
            break
        if "Error" in result:
            print("Upgrade pod finished in error")
            logs = check_output(
                "kubectl logs $(kubectl get pods -n default | grep upgrade-astronomer | awk "
                + "'{ print $1 }')",
                shell=True,
            ).decode("utf8")
            print(logs)
            assert False, "Failed to perform upgrade, see logs"
        if time() - start_time > timeout:
            logs = check_output(
                "kubectl logs $(kubectl get pods -n default | grep upgrade-astronomer | awk "
                + "'{ print $1 }')",
                shell=True,
            ).decode("utf8")
            print(logs)
            assert False, "Failed to perform upgrade (timeout!), see logs"

    helm_history = check_output(
        f"helm3 history { release_name } -n { namespace }", shell=True
    ).decode("utf8")
    print(f"Helm history: (post-upgrade)\n{helm_history}")

    assert (
        "0.25" in helm_history.split("\n")[-2]
    ), "Expected version 0.25 to be installed after upgrade"
    assert (
        "deployed" in helm_history.split("\n")[-2]
    ), "Expected state to be deployed after upgrade"

    rollback_manifest_data = rewrite_manifest_for_local_testing(rollback_manifest_path)

    with open(f"{rollback_manifest_path}.test.yaml", "w") as f:
        f.write(rollback_manifest_data)
    check_output(f"kubectl apply -f {rollback_manifest_path}.test.yaml", shell=True)
    timeout = 800
    start_time = time()
    while True:
        sleep(5)
        result = check_output(
            "kubectl get pods -n default | grep rollback", shell=True
        ).decode("utf8")
        if "Completed" in result:
            print("Rollback pod finished in success")
            break
        if "Error" in result:
            print("Rollback pod finished in error")
            logs = check_output(
                "kubectl logs $(kubectl get pods -n default | grep rollback | awk "
                + "'{ print $1 }')",
                shell=True,
            ).decode("utf8")
            print(logs)
            assert False, "Failed to perform rollback, see logs"
        if time() - start_time > timeout:
            logs = check_output(
                "kubectl logs $(kubectl get pods -n default | grep rollback | awk "
                + "'{ print $1 }')",
                shell=True,
            ).decode("utf8")
            print(logs)
            assert False, "Failed to perform rollback (timeout!), see logs"

    helm_history = check_output(
        f"helm3 history { release_name } -n { namespace }", shell=True
    ).decode("utf8")
    print(f"Helm history: (post-rollback)\n{helm_history}")

    assert (
        "0.23" in helm_history.split("\n")[-2]
    ), "Expected version 0.23 to be installed after rollback"
    assert (
        "deployed" in helm_history.split("\n")[-2]
    ), "Expected state to be deployed after rollback"


def rewrite_manifest_for_local_testing(manifest):
    # Rewrite some parts of the k8s manifest with testing-specific configs
    with open(manifest) as f:
        new_manifest = f.read()

    new_manifest = new_manifest.replace(
        "image: quay.io/astronomer/lts-23-to-25-upgrade:latest",
        "image: lts-23-to-25-upgrade:latest",
    )
    new_manifest = new_manifest.replace(
        "imagePullPolicy: Always", "imagePullPolicy: Never"
    )
    return new_manifest
