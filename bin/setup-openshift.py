#!/usr/bin/env python3
"""Create a single-node OpenShift cluster in a container and prepare it for `helm install`.

Named for what it provides; MicroShift is the OKD distribution that fits in a container.

Interchangeable with bin/setup-kind.py by design -- same --topology flag, same kubeconfig path,
same namespace and TLS secrets -- which is what lets bin/reset-local-dev pick between them with
--cluster-provider and leaves helm-install.py and the scenario machinery untouched.

Needs podman, not docker: the MicroShift image runs --privileged with the host's /dev so TopoLVM
can carve PVs out of a real LVM volume group. On Linux (CircleCI) that host is this machine, so
podman runs rootful via sudo; on macOS it is podman's VM, reached with `podman machine ssh`.

KUBE_VERSION is ignored -- it pins the KIND node image, and MicroShift's Kubernetes version is
whatever MICROSHIFT_IMAGE ships.
"""

import argparse
import os
import platform
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml
from certs import astronomer_tls_cert_file, astronomer_tls_key_file
from k3d_setup_shared import _mkcert_caroot, _mkcert_path
from kubernetes import client, config

# OKD/SCOS build, which ships TopoLVM and the router preconfigured.
# https://github.com/microshift-io/microshift/pkgs/container/microshift
MICROSHIFT_IMAGE = "ghcr.io/microshift-io/microshift:4.22.0_202610071017_g0a516b4eb_4.22.0_okd_scos.ec.16"
CONTAINER_NAME = "microshift"

# What upstream's quickstart.sh sets, so the image runs as tested. Unrelated to the platform's
# base domain (localtest.me): the chart's Ingress objects carry explicit hosts, which the router
# admits whatever the cluster is called.
CONTAINER_HOSTNAME = "127.0.0.1.nip.io"

# Only the API is published by default -- all pytest needs. The router's 80/443 are opt-in
# (--publish-router-ports) because they are usually already taken on a developer machine.
API_PORT = 6443
HTTP_PORT = 80
HTTPS_PORT = 443

# TopoLVM provisions PVs out of this group, so it caps every PVC the chart creates.
# configs/openshift.yaml trims them to ~37Gi against the 50Gi here; raise both together.
#
# The name is NOT a free choice: MicroShift generates the topolvm-lvmd-0 ConfigMap from a
# built-in default that hardcodes myvg1 and ignores /etc/microshift/lvmd.yaml. Rename this and
# lvmd crashloops with "volume group not found" unless you also patch that ConfigMap.
VG_NAME = "myvg1"
LVM_DISK = "/var/lib/microshift-okd/lvmdisk.image"
LVM_SIZE = "50G"

IN_CONTAINER_KUBECONFIG = "/var/lib/microshift/resources/kubeadmin/kubeconfig"
HOST_KUBECONFIG_SOURCE = f"/var/lib/microshift/resources/kubeadmin/{CONTAINER_HOSTNAME}/kubeconfig"
KUBECONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"
KUBECTL_EXE = str(Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "kubectl")
READY_TIMEOUT = 600
MIN_MACHINE_MEMORY_MB = 8192

IS_LINUX = platform.system() == "Linux"

# cgroupfs rather than podman's default systemd cgroup manager on Linux. The systemd manager
# places conmon in a cgroup over dbus, and where that is unavailable -- a CI VM with no usable
# system dbus -- conmon dies before saying anything, which podman reports as the unhelpful
# "container create failed (no logs from conmon)". cgroupfs needs neither.
PODMAN = ["sudo", "podman", "--cgroup-manager=cgroupfs"] if IS_LINUX else ["podman"]


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--topology",
        required=True,
        choices=["unified", "control", "data"],
        help="Install topology to set up: unified (control+data in one cluster), control, or data. "
        "Names the kubeconfig this writes, which is how bin/helm-install.py finds the cluster.",
    )
    parser.add_argument(
        "--publish-router-ports",
        action="store_true",
        # Also readable from the environment, because bin/run-scenario.py has no way to pass a flag
        # through to this script, and this is the only knob a local run wants.
        default=os.environ.get("PUBLISH_ROUTER_PORTS", "").lower() in ("1", "true", "yes"),
        help=f"Also publish the router's ports {HTTP_PORT} and {HTTPS_PORT}, so the platform can be opened "
        "in a browser (also settable as PUBLISH_ROUTER_PORTS=1, which is how a scenario run reaches it). "
        f"Off by default: {HTTPS_PORT} is usually already taken on a developer machine, which fails the "
        "container with 'bind: address already in use'.",
    )
    return parser.parse_args()


