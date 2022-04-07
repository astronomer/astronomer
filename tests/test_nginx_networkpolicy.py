from tests.helm_template_generator import render_chart


class TestNginxNetworkPolicy:
    def test_nginx_networkpolicy_basics(self):
        docs = render_chart(
            show_only=[
                "charts/nginx/templates/nginx-metrics-networkpolicy.yaml",
                "charts/nginx/templates/nginx-networkpolicy.yaml",
            ],
        )
        assert len(docs) == 2
        for doc in docs:
            assert doc["kind"] == "NetworkPolicy"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert doc["spec"]["podSelector"]["matchLabels"]["tier"] == "nginx"
