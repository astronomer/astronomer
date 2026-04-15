from subprocess import CalledProcessError

import pytest

from tests import supported_k8s_versions
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
        assert cert_copier["image"] == "quay.io/astronomer/ap-db-bootstrapper:1.1.2"

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
                "name": "cert-copy-and-toml-update",
                "configMap": {"name": "release-name-cert-copy-and-toml-update"},
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
                "name": "cert-copy-and-toml-update",
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

    def test_containerd_privateca_daemonset_has_env_vars(self, kube_version):
        """Test that the daemonset injects the required environment variables
        for the Python script."""
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

        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        env = {e["name"]: e["value"] for e in container["env"]}
        assert env["REGISTRY_HOST"] == "registry.example.com"
        assert env["CONTAINERD_HOST_PATH"] == "/hostcontainerd"
        assert env["CERT_CONFIG_PATH"] == "/etc/containerd/certs.d"
        assert env["PRIVATE_CA_CERTS_DIR"] == "/private-ca-certs"

    def test_containerd_privateca_configmap_uses_python_script(self, kube_version):
        """Test that the ConfigMap contains the Python script loaded via .Files.Get."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "privateCaCerts": ["private-ca-cert-foo"],
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "addToContainerd": True,
                    },
                }
            },
        )

        configmap = docs[1]
        assert configmap["kind"] == "ConfigMap"
        script = configmap["data"]["update-containerd-certs.py"]
        # Verify it's the Python script with key features
        assert "detect_containerd_version" in script
        assert "generate_hosts_toml" in script
        assert "REGISTRY_HOST" in script

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

    def test_containerd_data_plane_mode_uses_domain_prefix(self, kube_version):
        """Test that in data plane mode the registry host includes the
        domainPrefix to form the correct registry hostname."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "baseDomain": "example.com",
                    "plane": {
                        "mode": "data",
                        "domainPrefix": "dp01",
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

        # Verify the daemonset env var uses the DP registry host
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        env = {e["name"]: e["value"] for e in container["env"]}
        assert env["REGISTRY_HOST"] == "registry.dp01.example.com"

        # Verify the daemonset volume path uses the DP registry host
        volumes = docs[0]["spec"]["template"]["spec"]["volumes"]
        hostcerts_vol = next(v for v in volumes if v["name"] == "hostcerts")
        assert hostcerts_vol["hostPath"]["path"] == "/etc/containerd/certs.d/registry.dp01.example.com/"

    def test_containerd_unified_mode_uses_base_domain(self, kube_version):
        """Test that in unified mode the registry host uses baseDomain
        without domainPrefix."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "baseDomain": "example.com",
                    "plane": {
                        "mode": "unified",
                        "domainPrefix": "",
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

        # Verify the daemonset env var uses base registry host (no prefix)
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        env = {e["name"]: e["value"] for e in container["env"]}
        assert env["REGISTRY_HOST"] == "registry.example.com"

        # Verify the daemonset volume path
        volumes = docs[0]["spec"]["template"]["spec"]["volumes"]
        hostcerts_vol = next(v for v in volumes if v["name"] == "hostcerts")
        assert hostcerts_vol["hostPath"]["path"] == "/etc/containerd/certs.d/registry.example.com/"
