#!/usr/bin/env python3
"""
POC: install the Laminar hypervisor onto an APC data plane created by `bin/setup-cp-dp-k3d.py`.

This is an investigation tool for the "Laminar Hypervisor Integration for APC" design work
(Linear project "Laminar integration (L)"). It is NOT a supported install path, and nothing
here is a proposal for how the astronomer chart should eventually ship Laminar — it exists to
let us run the real thing against a real APC data plane and find out what breaks.

What it does, against a data-plane context you name explicitly:

  install-laminar
    - installs KEDA (the astronomer chart does not ship it; worker-queue autoscaling needs it)
    - builds the laminar image from a local checkout of github.com/astronomer/laminar and
      imports it straight into the k3d cluster (no registry, no ACR token to expire)
    - creates the `laminar` namespace
    - creates Laminar's own database on the data plane's postgres, plus the `laminar-connection`
      secret it reads via LAMINAR_DATABASE_URL
    - renders the laminar manifests (base + hypervisor, optionally apiserver) and applies them

  attach-deployment --release-name <r>
    - copies the deployment's Airflow metadata-DB connection secret into the `laminar`
      namespace under the name and key Laminar actually reads
    - stamps the Astro identity labels Laminar requires (see below)
    - annotates the Airflow CR so the hypervisor will act on it

VERIFIED GAP (2026-08-17, on a real APC data plane): CRD-watch discovery alone is NOT enough.
Laminar ignores any Airflow CR missing ALL THREE of astronomer.io/deploymentId, /workspaceId
and /organizationId. APC's CR carries only deploymentId — the workspace id is under a bare
`workspace` key, and APC has no Organization entity at all. Symptom: the watcher logs
"Could not find Astro IDs on Airflow CR" and num_airflows stays 0 forever.

Why `attach-deployment` is a separate action: it is the exact step the design doc assigns to
Commander (decision D4). Running it by hand, per deployment, is the point — it shows what
Houston/Commander do not do today.

Contracts this tool depends on (read out of astronomer/laminar at v2026.08.10, verify before
trusting on a newer tag):

  - Laminar's own DB:     env LAMINAR_DATABASE_URL <- secret `laminar-connection` key
                          `connection-string`  (manifests/hypervisor/deployment.yaml)
  - Per-deployment DB:    secret `<airflow-cr-name>-db` key `connection`, in Laminar's own
                          namespace  (src/laminar/common/models/deployment.py, `dsn` property)
  - APC side:             commander writes `<releaseName>-active-metadata` key `connection`
                          into the deployment namespace
                          (commander provisioner/kubernetes/kubernetes.go, NewAirflowSecretRef)
  - Act-on-deployment:    annotations `astronomer.io/enable-scaling` and
                          `astronomer.io/hibernation-spec` on the Airflow CR
                          (astro apps/harmony/plugins/airflows/types/types.go)

Prerequisites: a data plane from `bin/setup-cp-dp-k3d.py --enable-operator`, a checkout of
astronomer/laminar, and docker (with buildx) / kubectl / k3d / kustomize / git / gh on PATH.

The image build needs a GitHub token, because laminar's Dockerfile sets
GOPRIVATE=github.com/astronomer and fetches private Go modules. It is taken from $GH_TOKEN, or
`gh auth token` — the same order laminar's own Justfile uses. Without one the build fails at
`go mod download` with "could not read Username for 'https://github.com'".

Examples:

  # install onto the dp01 data plane
  uv run bin/setup-laminar-poc.py install-laminar \\
      --context k3d-dp01 --platform-namespace astronomer --laminar-repo ~/codebase/laminar

  # wire one operator-mode deployment up to it
  uv run bin/setup-laminar-poc.py attach-deployment \\
      --context k3d-dp01 --release-name pretty-cosmos-1234 --deployment-namespace pretty-cosmos-1234
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import tempfile
from pathlib import Path

from k3d_setup_shared import (
    CommandError,
    Milestones,
    _print,
    _require_executable,
    _run,
)

# KEDA 2.14.0 matches what laminar's own script/k3d-install-prerequisites pins, so the POC
# reproduces the combination Laminar is developed against rather than inventing a new one.
KEDA_VERSION = "2.14.0"
KEDA_MANIFEST_URL = f"https://github.com/kedacore/keda/releases/download/v{KEDA_VERSION}/keda-{KEDA_VERSION}.yaml"

LAMINAR_NAMESPACE = "laminar"
LAMINAR_IMAGE = "laminar:apc-poc"

# Matches laminar's Justfile LAMINAR_VERSION. The Dockerfile requires the build arg.
LAMINAR_VERSION = "0.1.0"

# Laminar's Dockerfile pins its base images by amd64-only digests, so an arm64 build emits
# InvalidBaseImagePlatform warnings and produces a mixed image. Build amd64 explicitly, as
# laminar's own release path does (`just docker-build-amd64`); it runs emulated on Apple silicon.
DEFAULT_BUILD_PLATFORM = "linux/amd64"

# Laminar's own database, provisioned in Astro by the external-db-operator via the `Scheme` CR in
# manifests/base. We do not run that operator here, so we create the database directly and drop
# the Scheme from the render — the same thing the `astro` overlay does with drop-scheme.yaml.
LAMINAR_DB_NAME = "laminar"
LAMINAR_DB_SECRET = "laminar-connection"  # noqa: S105 — k8s object name, not a credential
LAMINAR_DB_SECRET_KEY = "connection-string"  # noqa: S105 — secret data key, not a credential

# Where Laminar looks for each Airflow deployment's metadata DB, and where commander puts it.
LAMINAR_DEPLOYMENT_DB_SECRET_KEY = "connection"  # noqa: S105 — secret data key, not a credential
COMMANDER_METADATA_SECRET_SUFFIX = "-active-metadata"  # noqa: S105 — k8s name suffix, not a credential

ENABLE_SCALING_ANNOTATION = "astronomer.io/enable-scaling"
HIBERNATION_SPEC_ANNOTATION = "astronomer.io/hibernation-spec"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="action", required=True)

    install = sub.add_parser("install-laminar", help="Install KEDA + Laminar onto a data plane.")
    install.add_argument(
        "--context",
        required=True,
        help="kubectl context of the DATA PLANE to install into (e.g. k3d-dp01). No default, on purpose.",
    )
    install.add_argument(
        "--laminar-repo",
        required=True,
        help="Path to a local checkout of github.com/astronomer/laminar. The image is built from here.",
    )
    install.add_argument(
        "--platform-namespace",
        required=True,
        help="Namespace of the astronomer platform release on the data plane (e.g. astronomer).",
    )
    install.add_argument(
        "--release-name",
        default="astronomer",
        help="Helm release name of the astronomer platform, used to find its postgres. Default: astronomer.",
    )
    install.add_argument(
        "--components",
        choices=["hypervisor", "both"],
        default="hypervisor",
        help=(
            "Which Laminar components to install. 'hypervisor' matches the design doc's P1 scope "
            "(api-server descoped); 'both' also installs the api-server. Default: hypervisor."
        ),
    )
    install.add_argument("--image", default=LAMINAR_IMAGE, help=f"Image tag to build. Default: {LAMINAR_IMAGE}")
    install.add_argument(
        "--platform",
        default=DEFAULT_BUILD_PLATFORM,
        help=(
            "Build platform. Default: "
            f"{DEFAULT_BUILD_PLATFORM}, because laminar's Dockerfile pins amd64-only base image "
            "digests. On Apple silicon the image runs under emulation."
        ),
    )
    install.add_argument(
        "--postgres-dsn",
        default="",
        help=(
            "Direct postgres superuser DSN for Laminar's own database. Defaults to reading the "
            "`astronomer-bootstrap` secret, which is right unless pgbouncer is enabled."
        ),
    )
    install.add_argument("--skip-keda", action="store_true", help="Skip the KEDA install.")
    install.add_argument("--skip-image-build", action="store_true", help="Reuse an image already in the cluster.")
    install.add_argument(
        "--enable-healers",
        action="store_true",
        help="Turn Laminar's healers on. Off by default, matching the design doc's P1 decision.",
    )

    attach = sub.add_parser(
        "attach-deployment",
        help="Give Laminar access to one deployment's metadata DB and let it act on the CR.",
    )
    attach.add_argument("--context", required=True, help="kubectl context of the DATA PLANE. No default, on purpose.")
    attach.add_argument("--release-name", required=True, help="Deployment release name (also the Airflow CR name).")
    attach.add_argument(
        "--deployment-namespace",
        required=True,
        help="Namespace the deployment runs in. No default, on purpose.",
    )
    attach.add_argument(
        "--workspace-id",
        default="",
        help="Value for astronomer.io/workspaceId. Defaults to the CR's existing `workspace` label.",
    )
    attach.add_argument(
        "--organization-id",
        default="",
        help=(
            "Value for astronomer.io/organizationId. APC has no Organization entity, so this is "
            "synthesized: defaults to the CR's `clusterid` label, else 'apc-no-organization'."
        ),
    )
    attach.add_argument(
        "--no-astro-id-labels",
        action="store_true",
        help="Skip stamping the Astro identity labels (Laminar will then ignore the deployment).",
    )
    attach.add_argument(
        "--no-enable-scaling",
        action="store_true",
        help=f"Skip setting {ENABLE_SCALING_ANNOTATION}=true on the CR (copy the DB secret only).",
    )
    attach.add_argument(
        "--hibernate",
        action="store_true",
        help="Also write a hibernation-spec annotation that hibernates the deployment immediately.",
    )

    return parser.parse_args()


def _kubectl(context: str, *args: str, check: bool = True, stdin: str | None = None):
    return _run(["kubectl", "--context", context, *args], check=check, stdin=stdin)


def _install_keda(context: str) -> None:
    """KEDA is not part of the astronomer chart; worker-queue autoscaling cannot work without it."""
    _kubectl(context, "apply", "--server-side", "-f", KEDA_MANIFEST_URL)
    _kubectl(context, "wait", "-n", "keda", "deployment/keda-operator", "--for", "condition=available", "--timeout", "300s")


def _gh_token() -> str:
    """Resolve a GitHub token for the build.

    Laminar's Dockerfile sets GOPRIVATE=github.com/astronomer and fetches private Go modules, so
    `go mod download` fails with "could not read Username for https://github.com" without one.
    Same resolution order as laminar's own Justfile: $GH_TOKEN, else `gh auth token`.
    """
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token
    proc = _run(["gh", "auth", "token"], check=False)
    token = (proc.stdout or "").strip()
    if not token:
        raise CommandError(
            "No GitHub token available for the image build. Run `gh auth login`, or export GH_TOKEN. "
            "Laminar's Dockerfile needs it to fetch private github.com/astronomer Go modules."
        )
    return token


def _git_describe(laminar_repo: Path) -> tuple[str, str]:
    """Return (commit, branch-ish tag) for the LAMINAR_COMMIT / LAMINAR_IMAGE build args."""
    commit = (_run(["git", "-C", str(laminar_repo), "rev-parse", "HEAD"], check=False).stdout or "").strip()
    ref = (_run(["git", "-C", str(laminar_repo), "rev-parse", "--abbrev-ref", "HEAD"], check=False).stdout or "").strip()
    return commit or "unknown", (ref or "unknown").replace("/", "-")


def _build_and_import_image(*, context: str, laminar_repo: Path, image: str, platform: str) -> None:
    """Build Laminar from source and side-load it into k3d.

    Building beats pulling `astrocr.azurecr.io/astronomer/laminar`: no Azure login, no token that
    expires mid-session, and the image can be patched to test a change.

    Mirrors laminar's own `just docker-build`: buildx with the GH_TOKEN secret mount and the
    LAMINAR_* build args. Plain `docker build` cannot satisfy the Dockerfile's
    `--mount=type=secret,id=GH_TOKEN`.
    """
    dockerfile = laminar_repo / "Dockerfile"
    if not dockerfile.is_file():
        raise CommandError(f"{dockerfile} not found — is --laminar-repo really a laminar checkout?")

    commit, ref = _git_describe(laminar_repo)
    env = {**os.environ, "GH_TOKEN": _gh_token()}

    _run(
        [
            "docker",
            "buildx",
            "build",
            "--load",
            "--platform",
            platform,
            "--secret",
            "id=GH_TOKEN,env=GH_TOKEN",
            "--build-arg",
            f"LAMINAR_VERSION={LAMINAR_VERSION}",
            "--build-arg",
            f"LAMINAR_COMMIT={commit}",
            "--build-arg",
            f"LAMINAR_IMAGE={ref}",
            "-t",
            image,
            "-f",
            str(dockerfile),
            str(laminar_repo),
        ],
        capture=False,
        env=env,
    )

    cluster = context.removeprefix("k3d-")
    _run(["k3d", "image", "import", image, "-c", cluster], capture=False)


def _platform_postgres_dsn(*, context: str, platform_namespace: str) -> str:
    """Read the platform postgres superuser DSN out of the `astronomer-bootstrap` secret.

    The postgresql subchart creates this secret; it is the same credential commander uses to
    provision each deployment's Airflow database, so it can also create Laminar's own database.
    """
    proc = _kubectl(
        context,
        "-n",
        platform_namespace,
        "get",
        "secret",
        "astronomer-bootstrap",
        "-o",
        "jsonpath={.data.connection}",
        check=False,
    )
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        raise CommandError(
            f"Could not read secret astronomer-bootstrap in namespace {platform_namespace} (context={context}). "
            "Is this a data plane installed by bin/setup-cp-dp-k3d.py with postgres enabled?"
        )
    dsn = base64.b64decode(proc.stdout.strip()).decode("utf8").strip()
    if not dsn.startswith("postgres"):
        raise CommandError(
            f"astronomer-bootstrap holds a non-postgres connection ({dsn.split('://')[0]}://...). "
            "Laminar requires postgres; re-run the data plane with --dp-airflow-db=postgres."
        )
    if "-pgbouncer." in dsn:
        # With global.pgbouncer.enabled the bootstrap DSN points at pgbouncer, which only proxies
        # databases it has been configured for — so it cannot reach a database we just created.
        # Rather than emit a DSN that fails at runtime, make the caller supply a direct one.
        raise CommandError(
            "astronomer-bootstrap points at pgbouncer, which cannot reach a newly created database. "
            "Pass --postgres-dsn with a direct postgres superuser DSN "
            "(e.g. postgres://postgres:postgres@<release>-postgresql.<ns>.svc.cluster.local.:5432)."
        )
    return dsn


def _postgres_master_pod(*, context: str, platform_namespace: str, release_name: str) -> str:
    """Find the platform postgres pod.

    `role=master` alone is NOT specific enough: the elasticsearch master StatefulSet carries the
    same `release=<r>,role=master` pair, and sorts first, so selecting on it and taking item 0
    silently hands back `<release>-elasticsearch-master-0`. Pin `app=postgresql` too, and refuse
    to guess if more than one pod still matches.
    """
    selector = f"app=postgresql,release={release_name},role=master"
    proc = _kubectl(
        context,
        "-n",
        platform_namespace,
        "get",
        "pods",
        "-l",
        selector,
        "-o",
        "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
        check=False,
    )
    pods = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if proc.returncode != 0 or not pods:
        raise CommandError(
            f"Found no pod matching `{selector}` in {platform_namespace} (context={context}). "
            "Is the postgresql subchart enabled on this plane?"
        )
    if len(pods) > 1:
        raise CommandError(
            f"`{selector}` matched {len(pods)} pods in {platform_namespace} ({', '.join(pods)}). "
            "Refusing to guess which one is the primary — pass --postgres-dsn instead."
        )
    return pods[0]


def _create_laminar_database(*, context: str, platform_namespace: str, release_name: str) -> None:
    """Create Laminar's own database, idempotently.

    In Astro this is done by the external-db-operator reconciling the `Scheme` CR in
    manifests/base. Running that operator here would mean another private image for no POC value,
    so we create the database directly and drop the Scheme from the render.
    """
    pod = _postgres_master_pod(context=context, platform_namespace=platform_namespace, release_name=release_name)
    # `CREATE DATABASE` has no IF NOT EXISTS, so gate on a lookup and make the whole thing a no-op
    # on re-run.
    sql = (
        f"SELECT 'CREATE DATABASE {LAMINAR_DB_NAME}' "
        f"WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{LAMINAR_DB_NAME}')\\gexec"
    )
    _kubectl(
        context,
        "-n",
        platform_namespace,
        "exec",
        pod,
        "--",
        "bash",
        "-c",
        f"PGPASSWORD=$POSTGRES_PASSWORD psql -U postgres -v ON_ERROR_STOP=1 <<'SQL'\n{sql}\nSQL",
    )


def _apply_laminar_connection_secret(*, context: str, base_dsn: str) -> None:
    """Point LAMINAR_DATABASE_URL at Laminar's own database on the platform postgres."""
    dsn = base_dsn.rstrip("/")
    # astronomer-bootstrap carries a server-level DSN with no database path; append ours.
    if dsn.count("/") > 2:
        dsn = dsn.rsplit("/", 1)[0]
    dsn = f"{dsn}/{LAMINAR_DB_NAME}"

    secret_yaml = _kubectl(
        context,
        "-n",
        LAMINAR_NAMESPACE,
        "create",
        "secret",
        "generic",
        LAMINAR_DB_SECRET,
        f"--from-literal={LAMINAR_DB_SECRET_KEY}={dsn}",
        "--dry-run=client",
        "-o",
        "yaml",
    ).stdout
    _kubectl(context, "apply", "-f", "-", stdin=secret_yaml)


