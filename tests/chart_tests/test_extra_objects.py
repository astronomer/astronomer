import json
from subprocess import CalledProcessError

import pytest

from tests.chart_tests.helm_template_generator import render_chart
from .. import supported_k8s_versions


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExtraObjects:
    def test_extra_objects_defaults(self, kube_version):
        """Test that extra-objects works as default."""
        with pytest.raises(CalledProcessError):
            render_chart(
                kube_version=kube_version,
                values={"astronomer": {"extraObjects": []}},
                show_only=["charts/astronomer/templates/extra-objects.yaml"],
            )

    def test_extra_objects_configured(self, kube_version):
        """Test that extra-objects works as default."""

        eo1 = json.loads(
            """{"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata":
            {"name": "minimal-ingress", "annotations": {"nginx.ingress.kubernetes.io/rewrite-target": "/"}},
            "spec": {"ingressClassName": "nginx-example", "rules": [{"http": {"paths": [{"path": "/testpath",
            "pathType": "Prefix", "backend": {"service": {"name": "test", "port": {"number": 80}}}}]}}]}}"""
        )
        eo2 = json.loads(
            """{"apiVersion":"storage.k8s.io/v1","kind":"StorageClass","metadata":
            {"name":"gluster-vol-default"},"provisioner":"kubernetes.io/glusterfs","parameters":
            {"resturl":"http://192.168.10.100:8080","restuser":"","secretNamespace":"","secretName":""},
            "allowVolumeExpansion":true}"""
        )

        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"extraObjects": [eo1, eo2]}},
            show_only=["charts/astronomer/templates/extra-objects.yaml"],
        )
        assert len(docs) == 2
        assert eo1 in docs
        assert eo2 in docs
