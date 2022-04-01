from tests.unit_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
from tests import git_root_dir


class TestHoustonPDB:
    def test_houston_pdb_cronjobs(self):
        """Test that pdbs do not touch houston cronjobs or workers"""
        templates = [
            "charts/astronomer/templates/houston/cronjobs/houston-expire-deployments-cronjob.yaml",
            "charts/astronomer/templates/houston/cronjobs/houston-check-updates-cronjob.yaml",
            "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deployments-cronjob.yaml",
            "charts/astronomer/templates/houston/cronjobs/houston-check-updates-cronjob.yaml",
        ]

        for show_only in templates:
            labels = render_chart(
                show_only=[show_only],
                values={
                    "astronomer": {"houston": {"expireDeployments": {"enabled": True}}}
                },
            )[0]["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
            assert (
                labels["component"] != "houston"
            ), f"ERROR: tempplate '{show_only}' matched houston"

    def test_houston_pdb_workers(self):
        """Test that pdbs do not touch houston cronjobs or workers"""
        template = (
            "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"
        )
        match_labels = render_chart(show_only=[template])[0]["spec"]["selector"][
            "matchLabels"
        ]
        assert (
            match_labels["component"] != "houston"
        ), f"ERROR: tempplate '{template}' matched houston"

    def test_houston_api_pdb_match_labels(self):
        # sourcery skip: class-extract-method
        """Houston pdb should have the right matchLabels"""
        template = (
            "charts/astronomer/templates/houston/api/houston-pod-disruption-budget.yaml"
        )
        match_labels = render_chart(show_only=[template])[0]["spec"]["selector"][
            "matchLabels"
        ]
        assert match_labels["tier"] == "astronomer"
        assert match_labels["component"] == "houston"

    def test_houston_api_pdb_deployment(self):
        """Houston pdb should have the right matchLabels"""
        template = "charts/astronomer/templates/houston/api/houston-deployment.yaml"
        labels = render_chart(show_only=[template])[0]["spec"]["template"]["metadata"][
            "labels"
        ]
        assert labels["tier"] == "astronomer"
        assert labels["component"] == "houston"


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPDB:

    show_only = [
        str(path.relative_to(git_root_dir))
        for path in git_root_dir.rglob("charts/**/*")
        if "pod-disruption-budget" in str(path)
    ]

    def test_pod_disruption_budgets_default(self, kube_version):
        """Validate that default PodDisruptionBudget configs use latest available API version."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"global": {"prometheusPostgresExporterEnabled": True}},
        )
        _, minor, _ = (int(x) for x in kube_version.split("."))

        if minor < 21:
            assert all(x["apiVersion"] == "policy/v1beta1" for x in docs)
        else:
            assert all(x["apiVersion"] == "policy/v1" for x in docs)

    def test_pod_disruption_budgets_use_legacy(self, kube_version):
        """Allow global.useLegacyPodDisruptionBudget to use policy/v1beta1 until k8s 1.25.0"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "prometheusPostgresExporterEnabled": True,
                    "useLegacyPodDisruptionBudget": True,
                }
            },
        )
        _, minor, _ = (int(x) for x in kube_version.split("."))

        if minor < 25:
            assert all(x["apiVersion"] == "policy/v1beta1" for x in docs)
        else:
            assert ValueError("policy/v1beta1 is not supported in k8s 1.25+")
