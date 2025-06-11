import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCpDpFeature:
    @staticmethod
    def filter_charts_by_component(charts, component):
        return [chart for chart in charts if chart.get("metadata", {}).get("labels", {}).get("plane") == component]

    def test_astronomer_cp_only(self, kube_version):
        """Test that helm renders the correct templates when only the control mode is enabled."""
        charts = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
        )
        cp_resources = self.filter_charts_by_component(charts, "control")
        assert len(cp_resources) > 0

        dp_resources = self.filter_charts_by_component(charts, "data")
        assert len(dp_resources) == 0

    def test_astronomer_dp_only(self, kube_version):
        """Test that helm renders the correct templates when only the data mode is enabled."""
        charts = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
        )
        cp_resources = self.filter_charts_by_component(charts, "control")
        assert len(cp_resources) == 0

        dp_resources = self.filter_charts_by_component(charts, "data")
        assert len(dp_resources) > 0

    def test_astronomer_both_cp_dp_enabled(self, kube_version):
        """Test when both CP and DP features are enabled."""
        charts = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "unified"}}},
        )
        unified_resources = self.filter_charts_by_component(charts, "unified")
        assert len(unified_resources) > 0

    def test_astronomer_both_cp_dp_disabled(self, kube_version):
        """Test when both CP and DP features are disabled."""
        charts = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "RandomValue"}}},
        )
        cp_resources = self.filter_charts_by_component(charts, "control")
        assert len(cp_resources) == 0

        dp_resources = self.filter_charts_by_component(charts, "data")
        assert len(dp_resources) == 0

        unified_resources = self.filter_charts_by_component(charts, "unified")
        assert len(unified_resources) == 0
