import ast

import yaml

from tests.utils.chart import render_chart


def common_test_cases(docs):
    """Test some things that should apply to all cases."""
    assert len(docs) == 1

    doc = docs[0]

    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
    assert doc["metadata"]["name"] == "release-name-houston-config"

    local_prod = yaml.safe_load(doc["data"]["local-production.yaml"])

    assert local_prod == {"nats": {"ackWait": 600000}}

    prod = yaml.safe_load(doc["data"]["production.yaml"])

    assert prod["deployments"]["helm"]["airflow"]["useAstroSecurityManager"] is True
    assert "disableManageClusterScopedResources" not in prod["deployments"]
    assert prod["helm"]["tlsSecretName"] == "astronomer-tls"
    airflow_local_settings = prod["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    scheduler_update_strategy = prod["deployments"]["helm"]["airflow"]["scheduler"]["strategy"]
    assert scheduler_update_strategy["type"] == "RollingUpdate"
    assert scheduler_update_strategy["rollingUpdate"]["maxUnavailable"] == 1
    assert (
        prod["deployments"]["helm"]["airflow"]["cleanup"]["schedule"]
        == '{{- add 3 (regexFind ".$" (adler32sum .Release.Name)) -}}-59/15 * * * *'
    )

    # validate yaml-embedded python
    ast.parse(airflow_local_settings.encode())


def test_houston_configmap_defaults():
    """Validate the houston configmap and its default embedded data."""
    docs = render_chart(
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])
    # Ensure airflow elasticsearch param is at correct location
    assert prod["deployments"]["helm"]["airflow"]["elasticsearch"]["enabled"] is True
    # Ensure elasticsearch client param is at the correct location and contains http://
    assert "node" in prod["elasticsearch"]["client"]
    assert prod["elasticsearch"]["client"]["node"].startswith("http://")

    assert not prod["deployments"].get("authSideCar")
    assert not prod["deployments"].get("loggingSidecar")

    af_images = prod["deployments"]["helm"]["airflow"]["images"]
    git_sync_images = prod["deployments"]["helm"]["gitSyncRelay"]["images"]

    assert af_images["statsd"]["tag"]
    assert af_images["redis"]["tag"]
    assert af_images["pgbouncer"]["tag"]
    assert af_images["pgbouncerExporter"]["tag"]
    assert af_images["gitSync"]["tag"]

    assert af_images["statsd"]["repository"] == "quay.io/astronomer/ap-statsd-exporter"
    assert af_images["redis"]["repository"] == "quay.io/astronomer/ap-redis"
    assert af_images["pgbouncer"]["repository"] == "quay.io/astronomer/ap-pgbouncer"
    assert af_images["pgbouncerExporter"]["repository"] == "quay.io/astronomer/ap-pgbouncer-exporter"
    assert af_images["gitSync"]["repository"] == "quay.io/astronomer/ap-git-sync"
    assert git_sync_images["gitDaemon"]["repository"] == "quay.io/astronomer/ap-git-daemon"
    assert git_sync_images["gitSync"]["repository"] == "quay.io/astronomer/ap-git-sync-relay"
    assert prod["deployments"]["helm"]["sccEnabled"] is False


def test_houston_configmap_with_custom_images():
    """Validate the houston configmap contains images that are customized through helm values."""
    values = {
        "global": {
            "airflow": {
                "images": {
                    "gitSync": {"repository": "custom-registry/example/ap-git-sync", "tag": "git-sync-999"},
                    "pgbouncer": {"repository": "custom-registry/example/ap-pgbouncer", "tag": "pgbouncer-999"},
                    "pgbouncerExporter": {
                        "repository": "custom-registry/example/ap-pgbouncer-exporter",
                        "tag": "pgbouncer-exporter-999",
                    },
                    "redis": {"repository": "custom-registry/example/ap-redis", "tag": "redis-999"},
                    "statsd": {"repository": "custom-registry/example/ap-statsd-exporter", "tag": "statsd-999"},
                }
            },
            "gitSyncRelay": {
                "images": {
                    "gitDaemon": {"repository": "custom-registry/example/ap-git-daemon", "tag": "git-daemon-999"},
                    "gitSync": {"repository": "custom-registry/example/ap-git-sync-relay", "tag": "git-sync-999"},
                }
            },
        }
    }

    docs = render_chart(values=values, show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"])

    common_test_cases(docs)
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])

    af_images = prod["deployments"]["helm"]["airflow"]["images"]
    git_sync_images = prod["deployments"]["helm"]["gitSyncRelay"]["images"]

    assert af_images["statsd"]["tag"] == "statsd-999"
    assert af_images["redis"]["tag"] == "redis-999"
    assert af_images["pgbouncer"]["tag"] == "pgbouncer-999"
    assert af_images["pgbouncerExporter"]["tag"] == "pgbouncer-exporter-999"
    assert af_images["gitSync"]["tag"] == "git-sync-999"
    assert git_sync_images["gitDaemon"]["tag"] == "git-daemon-999"
    assert git_sync_images["gitSync"]["tag"] == "git-sync-999"

    assert af_images["statsd"]["repository"] == "custom-registry/example/ap-statsd-exporter"
    assert af_images["redis"]["repository"] == "custom-registry/example/ap-redis"
    assert af_images["pgbouncer"]["repository"] == "custom-registry/example/ap-pgbouncer"
    assert af_images["pgbouncerExporter"]["repository"] == "custom-registry/example/ap-pgbouncer-exporter"
    assert af_images["gitSync"]["repository"] == "custom-registry/example/ap-git-sync"
    assert git_sync_images["gitDaemon"]["repository"] == "custom-registry/example/ap-git-daemon"
    assert git_sync_images["gitSync"]["repository"] == "custom-registry/example/ap-git-sync-relay"


