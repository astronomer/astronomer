"""Runtime assertions for file-based secret loading (global.secretsFromFiles).

The chart side of this feature has ~7200 render tests. This module deliberately asserts
only what `helm template` provably cannot see, because the two worst bugs in this
feature's history were both schema-valid on paper and fatal at container start:

  - the secret volume mounted at /run/secrets, where runc cannot create the
    service-account token's mountpoint inside a read-only mount, so the container
    reported StartError before any application code ran; and
  - the loader imported with a bare specifier that babel never rewrote, so
    `require("secrets-from-files")` was unresolvable and houston would have crash-looped
    at boot the moment the branch shipped.

A Ready pod proves nothing here. houston's /v1/healthz is `res.status(200).send({})` and
backs both probes, touching neither the database nor config -- so the pod goes Ready
whether or not a single secret was read from a file. Every assertion below therefore looks
at evidence the process itself produced, not at pod phase.

Three loaders exist (houston TypeScript, commander Go, kuiper Python) and are
contract-identical in behaviour. They are NOT identical in observability: kuiper's
"Loaded N secret(s)" is logger.info, emitted before any logging handler or level is
configured, so the root logger's WARNING default swallows it. The filesd-reloader
container therefore never prints the line the other two do, and its proof has to be
behavioural instead. That asymmetry is why test_kuiper_* below looks different.
"""

import re
import subprocess
import time

import pytest

NAMESPACE = "astronomer"

# The placeholder the chart writes into a bootstrap Secret so a file-mode consumer cannot
# latch a pre-bootstrap value. Finding it in a log means the wait-for-secret gate let a
# process start against the placeholder -- one grep covering the whole race family.
SENTINEL = "__ASTRONOMER_NOT_BOOTSTRAPPED__"

# Carried by every value bin/setup-secrets-from-files-fixtures.py creates, so one grep can
# assert no fixture secret reached a process environment.
FIXTURE_MARKER = "sff-not-a-real-secret"

SECRETS_DIR = "/etc/astronomer/secrets"

# Gate env var -> which loader it turns on. A container carrying one of these set to
# "true" is a container the loader runs in.
LOADER_GATES = {
    "HOUSTON_SECRETS_FROM_FILES": "houston",
    "COMMANDER_SECRETS_FROM_FILES": "commander",
    "KUIPER_SECRETS_FROM_FILES": "kuiper",
}

# "Done. Loaded 4 secret(s) from files." -- the shape houston and commander both log.
LOADED_COUNT = re.compile(r"Done\. Loaded (\d+) secret\(s\) from files")

# Containers that carry <VAR>_FILE paths they deliberately do not mount. They include the
# houston_environment helper, so they inherit the gate flag and every path, but get no
# secret volume. Safe only because they run the pure-shell /houston/bin/entrypoint and
# never invoke node, so the loader never runs -- the same exemption, for the same stated
# reason, as CONTAINERS_EXEMPT_FROM_FILE_PATH_MOUNTS in
# tests/chart_tests/test_secrets_from_files.py.
SHELL_ONLY_CONTAINERS = {"houston-wait-for-db", "wait-for-db"}

# ap-db-bootstrapper init containers. They are expected to restart on a FRESH install and
# are not part of this feature: BOOTSTRAP_DB is the one path deliberately left on
# valueFrom.secretKeyRef, blocked on that external image gaining file support.
#
# They race each other. The houston Deployment's bootstrapper and the db-migrations Job's
# bootstrapper both run CREATE DATABASE astronomer_houston, and the loser dies with
# `duplicate key value violates unique constraint "pg_database_datname_index"`. It is
# self-healing -- the next attempt sees the database already there -- so it costs a restart
# and nothing else. Excluded from the restart and event assertions so those stay strict
# about the containers this feature actually changed.
EXTERNAL_BOOTSTRAPPER_CONTAINERS = {
    "houston-bootstrapper",
    "flightdeck-bootstrapper",
    "bootstrapper",
}

