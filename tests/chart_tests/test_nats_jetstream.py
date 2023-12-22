from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import yaml


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestNatsJetstream:
    def test_nats_statefulset_with_jetstream(self, kube_version):
        """Test that nats statefulset is good with defaults."""
        values = {
            "global": {"nats": {"jetStream": {"enabled": True}}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
                "charts/nats/templates/statefulset.yaml",
                "charts/nats/templates/configmap.yaml",
                "charts/nats/templates/jetstream-job.yaml",
            ],
        )

        assert len(docs) == 7
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        assert prod["nats"] == {"jetStreamEnabled": True, "tlsEnabled": False}
        nats_cm = docs[2]["data"]["nats.conf"]
        assert "jetstream" in nats_cm

    def test_nats_statefulset_with_jetstream_and_tls(self, kube_version):
        """Test Nats with jetstream config."""
        values = {
            "global": {"nats": {"jetStream": {"enabled": True, "tls": True}}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
                "charts/nats/templates/statefulset.yaml",
                "charts/nats/templates/configmap.yaml",
                "charts/nats/templates/jetstream-job.yaml",
                "charts/nats/templates/nats-jetstream-tls-secret.yaml",
            ],
        )

        assert len(docs) == 9
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        assert prod["nats"] == {
            "jetStreamEnabled": True,
            "tlsEnabled": True,
            "tls": {
                "caFile": "/etc/houston/jetstream/tls/release-name-jetstream-tls-certificate/ca.crt",
                "certFile": "/etc/houston/jetstream/tls/release-name-jetstream-tls-certificate/tls.crt",
                "keyFile": "/etc/houston/jetstream/tls/release-name-jetstream-tls-certificate/tls.key",
            },
        }
        nats_cm = docs[2]["data"]["nats.conf"]
        assert "jetstream" in nats_cm
        assert docs[7]["metadata"]["name"] == "release-name-jetstream-tls-certificate"
        assert (
            docs[8]["metadata"]["name"]
            == "release-name-jetstream-tls-certificate-houston"
        )