def test_houston_configmap_with_namespaceFreeFormEntry_true():
    """Validate the houston configmap's embedded data with
    namespaceFreeFormEntry=True."""

    docs = render_chart(
        values={"global": {"namespaceFreeFormEntry": True}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
    assert prod["deployments"]["namespaceFreeFormEntry"] is True


def test_houston_configmap_with_namespaceFreeFormEntry_defaults():
    """Validate the houston configmap's embedded data with
    namespaceFreeFormEntry defaults."""
    docs = render_chart(
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
    assert prod["deployments"]["namespaceFreeFormEntry"] is False


def test_houston_configmap_with_customlogging_enabled():
    """Validate the houston configmap and its embedded data with
    customLogging."""
    docs = render_chart(
        values={"global": {"customLogging": {"enabled": True}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])

    assert "node" in prod["elasticsearch"]["client"]
    assert prod["elasticsearch"]["client"]["node"].startswith("http://") is True


def test_houston_configmapwith_scc_enabled():
    """Validate the houston configmap and its embedded data with sscEnabled."""
    docs = render_chart(
        values={"global": {"sccEnabled": True}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])

    assert prod["deployments"]["helm"]["sccEnabled"] is True


def test_houston_configmap_with_azure_enabled():
    """Validate the houston configmap and its embedded data with azure
    enabled."""
    docs = render_chart(
        values={"global": {"azure": {"enabled": True}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])

    assert prod["deployments"]["helm"]["sccEnabled"] is False

    livenessProbe = prod["deployments"]["helm"]["airflow"]["webserver"]["livenessProbe"]
    assert livenessProbe["failureThreshold"] == 25
    assert livenessProbe["periodSeconds"] == 10


def test_houston_configmap_with_config_syncer_enabled():
    """Validate the houston configmap and its embedded data with configSyncer
    enabled."""
    docs = render_chart(
        values={"astronomer": {"configSyncer": {"enabled": True}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod["deployments"]["helm"]["airflow"]["webserver"]["extraVolumeMounts"] == [
        {
            "name": "signing-certificate",
            "mountPath": "/etc/airflow/tls",
            "readOnly": True,
        }
    ]
    assert prod["deployments"]["helm"]["airflow"]["webserver"]["extraVolumes"] == [
        {
            "name": "signing-certificate",
            "secret": {"secretName": "release-name-houston-jwt-signing-certificate"},
        }
    ]


def test_houston_configmap_with_config_syncer_disabled():
    """Validate the houston configmap and its embedded data with configSyncer
    disabled."""
    docs = render_chart(
        values={"astronomer": {"configSyncer": {"enabled": False}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert "extraVolumeMounts" not in prod_yaml["deployments"]["helm"]["airflow"]["webserver"]
    assert "extraVolumes" not in prod_yaml["deployments"]["helm"]["airflow"]["webserver"]
    assert not prod_yaml["deployments"].get("loggingSidecar")


def test_houston_configmap_with_vector_index_prefix_defaults():
    """Validate the houston configmap and its embedded data with configSyncer
    disabled."""
    docs = render_chart(
        values={},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert "fluentd" in prod_yaml["deployments"].get("fluentdIndexPrefix")


def test_houston_configmap_with_vector_index_prefix_overrides():
    """Validate the houston configmap and its embedded data with configSyncer
    disabled."""
    docs = render_chart(
        values={"global": {"logging": {"indexNamePrefix": "astronomer"}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert "astronomer" in prod_yaml["deployments"].get("fluentdIndexPrefix")


def test_houston_configmap_with_loggingsidecar_enabled():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "repository": "quay.io/astronomer/ap-vector",
                    "tag": "0.22.3",
                },
            },
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": "sidecar-log-consumer",
        "image": "quay.io/astronomer/ap-vector:0.22.3",
        "customConfig": False,
    }
    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_index_prefix_overrides():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    image = "registry.example.com/foobar/test-image-name:99.88.77"
    docs = render_chart(
        values={
            "global": {
                "logging": {"indexNamePrefix": "test-index-name-prefix-999"},
                "loggingSidecar": {
                    "enabled": True,
                    "repository": image.split(":")[0],
                    "tag": image.split(":")[1],
                },
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": "sidecar-log-consumer",
        "image": image,
        "customConfig": False,
        "indexNamePrefix": "test-index-name-prefix-999",
    }
    assert image in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_overrides():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    sidecar_container_name = "sidecar-log-test"
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": sidecar_container_name,
                    "repository": "quay.io/astronomer/ap-vector",
                    "tag": "0.22.3",
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": sidecar_container_name,
        "image": "quay.io/astronomer/ap-vector:0.22.3",
        "customConfig": False,
    }
    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_indexPattern():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    sidecar_container_name = "sidecar-log-test"
    image_name = "example.com/some-repo/test-image-name:test-tag-foo"
    indexPattern = "%Y.%m"
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": sidecar_container_name,
                    "repository": image_name.split(":")[0],
                    "tag": image_name.split(":")[1],
                    "indexPattern": indexPattern,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": sidecar_container_name,
        "image": image_name,
        "customConfig": False,
        "indexPattern": indexPattern,
    }


def test_houston_configmap_with_loggingsidecar_customConfig_enabled():
    """Validate the houston configmap and its embedded data with loggingSidecar
    customConfig Enabled."""
    sidecar_container_name = "sidecar-log-test"
    image_name = "quay.io/astronomer/ap-vector:0.22.3"
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": sidecar_container_name,
                    "customConfig": True,
                    "repository": image_name.split(":")[0],
                    "tag": image_name.split(":")[1],
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": sidecar_container_name,
        "image": "quay.io/astronomer/ap-vector:0.22.3",
        "customConfig": True,
    }
    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_custom_env_overrides():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    sidecar_container_name = "sidecar-log-test"
    image_name = "quay.io/astronomer/ap-vector:0.22.3"
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": sidecar_container_name,
                    "repository": image_name.split(":")[0],
                    "tag": image_name.split(":")[1],
                    "extraEnv": [
                        {
                            "name": "ES_USER",
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": "elastic-creds",
                                    "key": "ESUSER",
                                }
                            },
                        },
                        {
                            "name": "ES_PASS",
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": "elastic-creds",
                                    "key": "ESPASS",
                                }
                            },
                        },
                    ],
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": sidecar_container_name,
        "image": "quay.io/astronomer/ap-vector:0.22.3",
        "customConfig": False,
        "extraEnv": [
            {
                "name": "ES_USER",
                "valueFrom": {"secretKeyRef": {"name": "elastic-creds", "key": "ESUSER"}},
            },
            {
                "name": "ES_PASS",
                "valueFrom": {"secretKeyRef": {"name": "elastic-creds", "key": "ESPASS"}},
            },
        ],
    }

    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_resource_overrides():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    sidecar_container_name = "sidecar-log-test"
    image_name = {"repository": "quay.io/astronomer/ap-vector", "tag": "0.22.3"}
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": sidecar_container_name,
                    "repository": f"{image_name['repository']}",
                    "tag": f"{image_name['tag']}",
                    "resources": {
                        "requests": {"memory": "386Mi", "cpu": "100m"},
                        "limits": {"memory": "386Mi", "cpu": "100m"},
                    },
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": sidecar_container_name,
        "image": "quay.io/astronomer/ap-vector:0.22.3",
        "customConfig": False,
        "resources": {
            "requests": {"memory": "386Mi", "cpu": "100m"},
            "limits": {"memory": "386Mi", "cpu": "100m"},
        },
    }

    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_securityContext_configured():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    securityContext = {
        "runAsUser": 1000,
    }
    sidecar_container_name = "sidecar-log-test"
    image_name = "quay.io/astronomer/ap-vector:unittest-tag"
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": sidecar_container_name,
                    "repository": image_name.split(":")[0],
                    "tag": image_name.split(":")[1],
                    "securityContext": securityContext,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": sidecar_container_name,
        "image": "quay.io/astronomer/ap-vector:unittest-tag",
        "customConfig": False,
        "securityContext": securityContext,
    }

    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmapwith_update_airflow_runtime_checks_enabled():
    """Validate the houston configmap and its embedded data with updateRuntimeCheck."""
    docs = render_chart(
        values={
            "astronomer": {
                "houston": {
                    "updateRuntimeCheck": {"enabled": True},
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]

    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod["updateRuntimeCheckEnabled"] is True


def test_houston_configmapwith_update_airflow_runtime_checks_disabled():
    """Validate the houston configmap and its embedded data with updateRuntimeCheck."""
    docs = render_chart(
        values={
            "astronomer": {
                "houston": {
                    "updateRuntimeCheck": {"enabled": False},
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]

    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod["updateRuntimeCheckEnabled"] is False


def test_houston_configmap_with_cleanup_airflow_db_enabled():
    """Validate the houston configmap and its embedded data with
    cleanupAirflowDb."""
    docs = render_chart(
        values={
            "astronomer": {
                "houston": {
                    "cleanupAirflowDb": {
                        "enabled": True,
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]

    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod["deployments"]["cleanupAirflowDb"]["enabled"] is True


def test_houston_configmap_with_cleanup_airflow_db_disabled():
    """Validate the houston configmap and its embedded data with
    cleanupAirflowDb."""
    docs = render_chart(
        values={
            "astronomer": {
                "houston": {
                    "cleanupAirflowDb": {
                        "enabled": False,
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]

    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod["deployments"]["cleanupAirflowDb"]["enabled"] is False


def test_houston_configmap_with_tls_secretname_overrides():
    """Validate the houston configmap and its embedded data with tls secretname overrides
    ."""
    docs = render_chart(
        values={"global": {"tlsSecret": "astro-ssl-secret"}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod["helm"]["tlsSecretName"] == "astro-ssl-secret"


def test_houston_configmap_with_authsidecar_liveness_probe():
    """Validate the authSidecar liveness probe in the Houston configmap."""
    liveness_probe = {
        "httpGet": {"path": "/auth-liveness", "port": 8080, "scheme": "HTTP"},
        "initialDelaySeconds": 10,
        "timeoutSeconds": 5,
        "periodSeconds": 10,
        "successThreshold": 1,
        "failureThreshold": 3,
    }
    docs = render_chart(
        values={
            "global": {
                "authSidecar": {
                    "enabled": True,
                    "repository": "someregistry.io/my-custom-image",
                    "tag": "my-custom-tag",
                    "resources": {},
                    "livenessProbe": liveness_probe,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert "livenessProbe" in prod_yaml["deployments"]["authSideCar"]
    assert prod_yaml["deployments"]["authSideCar"]["livenessProbe"] == liveness_probe


def test_houston_configmap_with_authsidecar_readiness_probe():
    """Validate the authSidecar readiness probe in the Houston configmap."""
    readiness_probe = {
        "httpGet": {"path": "/auth-readiness", "port": 8080, "scheme": "HTTP"},
        "initialDelaySeconds": 10,
        "timeoutSeconds": 5,
        "periodSeconds": 10,
        "successThreshold": 1,
        "failureThreshold": 3,
    }
    docs = render_chart(
        values={
            "global": {
                "authSidecar": {
                    "enabled": True,
                    "repository": "someregistry.io/my-custom-image",
                    "tag": "my-custom-tag",
                    "resources": {},
                    "readinessProbe": readiness_probe,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert "readinessProbe" in prod_yaml["deployments"]["authSideCar"]
    assert prod_yaml["deployments"]["authSideCar"]["readinessProbe"] == readiness_probe


def test_houston_configmap_with_loggingsidecar_liveness_probe():
    """Validate the houston configmap with liveness probe configured."""
    liveness_probe = {
        "httpGet": {
            "path": "/healthz",
            "port": 8080,
            "scheme": "HTTP",
        },
        "initialDelaySeconds": 15,
        "timeoutSeconds": 30,
        "periodSeconds": 5,
        "successThreshold": 1,
        "failureThreshold": 20,
    }

    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": "sidecar-log-test",
                    "livenessProbe": liveness_probe,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert "livenessProbe" in prod_yaml["deployments"]["loggingSidecar"]
    assert prod_yaml["deployments"]["loggingSidecar"]["livenessProbe"] == liveness_probe


def test_houston_configmap_with_loggingsidecar_readiness_probe():
    """Validate the houston configmap with readiness probe configured."""
    readiness_probe = {
        "httpGet": {
            "path": "/healthz",
            "port": 8080,
            "scheme": "HTTP",
        },
        "initialDelaySeconds": 15,
        "timeoutSeconds": 30,
        "periodSeconds": 5,
        "successThreshold": 1,
        "failureThreshold": 20,
    }

    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "name": "sidecar-log-test",
                    "readinessProbe": readiness_probe,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert "readinessProbe" in prod_yaml["deployments"]["loggingSidecar"]
    assert prod_yaml["deployments"]["loggingSidecar"]["readinessProbe"] == readiness_probe


def test_houston_configmap_with_custom_airflow_ingress_annotation_with_authsidecar_disabled():
    """Validate the houston configmap with custom airflow ingress annotation."""
    docs = render_chart(
        values={"global": {"extraAnnotations": {"route.openshift.io/termination": "passthrough"}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    helm = prod_yaml["deployments"]["helm"]
    assert "ingress" in helm
    assert {"extraIngressAnnotations": {"route.openshift.io/termination": "passthrough"}} == helm["ingress"]


def test_houston_configmap_with_custom_airflow_ingress_annotation_disabled_with_authsidecar_disabled():
    """Validate the houston configmap does not include airflow ingress annotation."""
    docs = render_chart(
        values={
            "global": {"authSidecar": {"enabled": True}, "extraAnnotations": {"route.openshift.io/termination": "passthrough"}}
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert not prod_yaml["deployments"]["helm"].get("ingress")


def test_houston_configmap_with_authsidecar_ingress_allowed_namespaces_undefined():
    """Validate the houston configmap should have empty array for ingressAllowedNamespaces."""
    docs = render_chart(
        values={"global": {"authSidecar": {"enabled": True}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod_yaml["deployments"]["authSideCar"].get("ingressAllowedNamespaces") == []


def test_houston_configmap_with_authsidecar_ingress_allowed_namespaces_is_empty():
    """Validate the houston configmap should have empty array for ingressAllowedNamespaces."""
    docs = render_chart(
        values={"global": {"authSidecar": {"enabled": True, "ingressAllowedNamespaces": []}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod_yaml["deployments"]["authSideCar"].get("ingressAllowedNamespaces") == []


def test_houston_configmap_with_authsidecar_ingress_allowed_namespaces():
    """Validate the houston configmap should have values in ingressAllowedNamespaces."""
    docs = render_chart(
        values={"global": {"authSidecar": {"enabled": True, "ingressAllowedNamespaces": ["astronomer", "ingress-namespace"]}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod_yaml["deployments"]["authSideCar"].get("ingressAllowedNamespaces") == ["astronomer", "ingress-namespace"]


def test_houston_configmap_with_plane_mode():
    """Validate the houston configmap should have values in plane mode."""
    docs = render_chart(
        values={"global": {"plane": {"mode": "control"}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod_yaml["plane"]["mode"] == "control"

    docs = render_chart(
        values={"global": {"plane": {"mode": "unified"}}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod_yaml["plane"]["mode"] == "unified"


def test_houston_configmap_pod_mutation_hook_airflow_compatibility():
    """Test that pod mutation hook supports both Airflow 2.x and 3.x task execution patterns with logging sidecar."""
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    airflow_local_settings = prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]

    # Check that both Airflow 2.x and 3.x patterns are supported
    airflow2_pattern = 'container.args[0:3] == ["airflow", "tasks", "run"]'
    airflow3_pattern = 'container.args[0:3] == ["python", "-m", "airflow.sdk.execution_time.execute_workload"]'
    version_check = "int(version.split('.')[0]) >= 3"

    assert airflow2_pattern in airflow_local_settings, "Airflow 2.x task execution pattern should be supported"
    assert airflow3_pattern in airflow_local_settings, "Airflow 3.x task execution pattern should be supported"
    assert version_check in airflow_local_settings, "Version comparison logic should be present"

    # Check that the complete condition includes both patterns
    complete_condition = 'if container.args[0:3] == ["airflow", "tasks", "run"] or (int(version.split(\'.\')[0]) >= 3 and container.args[0:3] == ["python", "-m", "airflow.sdk.execution_time.execute_workload"]):'
    assert complete_condition in airflow_local_settings, "Complete condition should include both Airflow 2.x and 3.x patterns"

    # Check that the logging command is present
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert log_cmd in airflow_local_settings, "Logging command should be present"

    # Validate the Python code is syntactically correct
    ast.parse(airflow_local_settings.encode())
