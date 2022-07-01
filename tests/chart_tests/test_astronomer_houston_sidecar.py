import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart

chart_values = {
    "astronomer": {
        "houston": {
            "command": ["/bin/sh"],
            "apiArgs": [
                "-c",
                "yarn serve 1> >( tee -a /var/log/houston/data.out.log ) 2> >( tee -a /var/log/houston/data.err.log >&2 )",
            ],
            "volumeMounts": [{"name": "logvol", "mountPath": "/var/log/houston"}],
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
            "worker": {
                "command": ["/bin/sh"],
                "args": [
                    "-c",
                    "yarn worker 1> >( tee -a /var/log/houston_worker/data.out.log ) 2> >( tee -a /var/log/houston_worker/data.err.log >&2 )",
                ],
                "volumeMounts": [
                    {"name": "logvol", "mountPath": "/var/log/houston_worker"}
                ],
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
        },
        "commander": {
            "command": ["/bin/sh"],
            "args": [
                "-c",
                "commander  1> >( tee -a /var/log/commander/out.log ) 2> >( tee -a /var/log/commander/err.log >&2 )",
            ],
            "volumeMounts": [{"name": "logvol", "mountPath": "/var/log/commander"}],
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


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerFileLogs:
    def fleuntd_container(self, container):
        assert container["image"] == "ap-fluentd:0.5"
        assert len(container["volumeMounts"]) == 1

    def houston_container(self, container, run_type):

        assert container["command"] == ["/bin/sh"]
        assert container["args"] == [
            "-c",
            "yarn serve"
            + " 1> >( tee -a /var/log/houston/data.out.log ) 2> >( tee -a /var/log/houston/data.err.log >&2 )",
        ]

        volume_mounts = container["volumeMounts"]
        for volume in volume_mounts:
            if volume["name"] == "logvol":
                assert volume["mountPath"] == "/var/log/houston"

    def houston_worker_container(self, container):

        assert container["command"] == ["/bin/sh"]
        assert container["args"] == [
            "-c",
            "yarn worker"
            + " 1> >( tee -a /var/log/houston_worker/data.out.log ) 2> >( tee -a /var/log/houston_worker/data.err.log >&2 )",
        ]

        volume_mounts = container["volumeMounts"]
        for volume in volume_mounts:
            if volume["name"] == "logvol":
                assert volume["mountPath"] == "/var/log/houston_worker"

    def commander_container(self, container):
        assert container["command"] == ["/bin/sh"]
        assert container["args"] == [
            "-c",
            "commander  1> >( tee -a /var/log/commander/out.log ) 2> >( tee -a /var/log/commander/err.log >&2 )",
        ]

        volume_mounts = container["volumeMounts"]
        for volume in volume_mounts:
            if volume["name"] == "logvol":
                assert volume["mountPath"] == "/var/log/commander"

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
                        self.houston_container(container=container)
                    elif container["name"] == "fluentd":
                        self.fleuntd_container(container=container)

                elif name == "astro-file-logs-houston-worker":

                    if container["name"] == "houston":
                        self.houston_worker_container(container=container)
                    elif container["name"] == "fluentd":
                        self.fleuntd_container(container)

                elif name == "astro-file-logs-commander":
                    if container["name"] == "commander":
                        self.commander_container(container)
                    elif container["name"] == "fluentd":
                        self.fleuntd_container(container)

            # Test volumes
            volumes = doc["spec"]["template"]["spec"]["volumes"]
            for volume in volumes:
                if volume["name"] == "logvol":
                    assert volume["emptyDir"] == {}
