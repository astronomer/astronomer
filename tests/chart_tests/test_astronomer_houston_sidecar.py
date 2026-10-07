import re
from subprocess import CalledProcessError

import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart

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
                    "name": "vector",
                    "image": "ap-vector:0.5",
                    "imagePullPolicy": "Never",
                    "volumeMounts": [{"name": "logvol", "mountPath": "/var/log/file_logs/"}],
                }
            ],
            "extraVolumes": [{"name": "logvol", "emptyDir": {}}],
            "worker": {
                "command": ["/bin/sh"],
                "args": [
                    "-c",
                    "yarn worker 1> >( tee -a /var/log/houston_worker/data.out.log ) 2> >( tee -a /var/log/houston_worker/data.err.log >&2 )",
                ],
                "volumeMounts": [{"name": "logvol", "mountPath": "/var/log/houston_worker"}],
                "extraContainers": [
                    {
                        "name": "vector",
                        "image": "ap-vector:0.5",
                        "imagePullPolicy": "Never",
                        "volumeMounts": [{"name": "logvol", "mountPath": "/var/log/file_logs/"}],
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
                    "name": "vector",
                    "image": "ap-vector:0.5",
                    "imagePullPolicy": "Never",
                    "volumeMounts": [{"name": "logvol", "mountPath": "/var/log/file_logs/"}],
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
        assert container["image"] == "ap-vector:0.5"
        assert len(container["volumeMounts"]) == 1

    def houston_container(self, container):
        assert container["command"] == ["/bin/sh"]
        assert container["args"] == [
            "-c",
            "yarn serve" + " 1> >( tee -a /var/log/houston/data.out.log ) 2> >( tee -a /var/log/houston/data.err.log >&2 )",
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
            name="astro-file-logs",
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
                    elif container["name"] == "vector":
                        self.fleuntd_container(container=container)

                elif name == "astro-file-logs-houston-worker":
                    if container["name"] == "houston-worker":
                        self.houston_worker_container(container=container)
                    elif container["name"] == "vector":
                        self.fleuntd_container(container)

                elif name == "astro-file-logs-commander":
                    if container["name"] == "commander":
                        self.commander_container(container)
                    elif container["name"] == "vector":
                        self.fleuntd_container(container)

            # Test volumes
            volumes = doc["spec"]["template"]["spec"]["volumes"]
            for volume in volumes:
                if volume["name"] == "logvol":
                    assert volume["emptyDir"] == {}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonSidecarLogging:
    def test_houston_sidecar_logging_defaults(self, kube_version):
        docs = render_chart(
            name="houston-sidecar-logging-defaults",
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-vector-configmap.yaml",
            ],
            values={},
        )
        assert len(docs) == 2
        for doc in docs:
            assert doc["kind"] == "Deployment"
            containers = doc["spec"]["template"]["spec"]["containers"]
            assert len(containers) == 1

    def test_houston_sidecar_logging_enabled(self, kube_version):
        resource_defaults = {
            "limits": {
                "memory": "256Mi",
                "cpu": "200m",
            },
            "requests": {
                "memory": "128Mi",
                "cpu": "50m",
            },
        }
        # PINF-1067: capabilities.drop has no pod-level fallback in Kubernetes, so this
        # sidecar's own securityContext must set it explicitly for PSS-Restricted -
        # unlike seccompProfile, which the pod-level securityContext already covers.
        security_context_defaults = {
            "runAsNonRoot": True,
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsUser": 65532,
            "capabilities": {"drop": ["ALL"]},
        }
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-vector-configmap.yaml",
            ],
            values={
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "cloudwatch": {
                                    "enabled": True,
                                },
                            },
                        },
                    }
                }
            },
        )

        assert len(docs) == 4
        # Test houston deployment sidecar
        c_by_name = get_containers_by_name(docs[0])
        assert len(c_by_name) == 2
        assert "vector" in c_by_name
        assert c_by_name["vector"]["image"].startswith("quay.io/astronomer/ap-vector:")
        assert c_by_name["vector"]["resources"] == resource_defaults
        assert c_by_name["vector"]["securityContext"] == security_context_defaults

        # Test houston worker deployment sidecar
        c_by_name = get_containers_by_name(docs[1])
        assert len(c_by_name) == 2
        assert "vector" in c_by_name
        assert c_by_name["vector"]["image"].startswith("quay.io/astronomer/ap-vector:")
        assert c_by_name["vector"]["resources"] == resource_defaults
        assert c_by_name["vector"]["securityContext"] == security_context_defaults

    def test_houston_sidecar_logging_rejects_multiple_sinks(self, kube_version):
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(
                kube_version=kube_version,
                show_only=[
                    "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
                ],
                values={
                    "astronomer": {
                        "houston": {
                            "logging": {
                                "loggingSidecar": {
                                    "enabled": True,
                                    "cloudwatch": {
                                        "enabled": True,
                                        "region": "us-east-2",
                                    },
                                    "elasticsearch": {
                                        "enabled": True,
                                        "endpoint": "https://es.example.com:9200",
                                    },
                                },
                            },
                        }
                    }
                },
            )
        stderr = excinfo.value.stderr.decode("utf-8")
        assert "houston.logging.loggingSidecar supports exactly one sink at a time" in stderr

    def test_houston_sidecar_logging_requires_at_least_one_sink(self, kube_version):
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(
                kube_version=kube_version,
                show_only=[
                    "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                ],
                values={
                    "astronomer": {
                        "houston": {
                            "logging": {
                                "loggingSidecar": {
                                    "enabled": True,
                                }
                            }
                        }
                    }
                },
            )
        stderr = excinfo.value.stderr.decode("utf-8")
        assert "houston.logging.loggingSidecar.enabled requires at least one supported sink" in stderr
        assert "extraSinks" not in stderr

    def test_houston_sidecar_logging_elasticsearch_requires_endpoint(self, kube_version):
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(
                kube_version=kube_version,
                show_only=[
                    "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                ],
                values={
                    "astronomer": {
                        "houston": {
                            "logging": {
                                "loggingSidecar": {
                                    "enabled": True,
                                    "elasticsearch": {
                                        "enabled": True,
                                    },
                                },
                            },
                        }
                    }
                },
            )
        assert "houston.logging.loggingSidecar.elasticsearch.endpoint must be set" in excinfo.value.stderr.decode("utf-8")

    def test_houston_log_wrapper_refreshes_ca_certificates(self, kube_version):
        """
        The shared log-wrapper ConfigMap must run update-ca-certificates so
        certs from global.privateCaCerts are trusted by Node
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-log-wrapper-configmap.yaml",
            ],
            values={
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "cloudwatch": {"enabled": True, "region": "us-east-2"},
                            },
                        },
                    }
                }
            },
        )

        assert len(docs) == 1
        wrapper_sh = docs[0]["data"]["wrapper.sh"]

        marker_idx = wrapper_sh.find('echo "update ca certs on startup..."')
        update_idx = wrapper_sh.find("update-ca-certificates")
        exec_idx = wrapper_sh.find('exec "$@"')

        assert marker_idx != -1, "startup marker missing from wrapper.sh"
        assert update_idx != -1, "update-ca-certificates missing from wrapper.sh"
        assert exec_idx != -1, "exec line missing from wrapper.sh"
        assert marker_idx < update_idx < exec_idx, "wrapper.sh must echo the marker and run update-ca-certificates before exec"

    def test_houston_log_wrapper_not_rendered_when_sidecar_disabled(self, kube_version):
        """
        The log-wrapper ConfigMap should only render when the sidecar is enabled.
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-log-wrapper-configmap.yaml",
            ],
            values={},
        )
        assert len(docs) == 0

    def test_houston_sidecar_logging_elasticsearch_uses_explicit_endpoint(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-vector-configmap.yaml",
            ],
            values={
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "elasticsearch": {
                                    "enabled": True,
                                    "endpoint": "https://es.example.com:9200",
                                    "auth": {
                                        "strategy": "basic",
                                        "secretName": "houston-elasticsearch-creds",
                                    },
                                },
                            },
                        },
                    }
                }
            },
        )

        deployments = [doc for doc in docs if doc["kind"] == "Deployment"]
        configmaps = [doc for doc in docs if doc["kind"] == "ConfigMap"]
        assert len(deployments) == 2
        assert len(configmaps) == 2

        for deployment in deployments:
            vector = get_containers_by_name(deployment)["vector"]
            vector_env = {env_var["name"] for env_var in vector["env"]}

            # Vector 0.57+ does not interpolate env vars in config, so credentials are
            # mounted from the secret and read through Vector's secrets backend.
            assert not vector_env & {"ES_ENDPOINT", "ES_USERNAME", "ES_PASSWORD"}

            mounts = {mount["name"]: mount for mount in vector["volumeMounts"]}
            assert mounts["es-creds"]["mountPath"] == "/etc/vector/secrets/elasticsearch"
            assert mounts["es-creds"]["readOnly"] is True

            volumes = {volume["name"]: volume for volume in deployment["spec"]["template"]["spec"]["volumes"]}
            assert volumes["es-creds"]["secret"]["secretName"] == "houston-elasticsearch-creds"
            assert volumes["es-creds"]["secret"]["items"] == [
                {"key": "username", "path": "username"},
                {"key": "password", "path": "password"},
            ]

        for configmap in configmaps:
            vector_config = configmap["data"]["vector.yaml"]
            assert 'endpoints: ["https://es.example.com:9200"]' in vector_config
            assert "strategy: basic" in vector_config
            assert "${" not in vector_config

            parsed = yaml.safe_load(vector_config)
            assert parsed["secret"] == {
                "es_creds": {
                    "type": "directory",
                    "path": "/etc/vector/secrets/elasticsearch",
                    "remove_trailing_whitespace": True,
                }
            }
            assert parsed["sinks"]["elasticsearch"]["auth"] == {
                "strategy": "basic",
                "user": "SECRET[es_creds.username]",
                "password": "SECRET[es_creds.password]",
            }

            # `vector validate` never resolves secrets, but Vector exits at startup if the directory
            # or a referenced key is missing, so the config and the pod spec must agree.
            referenced_keys = {ref.split(".", 1)[1].rstrip("]") for ref in re.findall(r"SECRET\[es_creds\.[^\]]+\]", vector_config)}
            for deployment in deployments:
                vector = get_containers_by_name(deployment)["vector"]
                mount = next(m for m in vector["volumeMounts"] if m["name"] == "es-creds")
                volume = next(v for v in deployment["spec"]["template"]["spec"]["volumes"] if v["name"] == "es-creds")
                assert mount["mountPath"] == parsed["secret"]["es_creds"]["path"]
                assert referenced_keys == {item["path"] for item in volume["secret"]["items"]}

    def test_houston_sidecar_logging_elasticsearch_without_basic_auth_has_no_credentials(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-vector-configmap.yaml",
            ],
            values={
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "elasticsearch": {
                                    "enabled": True,
                                    "endpoint": "https://es.example.com:9200",
                                    "auth": {"strategy": "none"},
                                },
                            },
                        },
                    }
                }
            },
        )

        for doc in docs:
            if doc["kind"] == "Deployment":
                vector = get_containers_by_name(doc)["vector"]
                assert "es-creds" not in {mount["name"] for mount in vector["volumeMounts"]}
                assert "es-creds" not in {volume["name"] for volume in doc["spec"]["template"]["spec"]["volumes"]}
            else:
                parsed = yaml.safe_load(doc["data"]["vector.yaml"])
                assert "secret" not in parsed
                assert "auth" not in parsed["sinks"]["elasticsearch"]

    def test_houston_sidecar_logging_cloudwatch_static_credentials_use_secrets_backend(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-vector-configmap.yaml",
            ],
            values={
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "cloudwatch": {
                                    "enabled": True,
                                    "region": "us-east-2",
                                    "useIRSA": False,
                                    "secretName": "houston-cloudwatch-creds",
                                },
                            },
                        },
                    }
                }
            },
        )

        deployments = [doc for doc in docs if doc["kind"] == "Deployment"]
        configmaps = [doc for doc in docs if doc["kind"] == "ConfigMap"]
        assert len(deployments) == 2
        assert len(configmaps) == 2

        for configmap in configmaps:
            vector_config = configmap["data"]["vector.yaml"]
            assert "${" not in vector_config

            parsed = yaml.safe_load(vector_config)
            assert parsed["secret"] == {
                "aws_creds": {
                    "type": "directory",
                    "path": "/etc/vector/secrets/cloudwatch",
                    "remove_trailing_whitespace": True,
                }
            }
            assert parsed["sinks"]["cloudwatch"]["auth"] == {
                "access_key_id": "SECRET[aws_creds.aws_access_key_id]",
                "secret_access_key": "SECRET[aws_creds.aws_secret_access_key]",
            }

            referenced_keys = {
                ref.split(".", 1)[1].rstrip("]") for ref in re.findall(r"SECRET\[aws_creds\.[^\]]+\]", vector_config)
            }
            for deployment in deployments:
                vector = get_containers_by_name(deployment)["vector"]
                mount = next(m for m in vector["volumeMounts"] if m["name"] == "aws-creds")
                volume = next(v for v in deployment["spec"]["template"]["spec"]["volumes"] if v["name"] == "aws-creds")
                assert mount["mountPath"] == parsed["secret"]["aws_creds"]["path"]
                assert mount["readOnly"] is True
                assert volume["secret"]["secretName"] == "houston-cloudwatch-creds"
                assert referenced_keys == {item["path"] for item in volume["secret"]["items"]}

        for deployment in deployments:
            vector_env = {env_var["name"]: env_var for env_var in get_containers_by_name(deployment)["vector"]["env"]}
            assert vector_env["AWS_REGION"]["value"] == "us-east-2"
            assert not vector_env.keys() & {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}

    def test_houston_sidecar_logging_cloudwatch_irsa_has_no_credentials(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-vector-configmap.yaml",
            ],
            values={
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "cloudwatch": {"enabled": True, "region": "us-east-2", "useIRSA": True},
                            },
                        },
                    }
                }
            },
        )

        assert len(docs) == 4
        for doc in docs:
            if doc["kind"] == "Deployment":
                vector = get_containers_by_name(doc)["vector"]
                assert "aws-creds" not in {mount["name"] for mount in vector["volumeMounts"]}
                assert "aws-creds" not in {volume["name"] for volume in doc["spec"]["template"]["spec"]["volumes"]}
            else:
                parsed = yaml.safe_load(doc["data"]["vector.yaml"])
                assert "secret" not in parsed
                assert "auth" not in parsed["sinks"]["cloudwatch"]
