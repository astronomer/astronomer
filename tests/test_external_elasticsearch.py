from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath
import base64

secret = base64.b64encode(b"sample-secret").decode()


def _base64(string):
    return base64.b64encode(string.encode()).decode()


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestExternalElasticSearch:
    def test_externalelasticsearch_with_secret(self, kube_version):
        """Test External ElasticSearch with secret passed from config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"custom_logging": {"enabled": True, "secret": secret}}},
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-external-es-proxy"
        expected_env = [{"name": "ES_SECRET", "value": secret}]
        assert expected_env == doc["spec"]["template"]["spec"]["containers"][0]["env"]

    def test_externalelasticsearch_with_secretname(self, kube_version):
        """Test External ElasticSearch with secret passed as kubernetes secrets."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "custom_logging": {"enabled": True, "secretName": "essecret"}
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        print(doc)
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

    def test_externalelasticsearch_with_awsSecretName(self, kube_version):
        """Test External ElasticSearch with aws secret passed as kubernetes secret."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "custom_logging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsSecretName": "awssecret",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        print(doc)
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

    def test_externalelasticsearch_with_awsIAMRole(self, kube_version):
        """Test External ElasticSearch with iam roles passed as Deployment annotation."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "custom_logging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsIAMRole": "arn:aws:iam::xxxxxxxx:role/customrole",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        expected_env = [{"name": "ENDPOINT", "value": "https://esdemo.example.com"}]

        assert expected_env == doc["spec"]["template"]["spec"]["containers"][1]["env"]

        assert "arn:aws:iam::xxxxxxxx:role/customrole" == jmespath.search(
            'spec.template.metadata.annotations."iam.amazonaws.com/role"', docs[0]
        )
