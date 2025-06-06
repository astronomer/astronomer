from subprocess import CalledProcessError

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrivateCaDaemonset:
    show_only = ["templates/trust-private-ca-on-all-nodes/daemonset.yaml"]

    @staticmethod
    def common_tests_daemonset(doc):
        """Test things common to all daemonsets."""
        assert doc["kind"] == "DaemonSet"
        assert doc["metadata"]["name"] == "release-name-private-ca"
        assert doc["spec"]["template"]["spec"]["containers"][0]["name"] == "cert-copy"

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
                        },
                    }
                },
            )

    def test_privateca_daemonset_enabled(self, kube_version):
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
                    },
                }
            },
        )

        assert len(docs) == 1
        self.common_tests_daemonset(docs[0])
        assert len(docs[0]["spec"]["template"]["spec"]["containers"]) == 1
        cert_copier = docs[0]["spec"]["template"]["spec"]["containers"][0]
        cert_copier["image"].startswith("alpine:3")

        volmounts = cert_copier["volumeMounts"]

        volmounts_expected = [
            {"name": "hostcerts", "mountPath": "/host-trust-store"},
            {
                "name": "private-ca-cert-foo",
                "mountPath": "/private-ca-certs/private-ca-cert-foo.crt",
                "subPath": "cert.pem",
            },
            {
                "name": "private-ca-cert-bar",
                "mountPath": "/private-ca-certs/private-ca-cert-bar.crt",
                "subPath": "cert.pem",
            },
        ]

        assert volmounts == volmounts_expected

    def test_privateca_daemonset_enabled_with_custom_image(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                        "certCopier": {
                            "repository": "snarks",
                            "tag": "boojums",
                        },
                    }
                }
            },
        )

        assert len(docs) == 1
        doc = docs[0]
        self.common_tests_daemonset(doc)
        spec = doc["spec"]["template"]["spec"]

        assert len(spec["containers"]) == 1
        assert spec["containers"][0]["image"] == "snarks:boojums"
