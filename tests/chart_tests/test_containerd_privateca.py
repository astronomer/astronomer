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
        assert len(docs[0]["spec"]["template"]["spec"]["containers"]) == 1
        cert_copier = docs[0]["spec"]["template"]["spec"]["containers"][0]
        cert_copier["image"].startswith("alpine:3")

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
                "mountPath": "/cert-copy-and-toml-update.sh",
                "name": "cert-copy-and-toml-update",
                "subPath": "update-containerd-certs.sh",
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
        assert len(docs[0]["spec"]["template"]["spec"]["containers"]) == 1
        cert_copier = docs[0]["spec"]["template"]["spec"]["containers"][0]
        cert_copier["image"].startswith("alpine:3")

        volumemounts = cert_copier["volumeMounts"]
        volumes = docs[0]["spec"]["template"]["spec"]["volumes"]

        expected_volumes = [
            {
                "hostPath": {"path": "/etc/astronomer", "type": ""},
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
                "mountPath": "/cert-copy-and-toml-update.sh",
                "name": "cert-copy-and-toml-update",
                "subPath": "update-containerd-certs.sh",
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
        assert len(docs[0]["spec"]["template"]["spec"]["containers"]) == 1
        cert_copier = docs[0]["spec"]["template"]["spec"]["containers"][0]
        cert_copier["image"].startswith("alpine:3")
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
        assert len(docs[0]["spec"]["template"]["spec"]["containers"]) == 1
        assert tolerationSpec == docs[0]["spec"]["template"]["spec"]["tolerations"]

    def test_containerd_v2_script_uses_cri_v1_images_plugin(self, kube_version):
        """Test that containerdVersion 2 renders the script with the
        io.containerd.cri.v1.images plugin namespace for GKE 1.33+."""
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
                        "containerdVersion": "2",
                    },
                }
            },
        )

        assert len(docs) == 2
        # docs[1] is the ConfigMap with the script
        configmap = docs[1]
        assert configmap["kind"] == "ConfigMap"
        script = configmap["data"]["update-containerd-certs.sh"]
        assert 'CONTAINERD_VERSION="2"' in script
        # Both plugin namespaces are in the shell if/else, but the version variable
        # controls which branch is taken at runtime
        assert 'io.containerd.cri.v1.images' in script
        assert 'io.containerd.grpc.v1.cri' in script
        # Should use hosts.toml approach and generate_hosts_toml
        assert "generate_hosts_toml" in script
        assert "registry.example.com" in script

    def test_containerd_v1_script_uses_grpc_v1_cri_plugin(self, kube_version):
        """Test that containerdVersion 1 renders the script with the
        io.containerd.grpc.v1.cri plugin namespace for legacy containerd."""
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
                        "containerdVersion": "1",
                    },
                }
            },
        )

        assert len(docs) == 2
        configmap = docs[1]
        assert configmap["kind"] == "ConfigMap"
        script = configmap["data"]["update-containerd-certs.sh"]
        assert 'CONTAINERD_VERSION="1"' in script
        # Both plugin namespaces are in the shell if/else — runtime selection via CONTAINERD_VERSION
        assert 'io.containerd.grpc.v1.cri' in script
        assert 'io.containerd.cri.v1.images' in script

    def test_containerd_v2_default_generates_hosts_toml(self, kube_version):
        """Test that when containerdVersion is 2 and containerdConfigToml is not
        set, the script generates a standard hosts.toml with CA cert path."""
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
                        "containerdVersion": "2",
                    },
                }
            },
        )

        configmap = docs[1]
        script = configmap["data"]["update-containerd-certs.sh"]
        # When containerdConfigToml is nil, the script should use generate_hosts_toml
        assert "generate_hosts_toml" in script
        assert "ca.crt" in script

    def test_containerd_v2_custom_config_toml_override(self, kube_version):
        """Test that when containerdConfigToml is set, the script uses the
        custom content for hosts.toml instead of generating one."""
        custom_toml = 'server = "https://custom.registry.io"\n[host."https://custom.registry.io"]\n  capabilities = ["pull"]\n  skip_verify = true'
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
                        "containerdVersion": "2",
                        "containerdConfigToml": custom_toml,
                    },
                }
            },
        )

        configmap = docs[1]
        script = configmap["data"]["update-containerd-certs.sh"]
        assert "custom.registry.io" in script
