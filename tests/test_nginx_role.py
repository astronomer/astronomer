from tests.helm_template_generator import render_chart


class TestNginxRole:
    def test_nginx_role(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            show_only=["charts/nginx/templates/nginx-role.yaml"],
        )

        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "Role"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-nginx"

    def test_nginx_role_verbs_ingresses_status(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            values={"global": {"singleNamespace": "true"}},
            show_only=["charts/nginx/templates/nginx-role.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Role"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-nginx"
        assert doc["rules"] == any('ingresses/status' in val for val in doc.values())
