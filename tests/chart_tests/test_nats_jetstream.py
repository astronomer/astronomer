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

        assert len(docs) == 3
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        assert prod["nats"] == {"jetStreamEnabled": True, "tlsEnabled": False}
        nats_cm = docs[2]["data"]["nats.conf"]
        assert "jetstream" in nats_cm
        assert {"runAsUser": 1000, "runAsNonRoot": True} == docs[1]["spec"]["template"]["spec"]["containers"][0]["securityContext"]

    def test_nats_statefulset_with_jetstream_and_tls(self, kube_version):
        """Test Nats with jetstream config."""
        values = {
            "global": {"nats": {"jetStream": {"enabled": True, "tls": True}}},
            "nats": {"nats": {"createJetStreamJob": True}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/houston-configmap.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/nats/templates/configmap.yaml",
                "charts/nats/templates/jetstream-job-scc.yaml",
                "charts/nats/templates/jetstream-job.yaml",
                "charts/nats/templates/nats-jetstream-tls-secret.yaml",
                "charts/nats/templates/statefulset.yaml",
            ],
        )

        assert len(docs) == 11

        obj_by_name = {f"{x['kind']}-{x['metadata']['name']}": x for x in docs}

        jetStreamCertPrefix = "/etc/houston/jetstream/tls/release-name-jetstream-tls-certificate"
        prod = yaml.safe_load(obj_by_name["ConfigMap-release-name-houston-config"]["data"]["production.yaml"])
        assert prod["nats"] == {
            "jetStreamEnabled": True,
            "tlsEnabled": True,
            "tls": {
                "caFile": f"{jetStreamCertPrefix}-client/ca.crt",
                "certFile": f"{jetStreamCertPrefix}-client/tls.crt",
                "keyFile": f"{jetStreamCertPrefix}-client/tls.key",
            },
        }

        assert {
            "name": "release-name-jetstream-tls-certificate-client-volume",
            "mountPath": "/etc/nats-certs/client/release-name-jetstream-tls-certificate-client",
        } in obj_by_name["StatefulSet-release-name-nats"]["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]

        assert {
            "name": "release-name-jetstream-tls-certificate-server-volume",
            "mountPath": "/etc/nats-certs/server/release-name-jetstream-tls-certificate",
        } in obj_by_name["StatefulSet-release-name-nats"]["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]

        assert {
            "name": "release-name-jetstream-tls-certificate-client-volume",
            "secret": {"secretName": "release-name-jetstream-tls-certificate-client"},
        } in obj_by_name["StatefulSet-release-name-nats"]["spec"]["template"]["spec"]["volumes"]

        assert {
            "name": "release-name-jetstream-tls-certificate-server-volume",
            "secret": {"secretName": "release-name-jetstream-tls-certificate"},
        } in obj_by_name["StatefulSet-release-name-nats"]["spec"]["template"]["spec"]["volumes"]

        nats_cm = obj_by_name["ConfigMap-release-name-nats-config"]["data"]["nats.conf"]
        assert "jetstream" in nats_cm
        assert (
            obj_by_name["Secret-release-name-jetstream-tls-certificate"]["metadata"]["name"]
            == "release-name-jetstream-tls-certificate"
        )
        assert (
            obj_by_name["Secret-release-name-jetstream-tls-certificate-client"]["metadata"]["name"]
            == "release-name-jetstream-tls-certificate-client"
        )

        for item in [
            "Deployment-release-name-houston",
            "Deployment-release-name-houston-worker",
        ]:
            assert {
                "name": "nats-jetstream-client-tls-volume",
                "mountPath": f"{jetStreamCertPrefix}-client",
            } in obj_by_name[item][
                "spec"
            ]["template"]["spec"]["containers"][0]["volumeMounts"]
            assert {
                "name": "nats-jetstream-client-tls-volume",
                "mountPath": "/usr/local/share/ca-certificates/release-name-jetstream-tls-certificate-client.crt",
                "subPath": "ca.crt",
            } in obj_by_name[item]["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
            assert {
                "name": "nats-jetstream-client-tls-volume",
                "secret": {"secretName": "release-name-jetstream-tls-certificate-client"},
            } in obj_by_name[item]["spec"]["template"]["spec"]["volumes"]

    def test_stan_with_jetstream_enabled(self, kube_version):
        """Test that stan statefulset is disabled when jetstream is enabled."""
        values = {
            "global": {"nats": {"jetStream": {"enabled": True}}},
            "nats": {"nats": {"createJetStreamJob": True}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/stan/templates/configmap.yaml",
                "charts/stan/templates/service.yaml",
                "charts/stan/templates/statefulset.yaml",
                "charts/stan/templates/stan-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 0

    def test_stan_with_jetstream_disabled(self, kube_version):
        """Test that stan statefulset is disabled when jetstream is enabled."""
        values = {
            "global": {"nats": {"jetStream": {"enabled": False}}},
            "nats": {"nats": {"createJetStreamJob": True}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/stan/templates/configmap.yaml",
                "charts/stan/templates/service.yaml",
                "charts/stan/templates/statefulset.yaml",
                "charts/stan/templates/stan-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 4

    def test_nats_with_jetstream_disabled_with_custom_flag(self, kube_version):
        """Test that jetstream feature  is disabled completely with createJetStreamJob."""
        values = {
            "global": {"nats": {"jetStream": {"enabled": False}}},
            "nats": {"nats": {"createJetStreamJob": False}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/nats/templates/statefulset.yaml",
                "charts/nats/templates/configmap.yaml",
                "charts/nats/templates/jetstream-job.yaml",
                "charts/stan/templates/configmap.yaml",
                "charts/stan/templates/service.yaml",
                "charts/stan/templates/statefulset.yaml",
                "charts/stan/templates/stan-networkpolicy.yaml",
                "charts/nats/templates/nats-jetstream-tls-secret.yaml",
            ],
        )
        assert len(docs) == 6

    def test_jetstream_hook_job_disabled(self, kube_version):
        """Test that jetstream hook job is disabled when createJetStreamJob is disabled."""
        values = {
            "nats": {"nats": {"createJetStreamJob": False}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/nats/templates/jetstream-job.yaml",
            ],
        )

        assert len(docs) == 0


@pytest.mark.parametrize(
    "scc_enabled,create_jetstream_job,jetstream_enabled,global_jetstream_enabled,stan_enabled,expected_docs",
    [
        (True, True, False, True, False, 1),
        (True, True, False, False, True, 1),
        (True, True, False, True, True, 1),
        (True, True, False, False, False, 0),
        (True, False, False, True, False, 0),
        (True, False, False, False, False, 0),
        (False, True, False, True, False, 0),
        (False, False, False, True, False, 0),
        (False, True, False, False, False, 0),
        (False, False, False, False, False, 0),
    ],
)
def test_jetstream_job_with_scc(
    scc_enabled,
    create_jetstream_job,
    jetstream_enabled,
    global_jetstream_enabled,
    stan_enabled,
    expected_docs,
):
    """Test that helm renders the nats SCC template only in the right circumstances."""
    values = {
        "global": {
            "sccEnabled": scc_enabled,
            "nats": {
                "jetStream": {
                    "enabled": global_jetstream_enabled,
                },
            },
            "stan": {
                "enabled": stan_enabled,
            },
        },
        "nats": {
            "nats": {
                "createJetStreamJob": create_jetstream_job,
                "jetStream": {
                    "enabled": jetstream_enabled,
                },
            },
        },
    }

    docs = render_chart(
        validate_objects=False,  # False because SCC is not a standard k8s object
        values=values,
        show_only=[
            "charts/nats/templates/jetstream-job-scc.yaml",
        ],
    )
    assert len(docs) == expected_docs
