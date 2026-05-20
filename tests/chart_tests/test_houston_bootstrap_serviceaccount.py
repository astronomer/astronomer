import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonBootstrapServiceAccount:
    def test_houston_bootstrap_serviceaccount_defaults(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-bootstrap-serviceaccount.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "ServiceAccount"
        assert "annotations" in doc["metadata"]
        assert doc["automountServiceAccountToken"] is True

    def test_houston_bootstrap_serviceaccount_automount_overrides(self, kube_version):
        """Test that the houston serviceaccount automountServiceAccountToken field is set to false overriding the defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-bootstrap-serviceaccount.yaml"],
            values={
                "astronomer": {
                    "houston": {
                        "serviceAccount": {
                            "automountServiceAccountToken": False,
                        },
                    },
                },
            },
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "ServiceAccount"
        assert "annotations" in doc["metadata"]
        assert doc["automountServiceAccountToken"] is False
