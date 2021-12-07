from tests.helm_template_generator import render_chart


class TestNginx:
    def test_nginx_service_basics(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "Service"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-nginx"

    def test_nginx_type_loadbalancer(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            values={"nginx": {"serviceType": "LoadBalancer"}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["spec"]["type"] == "LoadBalancer"
