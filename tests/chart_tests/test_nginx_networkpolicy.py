from tests.utils.chart import render_chart


class TestNginxNetworkPolicy:
    def test_nginx_networkpolicy_basics(self):
        docs = render_chart(
            show_only=[
                "charts/nginx/templates/controlplane/nginx-cp-metrics-networkpolicy.yaml",
                "charts/nginx/templates/controlplane/nginx-cp-networkpolicy.yaml",
            ],
        )
        assert len(docs) == 2
        for doc in docs:
            assert doc["kind"] == "NetworkPolicy"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert doc["spec"]["podSelector"]["matchLabels"]["tier"] == "nginx"

    def test_disabled_networkpolicies(self):
        """Test that NetworkPolicies can be disabled via global settings."""
        disabled_values = {"global": {"plane": {"mode": "data"}}}
        docs = render_chart(
            show_only=[
                "charts/nginx/templates/controlplane/nginx-cp-networkpolicy.yaml",
                "charts/nginx/templates/dataplane/nginx-dp-networkpolicy.yaml",
            ],
            values=disabled_values,
        )
        assert len(docs) == 1, f"Expected 1 document, got {len(docs)}"
        assert "release-name-dp-nginx-policy" in docs[0]["metadata"]["name"]

        disabled_values = {"global": {"plane": {"mode": "control"}}}
        docs = render_chart(
            show_only=[
                "charts/nginx/templates/controlplane/nginx-cp-networkpolicy.yaml",
                "charts/nginx/templates/dataplane/nginx-dp-networkpolicy.yaml",
            ],
            values=disabled_values,
        )
        assert len(docs) == 1, f"Expected 1 document, got {len(docs)}"
        assert "release-name-cp-nginx-policy" in docs[0]["metadata"]["name"]

        disabled_values = {"global": {"plane": {"mode": "RandomValue"}}}
        docs = render_chart(
            show_only=[
                "charts/nginx/templates/controlplane/nginx-cp-networkpolicy.yaml",
                "charts/nginx/templates/dataplane/nginx-dp-networkpolicy.yaml",
            ],
            values=disabled_values,
        )
        assert len(docs) == 0
