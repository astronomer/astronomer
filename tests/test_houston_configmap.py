import yaml
from tests.helm_template_generator import render_chart
import pytest
import tempfile
from subprocess import check_call


def common_test_cases(docs):
    """Test some things that should apply to all cases."""
    assert len(docs) == 1

    doc = docs[0]

    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

    local_prod = yaml.safe_load(doc["data"]["local-production.yaml"])

    assert local_prod == {}

    prod = yaml.safe_load(doc["data"]["production.yaml"])

    assert prod["deployments"]["helm"]["airflow"]["useAstroSecurityManager"] is True

    airflow_local_settings = prod["deployments"]["helm"]["airflow"][
        "airflowLocalSettings"
    ]

    with tempfile.NamedTemporaryFile() as f:
        f.write(airflow_local_settings.encode())
        f.flush()
        # validate embedded python. returns if black succeeds, else raises CalledProcessError.
        check_call(["black", "-q", f.name])


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

    with pytest.raises(KeyError):
        # Ensure sccEnabled is not defined by default
        assert prod["deployments"]["helm"]["sccEnabled"] is False


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
    """Validate the houston configmap and its embedded data with azure enabled."""
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


def test_houston_configmap_with_kubed_enabled():
    """Validate the houston configmap and its embedded data with kubedEnabled."""
    docs = render_chart(
        values={"global": {"kubedEnabled": True}},
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
            "secret": {"secretName": "RELEASE-NAME-houston-jwt-signing-certificate"},
        }
    ]


def test_houston_configmap_with_kubed_disabled():
    """Validate the houston configmap and its embedded data with kubedEnabled."""
    docs = render_chart(
        values={"global": {"kubedEnabled": False}},
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )

    common_test_cases(docs)
    doc = docs[0]
    prod = yaml.safe_load(doc["data"]["production.yaml"])
    assert (
        "extraVolumeMounts" not in prod["deployments"]["helm"]["airflow"]["webserver"]
    )
    assert "extraVolumes" not in prod["deployments"]["helm"]["airflow"]["webserver"]
