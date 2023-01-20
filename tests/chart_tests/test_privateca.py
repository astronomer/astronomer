from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
from subprocess import CalledProcessError


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
        assert len(docs[0]["spec"]["template"]["spec"]["containers"]) == 1
        assert (
            doc["spec"]["template"]["spec"]["containers"][0]["image"]
            == "snarks:boojums"
        )


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrivateCaPsp:
    def test_privateca_psp_enabled_cacertaddtohost_disabled(self, kube_version):
        """Test that there is nothing rendered when psp is enabled and
        privateCaCertsAddToHost is disabled."""
        with pytest.raises(CalledProcessError):
            render_chart(
                kube_version=kube_version,
                show_only=["templates/trust-private-ca-on-all-nodes/psp.yaml"],
                values={
                    "global": {
                        "pspEnabled": True,
                        "privateCaCertsAddToHost": {
                            "enabled": False,
                        },
                    }
                },
            )

    def test_privateca_psp_disabled_cacertaddtohost_enabled(self, kube_version):
        """Test that nothing is rendered when psp is disabled and
        privateCaCertsAddToHost is enabled."""
        with pytest.raises(CalledProcessError):
            render_chart(
                kube_version=kube_version,
                show_only=["templates/trust-private-ca-on-all-nodes/psp.yaml"],
                values={
                    "global": {
                        "pspEnabled": False,
                        "privateCaCertsAddToHost": {
                            "enabled": True,
                        },
                    }
                },
            )

    def test_privateca_psp_enabled(self, kube_version):
        """Test that psp is rendered when psp is enabled and
        privateCaCertsAddToHost is enabled."""

        _, minor, _ = (int(x) for x in kube_version.split("."))
        if minor >= 25:
            assert ValueError("PSP is not supported in k8s 1.25+")
        else:
            docs = render_chart(
                kube_version=kube_version,
                show_only=["templates/trust-private-ca-on-all-nodes/psp.yaml"],
                values={
                    "global": {
                        "pspEnabled": True,
                        "privateCaCertsAddToHost": {
                            "enabled": True,
                        },
                    }
                },
            )
            assert all(x["kind"] == "PodSecurityPolicy" for x in docs)
            assert len(docs) == 1
            assert docs[0]["kind"] == "PodSecurityPolicy"
            assert docs[0]["metadata"]["name"] == "release-name-private-ca"
