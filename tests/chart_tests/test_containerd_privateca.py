import textwrap
from subprocess import CalledProcessError

import pytest

from tests import supported_k8s_versions
from tests.utils import get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestContainerdPrivateCaDaemonset:
    show_only = [
        "templates/trust-private-ca-on-all-nodes/containerd-daemonset.yaml",
        "templates/trust-private-ca-on-all-nodes/containerd-ca-update-script.yaml",
    ]

    @staticmethod
    def common_tests_daemonset(doc):
        """Test things common to all daemonsets."""
        assert doc["kind"] == "DaemonSet"
        assert doc["metadata"]["name"] == "release-name-containerd-ca-update"
        assert len(doc["spec"]["template"]["spec"]["containers"]) == 1
        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert container["name"] == "cert-copy-and-toml-update"
        assert container["securityContext"] == {"runAsUser": 0, "privileged": True, "readOnlyRootFilesystem": True}

    def test_privateca_daemonset_disabled(self, kube_version):
        """Test that no daemonset is rendered when privateCaCertsAddToHost is
        disabled."""
        with pytest.raises(CalledProcessError):
            render_chart(
                kube_version=kube_version,
                show_only=self.show_only,
                values={
                    "global": {
                        "privateCaCerts": [
                            "private-ca-cert-foo",
                            "private-ca-cert-bar",
                        ],
                        "privateCaCertsAddToHost": {
                            "enabled": False,
                            "addToContainerd": False,
                        },
                    }
                },
            )

    def test_containerd_privateca_daemonset_enabled(self, kube_version):
        """Test that the daemonset is rendered with valid properties when
        enabled."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "privateCaCerts": ["private-ca-cert-foo", "private-ca-cert-bar"],
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                    },
                }
            },
        )

        assert len(docs) == 2
        self.common_tests_daemonset(docs[0])
        cert_copier = docs[0]["spec"]["template"]["spec"]["containers"][0]
        image = cert_copier["image"]
        assert image.startswith("quay.io/astronomer/ap-db-bootstrapper:")
        assert image.split(":", 1)[1]  # non-empty tag

        volumemounts = cert_copier["volumeMounts"]
        volumes = docs[0]["spec"]["template"]["spec"]["volumes"]

        expected_volumes = [
            {
                "hostPath": {"path": "/etc/containerd", "type": ""},
                "name": "hostcontainerd",
            },
            {
                "name": "hostcerts",
                "hostPath": {"path": "/etc/containerd/certs.d/registry.example.com/"},
            },
            {
                "name": "containerd-ca-config",
                "configMap": {"name": "release-name-containerd-ca-config"},
            },
            {
                "name": "private-ca-cert-foo",
                "secret": {"secretName": "private-ca-cert-foo"},
            },
            {
                "name": "private-ca-cert-bar",
                "secret": {"secretName": "private-ca-cert-bar"},
            },
        ]

        expected_volumemounts = [
            {"name": "hostcerts", "mountPath": "/host-trust-store"},
            {
                "mountPath": "/hostcontainerd",
                "name": "hostcontainerd",
                "readOnly": False,
            },
            {
                "mountPath": "/scripts/update-containerd-certs.py",
                "name": "containerd-ca-config",
                "subPath": "update-containerd-certs.py",
            },
            {
                "name": "private-ca-cert-foo",
                "mountPath": "/private-ca-certs/private-ca-cert-foo/private-ca-cert-foo.pem",
                "subPath": "cert.pem",
            },
            {
                "name": "private-ca-cert-bar",
                "mountPath": "/private-ca-certs/private-ca-cert-bar/private-ca-cert-bar.pem",
                "subPath": "cert.pem",
            },
        ]

        assert volumemounts == expected_volumemounts
        assert volumes == expected_volumes

    def test_containerd_privateca_defaults(self, kube_version):
        """Default daemonset env vars and ConfigMap Python script (single render_chart)."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "baseDomain": "example.com",
                    "privateCaCerts": ["private-ca-cert-foo"],
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                    },
                }
            },
        )

        assert len(docs) == 2
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        env = get_env_vars_dict(container["env"])
        assert env["REGISTRY_HOST"] == "registry.example.com"
        assert env["CONTAINERD_HOST_PATH"] == "/hostcontainerd"
        assert env["CERT_CONFIG_PATH"] == "/etc/containerd/certs.d"
        assert env["PRIVATE_CA_CERTS_DIR"] == "/private-ca-certs"

        configmap = docs[1]
        assert configmap["kind"] == "ConfigMap"
        script = configmap["data"]["update-containerd-certs.py"]
        assert "detect_containerd_version" in script
        assert "generate_hosts_toml" in script
        assert "REGISTRY_HOST" in script

        assert "containerd-config-toml" not in configmap["data"]
        volume_mounts = container["volumeMounts"]
        assert not any(vm.get("mountPath") == "/config/containerd-config-toml" for vm in volume_mounts)

    def test_containerd_privateca_containerd_config_toml_mounted_from_configmap(self, kube_version):
        """When `global.privateCaCertsAddToHost.containerdConfigToml` is set,
        the blob lands in the ConfigMap under the `containerd-config-toml` key
        and is mounted into the container at /config/containerd-config-toml
        via subPath. The Python script reads it from there on containerd 1.x.

        A ConfigMap mount is used rather than an env var so multi-line TOML
        renders cleanly (both in the chart template and in `kubectl describe
        pod` output) and the reader contract is a simple file read."""
        operator_blob = textwrap.dedent("""\
            [plugins."io.containerd.grpc.v1.cri".registry.configs."registry.example.com".tls]
              ca_file = "/etc/containerd/certs.d/registry.example.com/private-ca-cert-foo.pem"
        """)
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "baseDomain": "example.com",
                    "privateCaCerts": ["private-ca-cert-foo"],
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                        "containerdConfigToml": operator_blob,
                    },
                }
            },
        )

        daemonset, configmap = docs
        container = daemonset["spec"]["template"]["spec"]["containers"][0]

        # Blob lives in the ConfigMap under a well-known key.
        blob_in_cm = configmap["data"]["containerd-config-toml"]
        assert 'plugins."io.containerd.grpc.v1.cri".registry.configs."registry.example.com".tls' in blob_in_cm
        assert 'ca_file = "/etc/containerd/certs.d/registry.example.com/private-ca-cert-foo.pem"' in blob_in_cm

        # Container mounts that key as a single file at the path the script reads.
        volume_mounts = container["volumeMounts"]
        blob_mount = next(
            (vm for vm in volume_mounts if vm.get("mountPath") == "/config/containerd-config-toml"),
            None,
        )
        assert blob_mount is not None
        assert blob_mount["name"] == "containerd-ca-config"
        assert blob_mount["subPath"] == "containerd-config-toml"

        # No stale env var — the blob must not be passed through env.
        env = get_env_vars_dict(container["env"])
        assert "CONTAINERD_CONFIG_TOML" not in env

    def test_containerd_privateca_daemonset_host_path_overrides(self, kube_version):
        """Test that the daemonset is rendered with custom hostPath."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "privateCaCerts": ["private-ca-cert-foo", "private-ca-cert-bar"],
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                        "containerdHostPath": "/etc/astronomer",
                    },
                }
            },
        )

        assert len(docs) == 2
        self.common_tests_daemonset(docs[0])
        volumes = docs[0]["spec"]["template"]["spec"]["volumes"]
        hostcontainerd_vol = next(v for v in volumes if v["name"] == "hostcontainerd")
        assert hostcontainerd_vol["hostPath"]["path"] == "/etc/astronomer"

    def test_containerd_privateca_daemonset_enabled_with_priority_class(self, kube_version):
        """Test that the containerd daemonset is rendered with priorityClass when
        enabled."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                        "priorityClassName": "high-priority",
                    },
                }
            },
        )

        assert len(docs) == 2
        self.common_tests_daemonset(docs[0])
        assert "high-priority" == docs[0]["spec"]["template"]["spec"]["priorityClassName"]

    def test_containerd_privateca_daemonset_enabled_with_affinity_and_toleration(self, kube_version):
        """Test that the containerd daemonset is rendered with affinity and toleration when enabled."""
        tolerationSpec = [{"key": "special-purpose", "operator": "Equal", "value": "workers-spot-vms", "effect": "NoExecute"}]
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                        "containerdTolerations": tolerationSpec,
                    },
                }
            },
        )

        assert len(docs) == 2
        self.common_tests_daemonset(docs[0])
        assert tolerationSpec == docs[0]["spec"]["template"]["spec"]["tolerations"]

    @pytest.mark.parametrize(
        "plane_mode,domain_prefix,expected_registry_host,expected_hostcerts_path",
        [
            ("data", "dp01", "registry.dp01.example.com", "/etc/containerd/certs.d/registry.dp01.example.com/"),
            ("unified", "", "registry.example.com", "/etc/containerd/certs.d/registry.example.com/"),
        ],
    )
    def test_containerd_registry_host_respects_plane(
        self,
        kube_version,
        plane_mode,
        domain_prefix,
        expected_registry_host,
        expected_hostcerts_path,
    ):
        """Registry hostname and hostcerts volume path follow plane mode (data vs unified)."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "baseDomain": "example.com",
                    "plane": {
                        "mode": plane_mode,
                        "domainPrefix": domain_prefix,
                    },
                    "privateCaCerts": ["private-ca-cert-foo"],
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                    },
                }
            },
        )

        assert len(docs) == 2
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        env = get_env_vars_dict(container["env"])
        assert env["REGISTRY_HOST"] == expected_registry_host
        volumes = docs[0]["spec"]["template"]["spec"]["volumes"]
        hostcerts_vol = next(v for v in volumes if v["name"] == "hostcerts")
        assert hostcerts_vol["hostPath"]["path"] == expected_hostcerts_path
