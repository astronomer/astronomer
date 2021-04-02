#!/usr/bin/env python3

import os
import yaml
from time import sleep, time
from subprocess import check_output
from packaging.version import parse as semver

# The top-level path of this repository
git_root_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..")


def test_upgrade():
    """
    Functional test for the LTS to LTS upgrade (0.16 to 0.23)
    """
    with open(os.path.join(git_root_dir, "Chart.yaml"), "r") as f:
        astro_chart_dot_yaml = yaml.safe_load(f.read())
    major, minor, patch = semver(astro_chart_dot_yaml["version"]).release

    assert major == 0 and minor == 23, "This test is only applicable for 0.23"

    upgrade_manifest_path = os.path.join(
        git_root_dir,
        "bin/migration-scripts/lts-to-lts/0.16-to-0.23/manifests/upgrade-0.16-to-0.23.yaml",
    )
    rollback_manifest_path = os.path.join(
        git_root_dir,
        "bin/migration-scripts/lts-to-lts/0.16-to-0.23/manifests/rollback-0.16-to-0.23.yaml",
    )

    namespace = os.environ.get("NAMESPACE")
    release_name = os.environ.get("RELEASE_NAME")
    if not namespace:
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = "astronomer"
    if not release_name:
        print(
            "RELEASE_NAME env var is not present, assuming 'astronomer' is the release name"
        )
        release_name = "astronomer"

    # Get the existing values
    result = check_output(
        f"helm3 history { release_name } -n { namespace } | tail -n 1", shell=True
    ).decode("utf8")
    assert "0.16" in result
    # rewrite manifest to replace with CI image for Kind test
    with open(upgrade_manifest_path, "r") as f:
        upgrade_manifest_data = f.read()
    upgrade_manifest_data = upgrade_manifest_data.replace(
        "image: quay.io/astronomer/lts-016-023-upgrade:latest",
        "image: lts-016-023-upgrade:latest",
    )
    upgrade_manifest_data = upgrade_manifest_data.replace(
        "imagePullPolicy: Always", "imagePullPolicy: Never"
    )
    with open(f"{upgrade_manifest_path}.test.yaml", "w") as f:
        f.write(upgrade_manifest_data)
    check_output(f"kubectl apply -f {upgrade_manifest_path}.test.yaml", shell=True)
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
    result = check_output(
        "helm3 history astronomer -n astronomer | tail -n 1", shell=True
    ).decode("utf8")
    assert "0.23" in result and "deployed" in result, "Expected upgrade to be performed"
    with open(rollback_manifest_path, "r") as f:
        rollback_manifest_data = f.read()
    rollback_manifest_data = rollback_manifest_data.replace(
        "image: quay.io/astronomer/lts-016-023-upgrade:latest",
        "image: lts-016-023-upgrade:latest",
    )
    rollback_manifest_data = rollback_manifest_data.replace(
        "imagePullPolicy: Always", "imagePullPolicy: Never"
    )
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
    result = check_output(
        "helm3 history astronomer -n astronomer | tail -n 1", shell=True
    ).decode("utf8")
    assert (
        "0.16" in result and "deployed" in result
    ), "Expected rollback to be performed"
