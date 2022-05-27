import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart

chart_values = {
    "astronomer": {
        "houston": {
            "enableFileLogs": True,
            "volumeMounts": [{"name": "logvol", "mountPath": "/var/logs/houston"}],
            "extraContainers": [
                {
                    "name": "fluentd",
                    "image": "ap-fluentd:0.5",
                    "imagePullPolicy": "Never",
                    "volumeMounts": [
                        {"name": "logvol", "mountPath": "/var/log/file_logs/"}
                    ],
                }
            ],
            "extraVolumes": [{"name": "logvol", "emptyDir": {}}],
        },
        "commander": {
            "volumeMounts": [{"name": "logvol", "mountPath": "/var/logs/commander"}],
            "extraContainers": [
                {
                    "name": "fluentd",
                    "image": "ap-fluentd:0.5",
                    "imagePullPolicy": "Never",
                    "volumeMounts": [
                        {"name": "logvol", "mountPath": "/var/log/file_logs/"}
                    ],
                }
            ],
            "extraVolumes": [{"name": "logvol", "emptyDir": {}}],
        },
    }
}


class TestAstronomerFileLogs:
    def fleuntd_container(self, container):
        assert container["image"] == "ap-fluentd:0.5"
        assert len(container["volumeMounts"]) == 1

    def test_houston_container(self, container, run_type):
        assert container["args"] == [
            "sh",
            "-c",
            "yarn "
            + run_type
            + " 1> >( tee -a /var/logs/houston/data.out.log ) 2> >( tee -a /var/logs/houston/data.err.log >&2 )",
        ]

        volume_mounts = container["volumeMounts"]
        for volume in volume_mounts:
            if volume["name"] == "logvol":
                assert volume["mountPath"] == "/var/logs/houston"

    @pytest.mark.parametrize(
        "kube_version",
        supported_k8s_versions,
    )
    def test_file_logs_config(self, kube_version):
        docs = render_chart(
            "astro-file-logs",
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/commander/commander-deployment.yaml",
            ],
            values=chart_values,
        )

        assert len(docs) == 3

        for doc in docs:
            assert doc["kind"] == "Deployment"
            name = doc["metadata"]["name"]

            # Test containers
            containers = doc["spec"]["template"]["spec"]["containers"]
            assert len(containers) == 2

            for container in containers:

                if name == "astro-file-logs-houston":

                    if container["name"] == "houston":
                        self.houston_container(container=container, run_type="serve")
                    elif container["name"] == "fluentd":
                        self.fleuntd_container(container=container)

                elif name == "astro-file-logs-houston-worker":

                    if container["name"] == "houston":
                        self.houston_container(container, "worker")
                    elif container["name"] == "fluentd":
                        self.fleuntd_container(container)

            # Test volumes
            volumes = doc["spec"]["template"]["spec"]["volumes"]
            for volume in volumes:
                if volume["name"] == "logvol":
                    assert volume["emptyDir"] == {}
