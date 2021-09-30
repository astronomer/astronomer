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

    def test_nginx_type_loadbalancer_omits_nodeports(self):
        # sourcery skip: extract-duplicate-method
        httpNodePort, httpsNodePort, metricsNodePort = [30401, 30402, 30403]
        docs = render_chart(
            values={
                "nginx": {
                    "serviceType": "LoadBalancer",
                    "httpNodePort": httpNodePort,
                    "httpsNodePort": httpsNodePort,
                    "metricsNodePort": metricsNodePort,
                }
            },
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        ports = doc["spec"]["ports"]
        assert not [x for x in ports if "nodePort" in x]

    def test_nginx_type_nodeport_doesnt_require_nodeports(self):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            values={
                "nginx": {
                    "serviceType": "NodePort",
                    "httpsNodePort": None,
                }
            },
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["type"] == "NodePort"

    def test_nginx_type_nodeport_specifying_nodeports(self):
        # sourcery skip: extract-duplicate-method
        httpNodePort, httpsNodePort, metricsNodePort = [30401, 30402, 30403]
        docs = render_chart(
            values={
                "nginx": {
                    "serviceType": "NodePort",
                    "httpNodePort": httpNodePort,
                    "httpsNodePort": httpsNodePort,
                    "metricsNodePort": metricsNodePort,
                }
            },
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        ports = doc["spec"]["ports"]
        ports_by_name = {x["name"]: x["nodePort"] for x in ports}
        assert ports_by_name["http"] == httpNodePort
        assert ports_by_name["https"] == httpsNodePort
        assert ports_by_name["metrics"] == metricsNodePort

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