def run(cmd: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command, echoing it first so a CI log shows what actually ran."""
    print(f"+ {shlex.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, text=True, check=False, capture_output=capture)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {shlex.join(cmd)}\n{(proc.stderr or '').strip()}")
    return proc


def podman(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run podman against whichever daemon owns the MicroShift container."""
    return run([*PODMAN, *args], check=check, capture=capture)


def host_sh(script: str, *, check: bool = True) -> str:
    """Run `script` as root on the host the containers run on: this machine, or podman's VM."""
    if IS_LINUX:
        cmd = ["sudo", "bash", "-c", script]
    else:
        cmd = ["podman", "machine", "ssh", f"sudo bash -c {shlex.quote(script)}"]
    return (run(cmd, check=check).stdout or "").strip()


def check_podman_available() -> None:
    """Fail early, and with the fix, rather than 40 lines into a cluster that cannot start."""
    if podman("--version", check=False).returncode != 0:
        raise SystemExit(
            "ERROR: podman is not available.\n"
            "  CircleCI's machine executor does not ship it: `sudo apt-get install -y podman`.\n"
            "  macOS: `brew install podman`, then `podman machine init --rootful` and `podman machine start`."
        )
    if IS_LINUX:
        return

    fields = run(["podman", "machine", "inspect", "--format", "{{.Rootful}} {{.Resources.Memory}}"], check=False).stdout.split()
    if len(fields) != 2:
        raise SystemExit("ERROR: could not inspect the podman machine -- is one initialised and started?")
    rootful, memory_mb = fields[0], int(fields[1])

    if rootful != "true":
        raise SystemExit(
            "ERROR: the podman machine must be rootful -- MicroShift runs --privileged with the host's /dev.\n"
            "  podman machine stop && podman machine set --rootful && podman machine start"
        )
    if memory_mb < MIN_MACHINE_MEMORY_MB:
        raise SystemExit(
            f"ERROR: the podman machine has {memory_mb}MiB, below the {MIN_MACHINE_MEMORY_MB}MiB this needs. "
            "The platform's pods will sit Pending on Insufficient memory.\n"
            f"  podman machine stop && podman machine set --memory {MIN_MACHINE_MEMORY_MB} && podman machine start"
        )


def wipe_logical_volumes() -> None:
    """Remove every logical volume in the volume group.

    The group outlives the cluster and nothing reclaims a TopoLVM volume once its PV is gone, so
    they accumulate until the next install sits Pending on "not enough free storage". Every LV is
    an orphan here, because this only runs when the cluster is about to be recreated.
    """
    removed = host_sh(
        f"n=0\n"
        f"for lv in $(lvs --noheadings -o lv_name {VG_NAME} 2>/dev/null); do\n"
        f"  lvremove -f {VG_NAME}/$lv >/dev/null 2>&1 && n=$((n+1))\n"
        f"done\n"
        f"echo $n",
        check=False,
    )
    if removed and removed != "0":
        print(f"Reclaimed {removed} stale TopoLVM volume(s) from '{VG_NAME}'")


def ensure_volume_group() -> None:
    """Create the volume group TopoLVM provisions from: a sparse file behind a loop device,
    because neither a CI machine nor a podman VM has a spare block device."""
    print(f"Ensuring LVM volume group '{VG_NAME}' exists")
    result = host_sh(
        f"set -e\n"
        f"if vgs {VG_NAME} >/dev/null 2>&1; then echo 'reusing existing volume group'; exit 0; fi\n"
        f"mkdir -p {Path(LVM_DISK).parent}\n"
        # A leftover file from a half-made cluster: zero its header so vgcreate accepts it.
        f"if [ -f {LVM_DISK} ]; then dd if=/dev/zero of={LVM_DISK} bs=1M count=100 conv=notrunc >/dev/null 2>&1;\n"
        f"else truncate --size={LVM_SIZE} {LVM_DISK}; fi\n"
        f"DEV=$(losetup -j {LVM_DISK} | cut -d: -f1 | head -1)\n"
        f'if [ -z "$DEV" ]; then DEV=$(losetup --find --show --nooverlap {LVM_DISK}); fi\n'
        f'vgcreate -f -y {VG_NAME} "$DEV"\n'
        f'echo "created volume group {VG_NAME} on $DEV"'
    )
    print(result)


def start_container(publish_router_ports: bool = False) -> None:
    """(Re)create the MicroShift container.

    --replace, not reuse: a cluster left from an earlier run has that run's chart in it. No --rm,
    so a container that dies during startup is still there for `podman logs`.
    """
    # The image declares VOLUME /var, so each run's container owns an anonymous volume holding
    # etcd and the cluster certs. --replace would delete the container and leave that volume
    # behind, one per run; -v drops them together, which also keeps /var and the volume group
    # consistent, since the next line wipes the volume group too.
    podman("rm", "--force", "--volumes", CONTAINER_NAME, check=False)
    wipe_logical_volumes()

    # Only an OVN-K build needs this; harmless otherwise, and upstream does it unconditionally.
    if IS_LINUX:
        host_sh("modprobe openvswitch || true", check=False)

    # TopoLVM needs the host's device nodes; mask the ones that come along with them.
    #
    # notmpcopyup because the default copies the directory's existing contents into the new
    # tmpfs, which is both the opposite of masking and a hard failure: runc cannot recreate a
    # device node in its staging dir, so /dev/input dies on "lchown .../event0: no such file or
    # directory". An empty tmpfs is what a mask means.
    run_opts = ["--tty", "--volume", "/dev:/dev"]
    for device in ("input", "snd", "dri"):
        if host_sh(f"test -d /dev/{device} && echo yes || true", check=False) == "yes":
            run_opts += ["--tmpfs", f"/dev/{device}:rw,notmpcopyup"]

    published = ["--publish", f"{API_PORT}:6443"]
    if publish_router_ports:
        published += ["--publish", f"{HTTP_PORT}:80", "--publish", f"{HTTPS_PORT}:443"]

    print(f"Starting {CONTAINER_NAME} from {MICROSHIFT_IMAGE} (this pulls a few GB on a cold machine)")
    podman(
        "run",
        "--privileged",
        "--detach",
        *run_opts,
        *published,
        "--name",
        CONTAINER_NAME,
        "--hostname",
        CONTAINER_HOSTNAME,
        MICROSHIFT_IMAGE,
        capture=False,
    )


def oc(*args: str, check: bool = True) -> str:
    """Run `oc` inside the container, which is the only place a kubeconfig exists yet."""
    proc = podman("exec", "--env", f"KUBECONFIG={IN_CONTAINER_KUBECONFIG}", CONTAINER_NAME, "oc", *args, check=check)
    return (proc.stdout or "").strip()


def wait_for_kubeconfig(timeout: int = 300) -> None:
    """Wait for the kubeadmin kubeconfig to appear, as upstream's quickstart.sh does.

    Before the node check, not instead of it: failing here means MicroShift never started, which
    is a different problem from a node that never went Ready.
    """
    print(f"Waiting up to {timeout}s for MicroShift to write {IN_CONTAINER_KUBECONFIG}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if podman("exec", CONTAINER_NAME, "test", "-f", IN_CONTAINER_KUBECONFIG, check=False).returncode == 0:
            return
        time.sleep(2)
    podman("logs", "--tail=50", CONTAINER_NAME, check=False, capture=False)
    raise RuntimeError(f"MicroShift never wrote {IN_CONTAINER_KUBECONFIG} within {timeout}s -- container logs above")


def check_container_dns() -> None:
    """Fail now if the container cannot resolve quay.io.

    A VPN or custom resolver on the host leaves every pod in ContainerCreating until its image
    pull times out, so the install looks hung rather than broken.
    """
    if podman("exec", CONTAINER_NAME, "getent", "hosts", "quay.io", check=False).returncode != 0:
        raise RuntimeError(
            "DNS resolution for 'quay.io' failed inside the container, so no pod will be able to pull "
            "its image. This is usually a VPN or a custom DNS configuration on the host that the "
            "container cannot reach -- disconnect from the VPN, or point podman at a resolver it can use."
        )


def wait_for_node_ready(timeout: int = READY_TIMEOUT) -> None:
    """Block until the single node reports Ready."""
    print(f"Waiting up to {timeout}s for MicroShift to come up")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if " Ready " in f" {oc('get', 'nodes', '--no-headers', check=False)} ":
            print("Node is Ready")
            return
        time.sleep(5)
    print(oc("get", "pods", "--all-namespaces", check=False), file=sys.stderr)
    raise RuntimeError(f"Timed out after {timeout}s waiting for the MicroShift node to become Ready")


def wait_for_cluster_components() -> None:
    """Wait for the router and TopoLVM: not part of the chart, but an install that starts before
    they are up fails as if they were."""
    oc("rollout", "status", "deployment/router-default", "--namespace=openshift-ingress", "--timeout=300s", check=False)
    oc("wait", "--for=condition=Ready", "pod", "--all", "--namespace=topolvm-system", "--timeout=300s", check=False)

    # Reused across a host reboot, topolvm can come up before the loop device does and find no
    # volume group. Restarting it is the documented recovery.
    if any(
        state in oc("get", "pods", "--namespace=topolvm-system", "--no-headers", check=False)
        for state in ("CrashLoopBackOff", "Error")
    ):
        print(f"Restarting topolvm pods to pick up volume group '{VG_NAME}'")
        oc("delete", "pod", "--all", "--namespace=topolvm-system", check=False)
        oc("wait", "--for=condition=Ready", "pod", "--all", "--namespace=topolvm-system", "--timeout=300s")


def write_kubeconfig(kubeconfig_file: Path) -> None:
    """Copy the per-hostname kubeadmin kubeconfig out to the path helm-install.py and pytest read.

    Per-hostname, not the default one: TLS to an IP sends no SNI, so https://127.0.0.1:6443 gets
    MicroShift's fallback serving cert, which the default kubeconfig's CA does not sign --
    "certificate verify failed: self-signed certificate in certificate chain". The kubeconfig
    MicroShift writes for its own hostname carries the CA for the cert served under that name,
    and the name resolves to 127.0.0.1, so TLS verifies without --insecure-skip-tls-verify.

    Only the port is rewritten, to whichever one is published.
    """
    proc = podman("exec", CONTAINER_NAME, "cat", HOST_KUBECONFIG_SOURCE, check=False)
    if proc.returncode != 0:
        present = podman("exec", CONTAINER_NAME, "ls", Path(HOST_KUBECONFIG_SOURCE).parent.parent.as_posix(), check=False)
        raise RuntimeError(
            f"No kubeconfig at {HOST_KUBECONFIG_SOURCE}. MicroShift writes one per hostname it serves; "
            f"present: {(present.stdout or '').split() or '(none)'}"
        )
    kubeconfig = yaml.safe_load(proc.stdout)
    if not kubeconfig or not kubeconfig.get("clusters"):
        raise RuntimeError(f"Could not parse a kubeconfig out of {HOST_KUBECONFIG_SOURCE}")
    for cluster in kubeconfig["clusters"]:
        cluster["cluster"]["server"] = f"https://{CONTAINER_HOSTNAME}:{API_PORT}"

    kubeconfig_file.parent.mkdir(parents=True, exist_ok=True)
    kubeconfig_file.write_text(yaml.safe_dump(kubeconfig))
    kubeconfig_file.chmod(0o600)
    print(f"Wrote kubeconfig to {kubeconfig_file}")


def verify_host_api_access(kubeconfig_file: Path) -> None:
    """Prove the API is reachable from here, not just from inside the container."""
    # nip.io is public wildcard DNS, and a resolver with rebind protection will not return
    # 127.0.0.1 for it.
    try:
        socket.gethostbyname(CONTAINER_HOSTNAME)
    except OSError as exc:
        raise RuntimeError(
            f"{CONTAINER_HOSTNAME} does not resolve here, so the API cannot be reached by the name its "
            f"certificate is issued for. Add it to /etc/hosts as 127.0.0.1, or use a resolver that "
            f"allows nip.io. ({exc})"
        ) from exc

    config.load_kube_config(config_file=str(kubeconfig_file))
    nodes = client.CoreV1Api().list_node().items
    if not nodes:
        raise RuntimeError(f"The API at https://{CONTAINER_HOSTNAME}:{API_PORT} reports no nodes")
    print(f"API reachable from the host: node {nodes[0].metadata.name}")


def create_namespace(kubeconfig: str, namespace: str = "astronomer") -> None:
    """Create the given namespace, tolerating one that is already there."""
    proc = run([KUBECTL_EXE, f"--kubeconfig={kubeconfig}", "create", "namespace", namespace], check=False)
    if proc.returncode == 0 or "AlreadyExists" in (proc.stderr or ""):
        return
    raise RuntimeError(f"Failed to create namespace {namespace}: {(proc.stderr or '').strip()}")


def create_astronomer_tls_secret(kubeconfig: str, namespace: str = "astronomer") -> None:
    """Create the astronomer-tls secret from the cert bin/certs.py generate-tls issued."""
    run(
        [
            KUBECTL_EXE,
            f"--kubeconfig={kubeconfig}",
            f"--namespace={namespace}",
            "create",
            "secret",
            "tls",
            "astronomer-tls",
            f"--cert={astronomer_tls_cert_file}",
            f"--key={astronomer_tls_key_file}",
        ]
    )


def create_mkcert_root_ca_secret(kubeconfig: str, namespace: str = "astronomer") -> None:
    """Create the mkcert-root-ca secret, so the platform trusts its own dev TLS chain.

    The CA that signs astronomer-tls, resolved the same way bin/setup-kind.py does. Consumers of
    global.privateCaCerts mount it with `subPath: cert.pem`, so the key= prefix is required.
    """
    root_ca = _mkcert_caroot(_mkcert_path())
    run(
        [
            KUBECTL_EXE,
            f"--kubeconfig={kubeconfig}",
            f"--namespace={namespace}",
            "create",
            "secret",
            "generic",
            "mkcert-root-ca",
            f"--from-file=cert.pem={root_ca}",
        ]
    )


def setup_common_cluster_configs(kubeconfig: str) -> None:
    """The three objects bin/setup-kind.py also creates, before helm-install.py runs."""
    create_namespace(kubeconfig)
    create_astronomer_tls_secret(kubeconfig)
    create_mkcert_root_ca_secret(kubeconfig)


def main() -> None:
    args = parse_args()
    kubeconfig_file = KUBECONFIG_DIR / args.topology

    check_podman_available()
    if not Path(astronomer_tls_cert_file).exists():
        raise SystemExit(f"ERROR: {astronomer_tls_cert_file} is missing -- run `bin/certs.py generate-tls` first.")

    ensure_volume_group()
    start_container(args.publish_router_ports)
    wait_for_kubeconfig()
    check_container_dns()
    wait_for_node_ready()
    wait_for_cluster_components()
    write_kubeconfig(kubeconfig_file)
    verify_host_api_access(kubeconfig_file)
    setup_common_cluster_configs(str(kubeconfig_file))

    print(f"MicroShift cluster '{args.topology}' setup completed successfully.")


if __name__ == "__main__":
    main()
