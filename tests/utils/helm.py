"""Live-upgrade the platform Astronomer Helm release from inside a running functional test.

Every other scenario applies its values overlays once, at initial `helm install` time (see
bin/run-scenario.py / bin/helm-install.py). The readonly-root-*-to-* scenarios need something
different: they create an Airflow Deployment first, and only *afterward* run a real
`helm upgrade` of the platform release to disable Houston's default readOnlyRootFilesystem --
because the thing under test is upgradeDeployments' own pre-upgrade hook Job
(houston-upgrade-deployments-job) actually rolling an already-existing deployment forward onto
the new securityContext, not just a chart rendering it correctly at install time.
"""

import subprocess
from pathlib import Path

GIT_ROOT_DIR = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
HELM_EXE = str(Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "helm")


def upgrade_platform_release(
    kubeconfig: str,
    *values_files: str,
    namespace: str = "astronomer",
    release_name: str = "astronomer",
    timeout: str = "10m0s",
) -> None:
    """Run `helm upgrade --reuse-values` on the platform release with one or more extra values
    files layered on top.

    --reuse-values keeps every value the scenario's initial install already set (including
    whatever `tests/functional/scenarios/<name>/test_profile.yaml` passed at install time) and
    merges values_files on top of that -- the same semantics `helm upgrade` always has, just
    invoked mid-test instead of via bin/helm-install.py.

    Deliberately does NOT pass --no-hooks: this needs the houston-upgrade-deployments-job
    pre-upgrade hook to actually run, since that Job (`yarn upgrade-deployments`) is what
    reconciles existing Airflow Deployments onto the new Houston config. Helm blocks until a
    pre-upgrade hook Job completes, so by the time this returns, that hook has already run --
    but the per-deployment helm upgrade Commander triggers as a result is still asynchronous,
    so callers should snapshot_release_revisions() before calling this and pass it to
    wait_for_release_ready(previous_revisions=...) afterward, exactly as for an
    upsertDeployment-driven switch.
    """
    command = [
        HELM_EXE,
        "upgrade",
        release_name,
        str(GIT_ROOT_DIR),
        f"--namespace={namespace}",
        f"--kubeconfig={kubeconfig}",
        f"--timeout={timeout}",
        "--reuse-values",
    ]
    command.extend(f"--values={values_file}" for values_file in values_files)
    subprocess.run(command, check=True)
