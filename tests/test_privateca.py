from tests.helm_template_generator import render_chart
import jmespath
import pytest
from . import supported_k8s_versions
from subprocess import CalledProcessError


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestDaemonset:
    @staticmethod
    def common_tests_daemonset(doc):
        """Test things common to all daemonsets"""
        assert "DaemonSet" == jmespath.search("kind", doc)
        assert "RELEASE-NAME-private-ca" == jmespath.search("metadata.name", doc)
        assert "cert-copy" == jmespath.search(
            "spec.template.spec.containers[0].name", doc
        )

    def test_privateca_daemonset_disabled(self, kube_version):
        with pytest.raises(CalledProcessError):
            render_chart(
                kube_version=kube_version,
                show_only=["templates/trust-private-ca-on-all-nodes/daemonset.yaml"],
                values={
                    "global": {
                        "privateCaCertsAddToHost": {
                            "enabled": False,
                        }
                    }
                },
            )

    def test_privateca_daemonset_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["templates/trust-private-ca-on-all-nodes/daemonset.yaml"],
            values={
                "global": {
                    "privateCaCertsAddToHost": {
                        "enabled": True,
                    }
                }
            },
        )

        assert len(docs) == 1
        doc = docs[0]
        self.common_tests_daemonset(doc)
        assert any(
            "alpine:3.14" in item
            for item in jmespath.search("spec.template.spec.containers[*].image", doc)
        )

    def test_privateca_daemonset_enabled_with_custom_image(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["templates/trust-private-ca-on-all-nodes/daemonset.yaml"],
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
        assert any(
            "snarks:boojums" in item
            for item in jmespath.search("spec.template.spec.containers[*].image", doc)
        )


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPSP:
    def test_privateca_psp_enabled_cacertaddtohost_disabled(self, kube_version):
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

        assert len(docs) == 1
        doc = docs[0]
        assert "PodSecurityPolicy" == jmespath.search("kind", doc)
        assert "RELEASE-NAME-private-ca" == jmespath.search("metadata.name", doc)