# Cronjobs excluded from the Stage 3 sweep, with the reason each is excluded.
CRONJOB_EXCLUSIONS = {
    # Hangs after completing its work, on the PUBLISHED ap-houston-api:2.2.0 as well as the
    # overlay -- verified by running `yarn cleanup-deploy-revisions` in both against the same
    # database: it logs "deleting many deployRevision ..." and then never exits (exit 124
    # under `timeout`). The script has no process.exit() and imports
    # resolvers/mutation/cleanup-deploy-revisions, which pulls in a graph that opens handles
    # and keeps the event loop alive. Its file differs from v2.2.0 by the loader import
    # alone, and the published image has no loader at all, so this is upstream and not ours.
    "astronomer-houston-cleanup-deploy-revisions": "pre-existing upstream hang, reproduced on the published image",
}

# Events that mean a pod never got as far as running the thing under test. Converting a
# secretKeyRef into a volume upgrades a per-container failure into a whole-pod FailedMount,
# which is precisely the class this feature introduced.
FATAL_EVENT_REASONS = {
    "FailedMount",
    "CreateContainerConfigError",
    "CreateContainerError",
    "StartError",
    "ErrImageNeverPull",
    "ErrImagePull",
    "ImagePullBackOff",
    "BackOff",
}


# --------------------------------------------------------------------------- helpers