def _manifest_dirs(components: str) -> list[str]:
    """Laminar manifest directories to assemble, in kustomize order."""
    dirs = ["base", "hypervisor"]
    if components == "both":
        dirs.insert(1, "apiserver")
    return dirs


def _kustomization(*, image: str, components: str) -> str:
    """Overlay in the spirit of astro's harmony plugin: assemble the repo's manifest dirs,
    retarget the image, drop the Scheme, patch the deployments.

    Resources are referenced by bare relative name because kustomize refuses an absolute path as
    a resource root ("new root ... cannot be absolute"), and a relative path escaping the
    kustomization root trips the load restrictor. `_render_and_apply` copies the directories in
    alongside this file so every path stays local. Each of base/, hypervisor/ and apiserver/ is
    self-contained — their kustomizations reference only sibling files — so copying is lossless.
    """
    resource_block = "\n".join(f"  - {d}" for d in _manifest_dirs(components))

    patches = ["  - path: drop-scheme.yaml", "  - path: hypervisor-patch.yaml"]
    if components == "both":
        patches.append("  - path: apiserver-patch.yaml")
    patch_block = "\n".join(patches)

    return f"""\
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: {LAMINAR_NAMESPACE}
resources:
{resource_block}
patches:
{patch_block}
images:
  - name: laminar
    newName: {image.rsplit(":", 1)[0]}
    newTag: {image.rsplit(":", 1)[1] if ":" in image else "latest"}
"""


