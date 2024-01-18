from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
from subprocess import CalledProcessError


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
        assert (
            doc["spec"]["template"]["spec"]["containers"][0]["name"]
            == "cert-copy-and-toml-update"
        )

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

        volmounts = cert_copier["volumeMounts"]

        volmounts_expected = [
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
                "mountPath": "/private-ca-certs/private-ca-cert-foo/private-ca-cert-foo.crt",
                "subPath": "private-ca-cert-foo.crt",
            },
            {
                "name": "private-ca-cert-bar",
                "mountPath": "/private-ca-certs/private-ca-cert-bar/private-ca-cert-bar.crt",
                "subPath": "private-ca-cert-bar.crt",
            },
        ]

        assert volmounts == volmounts_expected