def _kubectl(kubeconfig, *args, check=False):
    """Run kubectl against the scenario cluster. Never inherits the ambient context."""
    result = subprocess.run(
        ["kubectl", f"--kubeconfig={kubeconfig}", f"--namespace={NAMESPACE}", *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"kubectl {' '.join(args)} failed: {result.stderr}")
    return result


def _env_of(container):
    """name -> literal value for a container's plain (non-valueFrom) env entries."""
    return {e.name: e.value for e in (container.env or []) if e.value is not None}


def _mount_paths(container):
    return [m.mount_path.rstrip("/") for m in (container.volume_mounts or [])]


def _advertised_file_vars(container):
    """<VAR>_FILE entries whose path sits inside a volume this container mounts.

    Only these can be loaded. A path with no mount behind it is either the known
    shell-only exemption or a bug, and in neither case will the loader have read it.
    """
    mounts = _mount_paths(container)
    return {
        name: value
        for name, value in _env_of(container).items()
        if name.endswith("_FILE") and value and any(value == m or value.startswith(m + "/") for m in mounts)
    }


def _running_container_names(pod):
    """Names of this pod's containers that are running RIGHT NOW.

    `kubectl exec` needs a live process: a Succeeded pod, or an init container that has
    already terminated, cannot be exec'd into ("cannot exec into a container in a completed
    pod"). Log-based assertions still work on those, so the two kinds of check have to be
    scoped differently rather than assuming every gated container is reachable.
    """
    statuses = (pod.status.container_statuses or []) + (pod.status.init_container_statuses or [])
    return {s.name for s in statuses if s.state and s.state.running}


def _loader_containers(k8s_core_v1_client, running_only=False):
    """(pod_name, container, loader) for every container the loader actually runs in.

    With running_only, restricted to containers that can currently be exec'd into.
    """
    found = []
    for pod in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items:
        if pod.status.phase not in ("Running", "Succeeded"):
            continue
        live = _running_container_names(pod)
        containers = list(pod.spec.containers or []) + list(pod.spec.init_containers or [])
        for container in containers:
            env = _env_of(container)
            for gate, loader in LOADER_GATES.items():
                if str(env.get(gate, "")).lower() == "true":
                    if container.name in SHELL_ONLY_CONTAINERS:
                        continue  # inherits the gate but never runs the loader
                    if running_only and container.name not in live:
                        continue
                    found.append((pod.metadata.name, container, loader))
                    break
    return found


def _await_jobs(batch_v1_client, created, timeout):
    """Wait for each fired Job to settle. cronjob name -> (outcome, job name).

    Under emulation these take minutes, so the wait is generous; anything still pending at
    the deadline is reported as "timed out" rather than silently treated as a pass.
    """
    deadline = time.time() + timeout
    pending = dict(created)
    outcomes = {}
    while pending and time.time() < deadline:
        for cronjob, job in list(pending.items()):
            status = batch_v1_client.read_namespaced_job_status(job, NAMESPACE).status
            if status.succeeded:
                outcomes[cronjob] = ("succeeded", job)
                del pending[cronjob]
            elif status.failed:
                outcomes[cronjob] = ("failed", job)
                del pending[cronjob]
        if pending:
            time.sleep(10)
    for cronjob, job in pending.items():
        outcomes[cronjob] = ("timed out", job)
    return outcomes


def _gated_cronjob_names(batch_v1_client):
    """Names of cronjobs whose containers carry a loader gate.

    The namespace also holds cronjobs belonging to other components (config-syncer), which
    never load secrets from files. Including them would fail a "logged no Loaded N secret(s)"
    assertion for the uninteresting reason that they have no loader at all.
    """
    gated = []
    for cronjob in batch_v1_client.list_namespaced_cron_job(NAMESPACE).items:
        pod = cronjob.spec.job_template.spec.template.spec
        containers = list(pod.containers or []) + list(pod.init_containers or [])
        if any(str(_env_of(container).get(gate, "")).lower() == "true" for container in containers for gate in LOADER_GATES):
            gated.append(cronjob.metadata.name)
    return gated


def _logs(kubeconfig, pod, container):
    result = _kubectl(kubeconfig, "logs", pod, "-c", container, "--tail=-1")
    return result.stdout if result.returncode == 0 else ""


def _exec(kubeconfig, pod, container, *argv):
    return subprocess.run(
        [
            "kubectl",
            f"--kubeconfig={kubeconfig}",
            f"--namespace={NAMESPACE}",
            "exec",
            pod,
            "-c",
            container,
            "--",
            *argv,
        ],
        capture_output=True,
        text=True,
    )


# --------------------------------------------------------------------------- Stage 1


def test_no_container_restarted(k8s_core_v1_client):
    """A restart is how a fail-closed loader manifests: it exits non-zero and comes back.

    Covers init containers too, where the wait-for-secret gate and the bootstrappers live.
    """
    offenders = []
    for pod in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items:
        statuses = (pod.status.container_statuses or []) + (pod.status.init_container_statuses or [])
        offenders += [
            f"{pod.metadata.name}/{s.name} restarted {s.restart_count}x"
            for s in statuses
            if s.restart_count and s.name not in EXTERNAL_BOOTSTRAPPER_CONTAINERS
        ]
    assert offenders == [], "\n".join(offenders)


def test_no_fatal_pod_events(k8s_core_v1_client):
    """FailedMount and friends mean the pod never ran, so nothing below would be meaningful."""
    events = k8s_core_v1_client.list_namespaced_event(NAMESPACE).items
    offenders = [
        f"{e.involved_object.name}: {e.reason}: {e.message}"
        for e in events
        if e.reason in FATAL_EVENT_REASONS and not any(name in (e.message or "") for name in EXTERNAL_BOOTSTRAPPER_CONTAINERS)
    ]
    assert offenders == [], "\n".join(offenders)


def test_sentinel_appears_in_no_container_log(kubeconfig_file, k8s_core_v1_client):
    """The single highest-value assertion: one grep over the whole wait-for-secret race family.

    A volume is projected once before any container starts, so without the gate a
    file-mode consumer can read the pre-bootstrap placeholder and run with it. Seeing the
    sentinel in any log means that happened.
    """
    offenders = []
    for pod in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items:
        containers = [c.name for c in (pod.spec.containers or [])] + [c.name for c in (pod.spec.init_containers or [])]
        offenders.extend(
            f"{pod.metadata.name}/{container}"
            for container in containers
            if SENTINEL in _logs(kubeconfig_file, pod.metadata.name, container)
        )
    assert offenders == [], (
        "the bootstrap sentinel reached these containers' logs, so something started "
        "against the placeholder rather than waiting for the real value:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("secret_name", ["astronomer-houston-backend", "astronomer-flightdeck-backend"])
def test_bootstrap_secret_no_longer_holds_the_sentinel(k8s_core_v1_client, secret_name):
    """Both bootstrap Secrets must have been rewritten with a real DSN by their bootstrapper.

    These are the two Secrets the `lookup` helper re-emits on every render; if one still
    holds the sentinel, the gate is the only thing standing between the platform and a
    placeholder DSN, and the test above is load-bearing rather than belt-and-braces.
    """
    import base64

    secret = k8s_core_v1_client.read_namespaced_secret(secret_name, NAMESPACE)
    value = base64.b64decode(secret.data["connection"]).decode()
    assert SENTINEL not in value, f"{secret_name} still holds the bootstrap sentinel"
    assert value.startswith("postgres"), f"{secret_name} holds an unexpected value shape"


def test_no_converted_secret_arrives_via_secret_key_ref(k8s_core_v1_client):
    """The point of the feature: converted values are gone from the pod's environment block.

    Asserted against LIVE pod specs rather than a render, so it also catches a pod left
    over from a previous configuration. BOOTSTRAP_DB is excluded deliberately: its
    conversion is blocked on the external ap-db-bootstrapper image and is a disclosed
    residual, not a regression.
    """
    deferred = {"BOOTSTRAP_DB"}
    offenders = []
    for pod in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items:
        containers = list(pod.spec.containers or []) + list(pod.spec.init_containers or [])
        for container in containers:
            for env in container.env or []:
                if env.name in deferred:
                    continue
                ref = getattr(env.value_from, "secret_key_ref", None) if env.value_from else None
                if ref and f"{env.name}_FILE" in _env_of(container):
                    offenders.append(
                        f"{pod.metadata.name}/{container.name} {env.name} arrives via "
                        f"secretKeyRef({ref.name}/{ref.key}) AND advertises {env.name}_FILE"
                    )
    assert offenders == [], "\n".join(offenders)


# --------------------------------------------------------------------------- Stage 2


def test_loader_ran_in_every_gated_container(k8s_core_v1_client):
    """Guards against the values overlay silently enabling nothing.

    If this count collapses, every other assertion here passes vacuously -- which is how
    the previous attempt's values file shipped covering about half of what it claimed.
    """
    by_loader = {}
    for _pod, _container, loader in _loader_containers(k8s_core_v1_client):
        by_loader[loader] = by_loader.get(loader, 0) + 1
    assert by_loader.get("houston", 0) >= 5, by_loader
    assert by_loader.get("commander", 0) >= 3, by_loader
    assert by_loader.get("kuiper", 0) == 1, by_loader


def test_loaded_count_matches_advertised_files(kubeconfig_file, k8s_core_v1_client):
    """The silent-success detector, and the reason this scenario exists.

    "Loaded 3 secret(s)" while four files are mounted means one was skipped -- an empty
    file, or a var the loader's list does not know about -- and the process started anyway
    with that secret unset. It will fail later, somewhere unrelated.

    kuiper is excluded: its info-level log is suppressed before any handler is installed
    (see the module docstring), so there is no count to compare. test_kuiper_* proves it
    behaviourally instead.
    """
    mismatches = []
    checked = 0
    for pod, container, loader in _loader_containers(k8s_core_v1_client, running_only=True):
        if loader == "kuiper":
            continue
        advertised = _advertised_file_vars(container)
        if not advertised:
            continue

        # Compare against the files actually MOUNTED, not the number of <VAR>_FILE env
        # vars. Those legitimately differ: the loader reads `<VAR>_FILE` when set and
        # otherwise probes the default path, so a projected file the chart did not also
        # advertise via _FILE is still loaded. commander's flightdeck-db-migrations is
        # exactly that -- one _FILE var, two projected files, two loaded. Counting env
        # vars calls that a mismatch; counting files is what "did it read everything it
        # was handed" actually means.
        mounted = set()
        for directory in {value.rsplit("/", 1)[0] for value in advertised.values()}:
            listing = _exec(kubeconfig_file, pod, container.name, "ls", "-1", directory)
            if listing.returncode != 0:
                mismatches.append(f"{pod}/{container.name}: cannot list {directory}")
                continue
            mounted |= {line.strip() for line in listing.stdout.splitlines() if line.strip()}

        logs = _logs(kubeconfig_file, pod, container.name)
        match = LOADED_COUNT.search(logs)
        if not match:
            mismatches.append(
                f"{pod}/{container.name} ({loader}) mounts {len(mounted)} secret file(s) "
                f"{sorted(mounted)} but logged no 'Done. Loaded N secret(s)' line at all"
            )
            continue
        checked += 1
        loaded = int(match.group(1))
        if loaded != len(mounted):
            mismatches.append(f"{pod}/{container.name} ({loader}) loaded {loaded} but mounts {len(mounted)}: {sorted(mounted)}")
    assert mismatches == [], "\n".join(mismatches)
    # Floor rather than an exact count: this sweep needs `kubectl exec` to list the mounted
    # directory, so it only sees containers running at that moment. The stable set is the
    # six long-running loader deployments -- houston, houston-worker, navigator, dp-link,
    # commander, pilot. The Job and cronjob containers load secrets too but have terminated
    # by the time this runs, and are covered by the log-based Stage 3 sweep instead.
    assert checked >= 6, f"only {checked} containers compared; expected the sweep to be broader"


def test_no_fixture_secret_value_appears_in_any_environ(kubeconfig_file, k8s_core_v1_client):
    """The security property, measured at the process rather than in the pod spec.

    /proc/1/environ is what `kubectl exec -- env`, a crash handler, or an APM agent would
    capture. Every fixture value carries one marker, so a single grep covers them all.

    Scoped to containers the loader runs in plus the esproxy, which are the containers
    whose secrets this feature moved. Exec is best-effort per container: a container
    without `cat` is reported, not silently skipped, so the sweep cannot quietly shrink.

    awsproxy is deliberately NOT in scope, and that is a real exemption rather than an
    oversight. aws-es-proxy takes its credentials from the AWS SDK's default chain, which
    means the environment, so the chart's shell preamble does
    `export AWS_ACCESS_KEY_ID="$(cat .../aws_access_key)"` before exec'ing it. The value is
    therefore in that one container's environ BY DESIGN -- the file is only the delivery
    mechanism, and what this feature removed there is the secretKeyRef in the pod spec, not
    the variable in the process. The security review discloses this explicitly.
    test_awsproxy_keys_are_absent_from_the_pod_spec asserts the property that does hold.
    """
    unreadable, leaked = [], []
    targets = [(pod, c.name) for pod, c, _ in _loader_containers(k8s_core_v1_client, running_only=True)]
    targets.extend(
        (pod.metadata.name, container.name)
        for pod in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items
        for container in pod.spec.containers or []
        if container.name == "external-es-proxy"
    )

    for pod, container in targets:
        result = _exec(kubeconfig_file, pod, container, "cat", "/proc/1/environ")
        if result.returncode != 0:
            unreadable.append(f"{pod}/{container}: {result.stderr.strip()[:120]}")
            continue
        environ = result.stdout.replace("\x00", "\n")
        if FIXTURE_MARKER in environ:
            hits = [line.split("=")[0] for line in environ.splitlines() if FIXTURE_MARKER in line]
            leaked.append(f"{pod}/{container}: {hits}")

    assert leaked == [], (
        "these containers carry a fixture secret VALUE in their process environment, "
        "which is exactly what this feature removes:\n" + "\n".join(leaked)
    )
    assert unreadable == [], (
        "could not read /proc/1/environ in these containers, so the sweep above did not "
        "actually cover them:\n" + "\n".join(unreadable)
    )


def test_awsproxy_keys_are_absent_from_the_pod_spec(k8s_core_v1_client):
    """The property that DOES hold for awsproxy, since the environ one cannot.

    aws-es-proxy reads credentials from the AWS SDK default chain, so the chart's shell
    preamble has to put them in its environment -- see the exemption in the test above.
    What the conversion actually achieves there is narrower but still real: the keys stop
    being `valueFrom.secretKeyRef` entries in the pod spec, so they are no longer visible
    to anyone with `get pod`, and no longer resolved by the kubelet into the spec's
    environment block. They arrive as a file the preamble reads instead.

    Asserting this separately keeps the exemption honest: dropping awsproxy from the
    environ sweep could otherwise hide a regression where the secretKeyRef came back.
    """
    checked = 0
    for pod in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items:
        for container in pod.spec.containers or []:
            if container.name != "awsproxy":
                continue
            checked += 1
            names_from_refs = [
                env.name for env in container.env or [] if env.value_from and getattr(env.value_from, "secret_key_ref", None)
            ]
            assert names_from_refs == [], (
                f"{pod.metadata.name}/awsproxy still takes {names_from_refs} from a "
                "secretKeyRef; the conversion should deliver them as mounted files"
            )
            mounts = [m.mount_path for m in container.volume_mounts or []]
            assert SECRETS_DIR in mounts, (
                f"{pod.metadata.name}/awsproxy does not mount {SECRETS_DIR}, so the shell preamble has no file to cat: {mounts}"
            )
    assert checked == 1, f"expected exactly one awsproxy container, found {checked}"


def test_file_paths_are_present_in_environ(kubeconfig_file, k8s_core_v1_client):
    """Positive control for the sweep above.

    Without this, a broken exec or an empty environ would make the "no secret values"
    assertion pass for the wrong reason. The _FILE *names* must be present even though the
    values must not.
    """
    missing = []
    for pod, container, _loader in _loader_containers(k8s_core_v1_client, running_only=True):
        advertised = _advertised_file_vars(container)
        if not advertised:
            continue
        result = _exec(kubeconfig_file, pod, container.name, "cat", "/proc/1/environ")
        if result.returncode != 0:
            continue  # reported by the test above; do not double-fail
        environ = result.stdout.replace("\x00", "\n")
        absent = sorted(name for name in advertised if f"{name}=" not in environ)
        if absent:
            missing.append(f"{pod}/{container.name}: {absent}")
    assert missing == [], "\n".join(missing)


def test_houston_db_migrations_job_succeeded(k8s_core_v1_client):
    """Deterministic proof that houston USED its file-loaded DSN, not merely that it loaded.

    `yarn migrate` connects to the database and applies migrations. It cannot succeed
    without a working DATABASE_URL, and with the feature on the only source of that value
    is the mounted file -- the chart dropped the secretKeyRef. A point-in-time check of
    pg_stat_activity was tried instead and proved flaky under sampling; this is the same
    evidence without the race.

    This job is also the one that exercised the migrate-deploy `--extensions .js` defect,
    where babel-node could not resolve the .ts loader and `yarn migrate` died outright.
    """
    from kubernetes import client as k8s_client

    batch = k8s_client.BatchV1Api(k8s_core_v1_client.api_client)
    jobs = [j for j in batch.list_namespaced_job(NAMESPACE).items if "db-migrations" in j.metadata.name]
    assert jobs, "no houston db-migrations Job found; it is this stage's only deterministic proof"
    for job in jobs:
        assert job.status.succeeded, (
            f"{job.metadata.name} did not succeed: succeeded={job.status.succeeded} failed={job.status.failed}"
        )


def test_kuiper_parsed_its_file_loaded_database_url(kubeconfig_file, k8s_core_v1_client):
    """Behavioural proof for the one loader whose success log is unobservable.

    kuiper's "Loaded N secret(s)" is logger.info, emitted before any handler is installed,
    so WARNING-level root logging swallows it (see the module docstring). What IS
    observable is the consequence: app/database.py derives the database name from
    settings.database_url at import time, so a populated settings object means the loader
    ran before pydantic snapshotted the environment -- the one ordering constraint that
    cannot be recovered from if it is wrong.
    """
    pods = [
        p
        for p in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items
        if any(c.name == "filesd-reloader" for c in (p.spec.containers or []))
    ]
    assert pods, "no pod carrying the filesd-reloader sidecar"
    pod = pods[0].metadata.name

    # The var must be absent from the environment block (the chart dropped the
    # secretKeyRef) yet present inside the process -- which can only happen via the file.
    result = _exec(kubeconfig_file, pod, "filesd-reloader", "cat", "/proc/1/environ")
    assert result.returncode == 0, result.stderr
    environ = result.stdout.replace("\x00", "\n")
    assert "DATABASE_URL_FILE=" in environ, "filesd-reloader does not advertise a file path"

    probe = _exec(
        kubeconfig_file,
        pod,
        "filesd-reloader",
        "python",
        "-c",
        "from app.core.config import settings; "
        "print('DSN_OK' if (settings.database_url or '').startswith('postgres') else 'DSN_MISSING')",
    )
    assert probe.returncode == 0, f"{probe.stdout}\n{probe.stderr}"
    assert "DSN_OK" in probe.stdout, (
        "settings.database_url was not populated from the mounted file, so the loader ran "
        f"after pydantic snapshotted the environment: {probe.stdout} {probe.stderr}"
    )


# --------------------------------------------------------------------------- Stage 3


def test_every_cronjob_loads_its_secrets_from_files(kubeconfig_file, k8s_core_v1_client):
    """Each cronjob is its own node process, so each resolves the loader independently.

    Most of the houston workloads in this release are cronjobs. They run on a schedule, so
    a resolution failure in one surfaces days later and nowhere near the cause -- which is
    exactly how the bare-specifier bug would have escaped. Firing all of them now, as real
    Jobs, is the only way to see it.
    """
    from kubernetes import client as k8s_client

    batch = k8s_client.BatchV1Api(k8s_core_v1_client.api_client)
    # Only cronjobs whose containers carry a loader gate. The namespace also holds
    # cronjobs from other components (config-syncer), which never load secrets from files
    # and would fail a "logged no Loaded N" check for the uninteresting reason that they
    # have no loader at all.
    gated = _gated_cronjob_names(batch)
    cronjobs = [name for name in gated if name not in CRONJOB_EXCLUSIONS]
    skipped = sorted(set(gated) & set(CRONJOB_EXCLUSIONS))
    assert len(gated) >= 9, f"expected at least 9 loader-bearing cronjobs, found {len(gated)}: {gated}"
    for name in skipped:
        print(f"SKIPPING {name}: {CRONJOB_EXCLUSIONS[name]}")

    created = {}
    for cronjob in cronjobs:
        job = f"sff-{cronjob}"[:63]
        _kubectl(kubeconfig_file, "delete", "job", job, "--ignore-not-found")
        result = _kubectl(kubeconfig_file, "create", "job", job, f"--from=cronjob/{cronjob}")
        assert result.returncode == 0, f"could not fire {cronjob}: {result.stderr}"
        created[cronjob] = job

    outcomes = _await_jobs(batch, created, timeout=900)

    problems = []
    for cronjob, (outcome, job) in sorted(outcomes.items()):
        pods = k8s_core_v1_client.list_namespaced_pod(NAMESPACE, label_selector=f"job-name={job}").items
        logs = "".join(
            _logs(kubeconfig_file, pod.metadata.name, container.name) for pod in pods for container in pod.spec.containers or []
        )

        match = LOADED_COUNT.search(logs)
        loaded = int(match.group(1)) if match else None
        if outcome != "succeeded":
            problems.append(f"{cronjob}: job {outcome}")
        elif loaded is None:
            problems.append(f"{cronjob}: succeeded but logged no 'Loaded N secret(s)' line")
        elif loaded < 1:
            problems.append(f"{cronjob}: loaded {loaded} secrets from files")
        elif SENTINEL in logs:
            problems.append(f"{cronjob}: sentinel present in logs")

    for cronjob, job in created.items():
        _kubectl(kubeconfig_file, "delete", "job", job, "--ignore-not-found")

    assert problems == [], "\n".join(problems)


# --------------------------------------------------------------------------- Stage 4


def test_secret_file_is_0440_root_owned_and_readable_via_fsgroup(kubeconfig_file, k8s_core_v1_client):
    """The 0440 + fsGroup pairing, which both design docs say was never checked on a pod.

    Kubernetes projects secret files root-owned. 0440 is stricter than the 0644 default
    (no world read inside the container), but it only leaves the file readable because
    fsGroup puts the non-root process in the owning group. Mode and fsGroup are a pair:
    0440 without fsGroup is unreadable, and getting that wrong hits the loader's FATAL
    branch, not a warning.

    stat must follow the symlink. Kubernetes writes the real file into a timestamped
    directory, points ..data at it, and symlinks each key to ..data/<key>; those symlinks
    are always 0777, so an lstat here would read the link's mode and prove nothing.
    """
    pods = [
        p
        for p in k8s_core_v1_client.list_namespaced_pod(NAMESPACE).items
        if any(c.name == "houston" for c in (p.spec.containers or [])) and p.status.phase == "Running"
    ]
    assert pods, "no running houston pod"
    pod = pods[0]
    assert pod.spec.security_context.fs_group, (
        "the houston pod sets no fsGroup, so a 0440 root-owned secret file would be unreadable and the loader would fail closed"
    )
    fs_group = pod.spec.security_context.fs_group
    name = pod.metadata.name

    probe = _exec(
        kubeconfig_file,
        name,
        "houston",
        "sh",
        "-c",
        f"stat -L -c '%a %U %G' {SECRETS_DIR}/DATABASE_URL; id -G; head -c1 {SECRETS_DIR}/DATABASE_URL >/dev/null && echo READABLE",
    )
    assert probe.returncode == 0, f"{probe.stdout}\n{probe.stderr}"
    lines = probe.stdout.split("\n")
    mode_owner, groups = lines[0].split(), lines[1].split()

    assert mode_owner[0] == "440", f"expected mode 440, got {mode_owner[0]} ({mode_owner})"
    assert mode_owner[1] == "root", f"expected a root-owned file, got {mode_owner[1]}"
    assert str(fs_group) in groups, (
        f"fsGroup {fs_group} is not among the process's supplementary groups {groups}, "
        "so group-read on the secret file cannot be what makes it readable"
    )
    assert "READABLE" in probe.stdout, "the 0440 secret file is not readable by the process"


def test_cronjobs_reading_a_bootstrapped_secret_are_still_ungated(k8s_core_v1_client):
    """KNOWN GAP: the ungated-cronjob window, which bit on a plain install, not only ArgoCD.

    A secret volume is projected ONCE before any container starts, so a file-mode consumer
    can read whatever the Secret held at that moment. The chart therefore seeds each
    bootstrap Secret with a sentinel and puts a wait-for-secret init container on the
    workloads that read it, which polls until the bootstrapper replaces it.

    That gate is on eight workloads and on none of the nine cronjobs. Observed here: the
    Secret was written at 15:59:22 (sentinel) and rewritten at 16:00:06 (bootstrapper),
    and the sync-dataplane-clusters cronjob started at 16:00:00 -- six seconds inside the
    window. Its loader dutifully loaded the sentinel (correct: the sentinel is non-empty,
    so skipping it is explicitly the gate's job, not the loader's) and Prisma then rejected
    `__ASTRONOMER_NOT_BOOTSTRAPPED__` with "the URL must start with the protocol
    postgresql://". The job failed.

    The design docs anticipate this only for ArgoCD, where PreSync re-applies the sentinel
    on every sync. It is really a property of any install whose cron schedule lands in the
    bootstrap window, and the failure is at least loud -- the Job fails and the next
    scheduled run succeeds -- rather than silent.

    Note the sentinel-in-logs assertion above cannot catch this: the loader logs variable
    names and never values, and Prisma's error does not echo the URL. That is why this
    structural check exists separately.
    """
    from kubernetes import client as k8s_client

    batch = k8s_client.BatchV1Api(k8s_core_v1_client.api_client)
    gated = set(_gated_cronjob_names(batch))
    ungated = [
        cronjob.metadata.name
        for cronjob in batch.list_namespaced_cron_job(NAMESPACE).items
        if cronjob.metadata.name in gated
        and not any(c.name == "wait-for-secret" for c in cronjob.spec.job_template.spec.template.spec.init_containers or [])
    ]

    # Asserted as a KNOWN GAP rather than as the desired behaviour, following the same
    # pattern as the chart suite's test_the_known_dangling_mount_still_dangles: pin the
    # defect so it stays visible, and fail the moment it is fixed so this exception cannot
    # outlive it. Flip this to `assert ungated == []` when the gate is added.
    assert sorted(ungated) == sorted(gated), (
        "the set of ungated cronjobs changed. If the wait-for-secret gate was added to "
        "some or all of them, this test has done its job -- replace it with "
        "`assert ungated == []`.\n"
        f"  gated-by-loader: {sorted(gated)}\n"
        f"  still ungated:   {sorted(ungated)}"
    )
    assert len(ungated) >= 9, f"expected at least 9 loader-bearing cronjobs to demonstrate the gap, found {len(ungated)}"