def _deployment_patch(name: str, *, enable_healers: bool) -> str:
    """Local-dev env for a Laminar deployment.

    Auth enforcement is off because APC has no Astro Cloud issuer and the P1 design descopes the
    api-server's inbound auth entirely. Healers are off by default per the design doc's P1
    decision — note Astro runs them ON, so leaving them off is a deliberate parity gap.
    """
    healer_env = ""
    if name == "hypervisor":
        healer_env = f"""
            - name: LAMINAR_HYPERVISOR__ENABLE_HEALERS
              value: "{enable_healers!s}"
            - name: LAMINAR_SCALING__DRY_RUN_STRATEGY
              value: "NEVER"
            - name: LAMINAR_APPLY_CUSTOM_DDL
              value: "true"\
"""
    return f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
spec:
  template:
    spec:
      nodeSelector: null
      containers:
        - name: {name}
          imagePullPolicy: IfNotPresent
          env:
            - name: LAMINAR_ENFORCE_AUTH
              value: "false"
            - name: LAMINAR_KUBE_NAMESPACE
              value: {LAMINAR_NAMESPACE}{healer_env}
"""


DROP_SCHEME = """\
$patch: delete
apiVersion: db.astronomer.io/v1alpha1
kind: Scheme
metadata:
  name: laminar
