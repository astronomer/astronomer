from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath
import base64
import yaml

secret = base64.b64encode(b"sample-secret").decode()


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestExternalElasticSearch:
    def test_externalelasticsearch_with_secret(self, kube_version):
        """Test External ElasticSearch with secret passed from config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secret": secret}}},
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-env-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 4
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-external-es-proxy"
        expected_env = [{"name": "ES_SECRET", "value": secret}]
        assert expected_env == doc["spec"]["template"]["spec"]["containers"][0]["env"]

        assert "Service" == jmespath.search("kind", docs[3])
        assert "RELEASE-NAME-external-es-proxy" == jmespath.search(
            "metadata.name", docs[3]
        )
        assert "ClusterIP" == jmespath.search("spec.type", docs[3])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
        } in jmespath.search("spec.ports", docs[3])
        assert {"name": "http", "protocol": "TCP", "port": 9201} in jmespath.search(
            "spec.ports", docs[3]
        )

    def test_externalelasticsearch_with_secretname(self, kube_version):
        """Test External ElasticSearch with secret passed as kubernetes secrets."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"customLogging": {"enabled": True, "secretName": "essecret"}}
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-env-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 4
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-external-es-proxy"
        expected_env = [
            {
                "name": "ES_SECRET_NAME",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "essecret",
                        "key": "elastic",
                    },
                },
            }
        ]
        assert expected_env == doc["spec"]["template"]["spec"]["containers"][0]["env"]

        assert "Service" == jmespath.search("kind", docs[3])
        assert "RELEASE-NAME-external-es-proxy" == jmespath.search(
            "metadata.name", docs[3]
        )
        assert "ClusterIP" == jmespath.search("spec.type", docs[3])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
        } in jmespath.search("spec.ports", docs[3])
        assert {"name": "http", "protocol": "TCP", "port": 9201} in jmespath.search(
            "spec.ports", docs[3]
        )

    def test_externalelasticsearch_with_awsSecretName(self, kube_version):
        """Test External ElasticSearch with aws secret passed as kubernetes secret."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsSecretName": "awssecret",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 2
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-external-es-proxy"
        expected_env = [
            {
                "name": "AWS_ACCESS_KEY_ID",
                "valueFrom": {
                    "secretKeyRef": {"name": "awssecret", "key": "aws_access_key"}
                },
            },
            {
                "name": "AWS_SECRET_ACCESS_KEY",
                "valueFrom": {
                    "secretKeyRef": {"name": "awssecret", "key": "aws_secret_key"}
                },
            },
            {"name": "ENDPOINT", "value": "https://esdemo.example.com"},
        ]
        assert expected_env == doc["spec"]["template"]["spec"]["containers"][1]["env"]

        assert "Service" == jmespath.search("kind", docs[1])
        assert "RELEASE-NAME-external-es-proxy" == jmespath.search(
            "metadata.name", docs[1]
        )
        assert "ClusterIP" == jmespath.search("spec.type", docs[1])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
        } in jmespath.search("spec.ports", docs[1])
        assert {"name": "http", "protocol": "TCP", "port": 9201} in jmespath.search(
            "spec.ports", docs[1]
        )

    def test_externalelasticsearch_with_awsIAMRole(self, kube_version):
        """Test External ElasticSearch with iam roles passed as Deployment annotation."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsIAMRole": "arn:aws:iam::xxxxxxxx:role/customrole",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 2
        doc = docs[0]
        expected_env = [{"name": "ENDPOINT", "value": "https://esdemo.example.com"}]

        assert expected_env == doc["spec"]["template"]["spec"]["containers"][1]["env"]

        assert "arn:aws:iam::xxxxxxxx:role/customrole" == jmespath.search(
            'spec.template.metadata.annotations."iam.amazonaws.com/role"', docs[0]
        )

        assert "Service" == jmespath.search("kind", docs[1])
        assert "RELEASE-NAME-external-es-proxy" == jmespath.search(
            "metadata.name", docs[1]
        )
        assert "ClusterIP" == jmespath.search("spec.type", docs[1])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
        } in jmespath.search("spec.ports", docs[1])
        assert {"name": "http", "protocol": "TCP", "port": 9201} in jmespath.search(
            "spec.ports", docs[1]
        )

    def test_externalelasticsearch_with_awsServiceAccountAnnotation(self, kube_version):
        """Test External ElasticSearch with eks iam roles passed as Service Account Annotation."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-serviceaccount.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 3
        doc = docs[0]
        expected_env = [{"name": "ENDPOINT", "value": "https://esdemo.example.com"}]

        assert expected_env == doc["spec"]["template"]["spec"]["containers"][1]["env"]

        doc = docs[1]

        assert "arn:aws:iam::xxxxxxxx:role/customrole" == jmespath.search(
            'metadata.annotations."eks.amazonaws.com/role-arn"', doc
        )

        assert "Service" == jmespath.search("kind", docs[2])
        assert "RELEASE-NAME-external-es-proxy" == jmespath.search(
            "metadata.name", docs[2]
        )
        assert "ClusterIP" == jmespath.search("spec.type", docs[2])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
        } in jmespath.search("spec.ports", docs[2])
        assert {"name": "http", "protocol": "TCP", "port": 9201} in jmespath.search(
            "spec.ports", docs[2]
        )

    def test_externalelasticsearch_houston_configmap_with_disabled_kibanaUIFlag(
        self, kube_version
    ):
        """Test Houston Configmap with kibanaUIFlag."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True}}},
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["kibanaUIEnabled"] is False
