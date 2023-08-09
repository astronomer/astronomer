import yaml
from tests.chart_tests.helm_template_generator import render_chart
import pytest
import ast


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
    airflow_local_settings = prod["deployments"]["helm"]["airflow"][
        "airflowLocalSettings"
    ]

    assert (
        prod["deployments"]["helm"]["airflow"]["cleanup"]["schedule"]
        == '{{- add 3 (regexFind ".$" (adler32sum .Release.Name)) -}}-59/15 * * * *'
    )

    # validate yaml-embedded python
    ast.parse(airflow_local_settings.encode())


def test_houston_configmap():
    """Validate the houston configmap and its embedded data."""
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
    assert prod["deployments"]["helm"]["airflow"]["elasticsearch"]["connection"][
        "host"
    ].startswith("http://")
    with pytest.raises(KeyError):
        # Ensure sccEnabled is not defined by default
        assert prod["deployments"]["helm"]["sccEnabled"] is False


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

    with pytest.raises(KeyError):
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
    assert (
        "extraVolumeMounts"
        not in prod_yaml["deployments"]["helm"]["airflow"]["webserver"]
    )
    assert (
        "extraVolumes" not in prod_yaml["deployments"]["helm"]["airflow"]["webserver"]
    )
    assert not prod_yaml["deployments"].get("loggingSidecar")


def test_houston_configmap_with_loggingsidecar_enabled():
    """Validate the houston configmap and its embedded data with
    loggingSidecar."""
    docs = render_chart(
        values={
            "global": {
                "loggingSidecar": {
                    "enabled": True,
                    "image": "quay.io/astronomer/ap-vector:0.22.3",
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert (
        log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    )
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": "sidecar-log-consumer",
        "image": "quay.io/astronomer/ap-vector:0.22.3",
        "customConfig": False,
    }
    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_overrides():
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
                    "image": image_name,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert (
        log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    )
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
                    "image": image_name,
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
    assert (
        log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    )
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
                    "image": image_name,
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
    log_cmd = 'log_cmd = " 1> >( tee -a /var/log/sidecar-log-consumer/out.log ) 2> >( tee -a /var/log/sidecar-log-consumer/err.log >&2 ) ; "'
    assert (
        log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    )
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
                    "image": image_name,
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
    assert (
        log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    )
    assert prod_yaml["deployments"]["loggingSidecar"] == {
        "enabled": True,
        "name": sidecar_container_name,
        "image": "quay.io/astronomer/ap-vector:0.22.3",
        "customConfig": False,
        "extraEnv": [
            {
                "name": "ES_USER",
                "valueFrom": {
                    "secretKeyRef": {"name": "elastic-creds", "key": "ESUSER"}
                },
            },
            {
                "name": "ES_PASS",
                "valueFrom": {
                    "secretKeyRef": {"name": "elastic-creds", "key": "ESPASS"}
                },
            },
        ],
    }

    assert "vector" in prod_yaml["deployments"]["loggingSidecar"]["image"]


def test_houston_configmap_with_loggingsidecar_enabled_with_resource_overrides():
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
                    "image": image_name,
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
    assert (
        log_cmd in prod_yaml["deployments"]["helm"]["airflow"]["airflowLocalSettings"]
    )
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


def test_houston_configmapwith_update_airflow_runtime_checks_enabled():
    """Validate the houston configmap and its embedded data with
    updateAirflowCheck and updateRuntimeCheck."""
    docs = render_chart(
        values={
            "astronomer": {
                "houston": {
                    "updateAirflowCheck": {"enabled": True},
                    "updateRuntimeCheck": {"enabled": True},
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]

    prod = yaml.safe_load(doc["data"]["production.yaml"])

    assert prod["updateAirflowCheckEnabled"] is True
    assert prod["updateRuntimeCheckEnabled"] is True


def test_houston_configmapwith_update_airflow_runtime_checks_disabled():
    """Validate the houston configmap and its embedded data with
    updateAirflowCheck and updateRuntimeCheck."""
    docs = render_chart(
        values={
            "astronomer": {
                "houston": {
                    "updateAirflowCheck": {"enabled": False},
                    "updateRuntimeCheck": {"enabled": False},
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )
    common_test_cases(docs)
    doc = docs[0]

    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert prod["updateAirflowCheckEnabled"] is False
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