"""


def _render_and_apply(*, context: str, laminar_repo: Path, image: str, components: str, enable_healers: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="laminar-poc-") as tmp:
        overlay = Path(tmp)

        # Copy rather than reference: kustomize will not accept an absolute resource root, and a
        # relative one pointing outside the kustomization directory trips the load restrictor.
        # Copying keeps every path inside the overlay and leaves the laminar checkout untouched.
        for name in _manifest_dirs(components):
            source = laminar_repo / "manifests" / name
            if not (source / "kustomization.yaml").is_file():
                raise CommandError(
                    f"{source}/kustomization.yaml not found. Is --laminar-repo a laminar checkout, "
                    "and does this tag still lay its manifests out under manifests/<component>/?"
                )
            shutil.copytree(source, overlay / name)

        (overlay / "kustomization.yaml").write_text(_kustomization(image=image, components=components))
        (overlay / "drop-scheme.yaml").write_text(DROP_SCHEME)
        (overlay / "hypervisor-patch.yaml").write_text(_deployment_patch("hypervisor", enable_healers=enable_healers))
        if components == "both":
            (overlay / "apiserver-patch.yaml").write_text(_deployment_patch("apiserver", enable_healers=enable_healers))

        rendered = _run(["kustomize", "build", str(overlay)], check=True).stdout
        _kubectl(context, "apply", "--server-side", "-f", "-", stdin=rendered)


def _copy_metadata_secret(*, context: str, release_name: str, deployment_namespace: str) -> str:
    """Copy the deployment's metadata-DB connection into the `laminar` namespace.

    This is design-doc decision D4, done by hand. Commander writes
    `<release>-active-metadata` into the deployment namespace; Laminar reads `<cr-name>-db`
    out of its own namespace. Nothing bridges the two today.
    """
    source = f"{release_name}{COMMANDER_METADATA_SECRET_SUFFIX}"
    proc = _kubectl(
        context,
        "-n",
        deployment_namespace,
        "get",
        "secret",
        source,
        "-o",
        f"jsonpath={{.data.{LAMINAR_DEPLOYMENT_DB_SECRET_KEY}}}",
        check=False,
    )
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        raise CommandError(
            f"Could not read secret {source} (key '{LAMINAR_DEPLOYMENT_DB_SECRET_KEY}') in namespace "
            f"{deployment_namespace}. Is {release_name} an operator-mode deployment that finished provisioning?"
        )
    connection = base64.b64decode(proc.stdout.strip()).decode("utf8").strip()

    target = f"{release_name}-db"
    secret_yaml = _kubectl(
        context,
        "-n",
        LAMINAR_NAMESPACE,
        "create",
        "secret",
        "generic",
        target,
        f"--from-literal={LAMINAR_DEPLOYMENT_DB_SECRET_KEY}={connection}",
        "--dry-run=client",
        "-o",
        "yaml",
    ).stdout
    _kubectl(context, "apply", "-f", "-", stdin=secret_yaml)
    return target


def _ensure_astro_id_labels(
    *, context: str, release_name: str, deployment_namespace: str, workspace_id: str, organization_id: str
) -> dict[str, str]:
    """Stamp the three Astro identity labels Laminar requires before it will manage a CR.

    Laminar drops any Airflow CR that does not carry ALL THREE of
    `astronomer.io/deploymentId`, `astronomer.io/workspaceId` and `astronomer.io/organizationId`
    (`AstroResourceIDs.all()` in src/laminar/common/kubernetes/crds.py). On a miss it logs
    "Could not find Astro IDs on Airflow CR", sets the id to UNKNOWN_DEPLOYMENT_ID, and
    `astro_deployment_service.py` returns before caching it — so the deployment is discovered and
    then silently ignored, and `num_airflows` stays 0 forever.

    APC's CR carries only `astronomer.io/deploymentId`. It has the workspace id under a bare
    `workspace` key, and no organization id at all — Houston has no Organization model. So this
    is not a pure label copy; the organization id has to be synthesized.
    """
    existing = _kubectl(
        context,
        "-n",
        deployment_namespace,
        "get",
        "airflow",
        release_name,
        "-o",
        "jsonpath={.metadata.labels}",
        check=False,
    ).stdout
    labels: dict[str, str] = json.loads(existing) if (existing or "").strip() else {}

    resolved_workspace = workspace_id or labels.get("workspace", "")
    # No APC equivalent exists. The cluster id is at least a real, stable APC identifier; fall back
    # to a visible sentinel so nothing masquerades as a genuine Astro organization.
    resolved_org = organization_id or labels.get("clusterid", "") or "apc-no-organization"

    if not resolved_workspace:
        raise CommandError(f"No workspace id on {release_name}: the CR has no `workspace` label. Pass --workspace-id.")

    applied = {
        "astronomer.io/workspaceId": resolved_workspace,
        "astronomer.io/organizationId": resolved_org,
    }
    _kubectl(
        context,
        "-n",
        deployment_namespace,
        "label",
        "airflow",
        release_name,
        *[f"{k}={v}" for k, v in applied.items()],
        "--overwrite",
    )
    return applied


def _annotate_airflow_cr(*, context: str, release_name: str, deployment_namespace: str, hibernate: bool) -> None:
    """Set the annotations that decide whether the hypervisor acts on this deployment.

    Houston writes neither of these today — grep either annotation across houston-api/src and you
    get nothing. That gap is the reason this step is manual.
    """
    annotations = [f"{ENABLE_SCALING_ANNOTATION}=true"]
    if hibernate:
        spec = json.dumps({"override": {"hibernate": True, "overrideUntil": None}})
        annotations.append(f"{HIBERNATION_SPEC_ANNOTATION}={spec}")

    _kubectl(
        context,
        "-n",
        deployment_namespace,
        "annotate",
        "airflow",
        release_name,
        *annotations,
        "--overwrite",
    )


def _do_install(args: argparse.Namespace, ms: Milestones) -> None:
    laminar_repo = Path(args.laminar_repo).expanduser().resolve()
    if not laminar_repo.is_dir():
        raise CommandError(f"--laminar-repo {laminar_repo} is not a directory.")

    if not args.skip_keda:
        h = ms.start(f"Install KEDA v{KEDA_VERSION} (not shipped by the astronomer chart)")
        _install_keda(args.context)
        ms.done(h)
    else:
        ms.skip("Install KEDA", reason="--skip-keda set")

    if not args.skip_image_build:
        h = ms.start(f"Build laminar image from {laminar_repo} and import into k3d")
        _build_and_import_image(context=args.context, laminar_repo=laminar_repo, image=args.image, platform=args.platform)
        ms.done(h, detail=f"{args.image} ({args.platform})")
    else:
        ms.skip("Build laminar image", reason="--skip-image-build set")

    h = ms.start(f"Create `{LAMINAR_NAMESPACE}` namespace")
    _kubectl(args.context, "create", "namespace", LAMINAR_NAMESPACE, check=False)
    ms.done(h)

    h = ms.start("Provision Laminar's own database + laminar-connection secret")
    dsn = args.postgres_dsn or _platform_postgres_dsn(context=args.context, platform_namespace=args.platform_namespace)
    _create_laminar_database(context=args.context, platform_namespace=args.platform_namespace, release_name=args.release_name)
    _apply_laminar_connection_secret(context=args.context, base_dsn=dsn)
    ms.done(h, detail=f"database={LAMINAR_DB_NAME}")

    h = ms.start(f"Render + apply laminar manifests (components={args.components})")
    _render_and_apply(
        context=args.context,
        laminar_repo=laminar_repo,
        image=args.image,
        components=args.components,
        enable_healers=args.enable_healers,
    )
    ms.done(h, detail=f"healers={'on' if args.enable_healers else 'off'}")

    _print(
        "\nNext: attach a deployment.\n"
        f"  uv run bin/setup-laminar-poc.py attach-deployment --context {args.context} "
        "--release-name <release> --deployment-namespace <ns>\n"
    )


def _do_attach(args: argparse.Namespace, ms: Milestones) -> None:
    h = ms.start(f"Copy metadata-DB secret into `{LAMINAR_NAMESPACE}` (design doc D4, by hand)")
    target = _copy_metadata_secret(
        context=args.context,
        release_name=args.release_name,
        deployment_namespace=args.deployment_namespace,
    )
    ms.done(h, detail=f"{LAMINAR_NAMESPACE}/{target}")

    if args.no_astro_id_labels:
        ms.skip("Stamp Astro identity labels on the Airflow CR", reason="--no-astro-id-labels set")
    else:
        h = ms.start("Stamp Astro identity labels (Laminar ignores the CR without all three)")
        applied = _ensure_astro_id_labels(
            context=args.context,
            release_name=args.release_name,
            deployment_namespace=args.deployment_namespace,
            workspace_id=args.workspace_id,
            organization_id=args.organization_id,
        )
        ms.done(h, detail=", ".join(f"{k.split('/')[-1]}={v}" for k, v in applied.items()))

    if args.no_enable_scaling:
        ms.skip("Annotate the Airflow CR", reason="--no-enable-scaling set")
    else:
        h = ms.start("Annotate the Airflow CR so the hypervisor acts on it")
        _annotate_airflow_cr(
            context=args.context,
            release_name=args.release_name,
            deployment_namespace=args.deployment_namespace,
            hibernate=args.hibernate,
        )
        ms.done(h, detail="hibernation-spec written" if args.hibernate else ENABLE_SCALING_ANNOTATION)

    _print(
        "\nWatch it work:\n"
        f"  kubectl --context {args.context} -n {LAMINAR_NAMESPACE} logs -l app.kubernetes.io/component=hypervisor -f\n"
        f"  kubectl --context {args.context} -n {args.deployment_namespace} get pods -w\n"
    )


def main() -> int:
    args = parse_args()  # aborts here on --help or a bare run, before anything touches a cluster

    _require_executable("kubectl", hint="Install kubectl and ensure it is in PATH.")
    _require_executable("kustomize", hint="Install kustomize v4+ (e.g. `brew install kustomize`).")
    if args.action == "install-laminar":
        _require_executable("docker", hint="Install Docker Desktop/OrbStack and ensure `docker` works.")
        _require_executable("k3d", hint="Install k3d (e.g. `brew install k3d`).")
        if not args.skip_image_build:
            _require_executable("git", hint="Install git; the build args are derived from the laminar checkout.")
            _require_executable("gh", hint="Install the GitHub CLI and run `gh auth login`, or export GH_TOKEN.")

    ms = Milestones()
    try:
        if args.action == "install-laminar":
            _do_install(args, ms)
        else:
            _do_attach(args, ms)
        ms.print_summary_table()
        _print("\n✅ Completed.")
        return 0
    except Exception as e:  # noqa: BLE001
        ms.fail_active_if_any(error=str(e))
        ms.print_summary_table()
        _print(f"\n❌ Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
