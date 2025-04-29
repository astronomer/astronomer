from tests.chart_tests.helm_template_generator import render_chart


class TestNginxNetworkPolicy:
    def test_nginx_networkpolicy_basics(self):
        docs = render_chart(
            show_only=[
                "charts/nginx/templates/nginx-cp/nginx-cp-metrics-networkpolicy.yaml",
                "charts/nginx/templates/nginx-cp/nginx-cp-networkpolicy.yaml",
                "charts/nginx/templates/nginx-dp/nginx-dp-metrics-networkpolicy.yaml",
                "charts/nginx/templates/nginx-dp/nginx-dp-networkpolicy.yaml",
            ],
        )
        assert len(docs) == 4
        for doc in docs:
            assert doc["kind"] == "NetworkPolicy"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert doc["spec"]["podSelector"]["matchLabels"]["tier"] == "nginx"
