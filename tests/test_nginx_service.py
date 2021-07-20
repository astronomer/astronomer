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

    def test_nginx_type_clusterip(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            values={"nginx": {"serviceType": "ClusterIP"}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["type"] == "ClusterIP"

    def test_nginx_type_nodeport(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            values={"nginx": {"serviceType": "NodePort"}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["type"] == "NodePort"

    def test_nginx_enabled_externalips(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            values={"nginx": {"externalIPs": "1.2.3.4"}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert len(doc["spec"]["externalIps"]) > 0
        assert "1.2.3.4" in doc["spec"]["externalIps"]
