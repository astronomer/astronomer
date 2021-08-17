from tests.helm_template_generator import render_chart
import jmespath

show_only = [
    "charts/astronomer/templates/commander/commander-deployment.yaml",
    "charts/astronomer/templates/commander/commander-networkpolicy.yaml",
    "charts/astronomer/templates/commander/commander-service.yaml",
    "charts/astronomer/templates/houston/api/houston-backend-secret.yaml",
    "charts/astronomer/templates/houston/api/houston-bootstrap-role.yaml",
    "charts/astronomer/templates/houston/api/houston-jwt-certificate-secret.yaml",  # 2 yaml docs
    "charts/astronomer/templates/registry/registry-configmap.yaml",
    "charts/astronomer/templates/registry/registry-networkpolicy.yaml",
    "charts/astronomer/templates/registry/registry-secret.yaml",
    "charts/astronomer/templates/registry/registry-service.yaml",
    "charts/astronomer/templates/registry/registry-statefulset.yaml",
    "charts/nats/templates/configmap.yaml",
    "charts/nats/templates/networkpolicy.yaml",
    "charts/nats/templates/service.yaml",
    "charts/nats/templates/statefulset.yaml",
    "charts/postgresql/templates/astronomer-bootstrap-secret.yaml",
    # "charts/postgresql/templates/configmap.yaml", # esoteric configurations
    # "charts/postgresql/templates/extended-config-configmap.yaml", # esoteric configurations
    # "charts/postgresql/templates/initialization-configmap.yaml", # esoteric configurations
    "charts/postgresql/templates/networkpolicy.yaml",
    "charts/postgresql/templates/secrets.yaml",
    "charts/postgresql/templates/serviceaccount.yaml",
    "charts/postgresql/templates/statefulset.yaml",
    "charts/postgresql/templates/svc.yaml",
    "charts/stan/templates/configmap.yaml",
    "charts/stan/templates/service.yaml",
    "charts/stan/templates/stan-networkpolicy.yaml",
    "charts/stan/templates/statefulset.yaml",
]


def test_argo_sync_wave():
    """Test that argo sync-wave is configured right."""

    def render_argo_charts(argo_enabled):
        return render_chart(
            show_only=show_only,
            values={
                "global": {
                    "enableArgoCDAnnotation": argo_enabled,
                    "postgresqlEnabled": True,
                },
                "postgresql": {"serviceAccount": {"enabled": True}},
            },
        )

    docs = render_argo_charts(argo_enabled=True)
    assert len(docs) == 26
    assert (
        len(
            jmespath.search(
                '[*].metadata.annotations."argocd.argoproj.io/sync-wave"', docs
            )
        )
        == 26
    )

    docs = render_argo_charts(argo_enabled=False)
    assert len(docs) == 26
    assert (
        len(
            jmespath.search(
                '[*].metadata.annotations."argocd.argoproj.io/sync-wave"', docs
            )
        )
        == 0
    )
