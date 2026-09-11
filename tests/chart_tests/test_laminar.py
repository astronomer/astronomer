from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils.chart import render_chart

LAMINAR_TEMPLATES = sorted(
    str(x.relative_to(git_root_dir))
    for x in Path(f"{git_root_dir}/charts/laminar/templates/").glob("**/*.yaml")
    if not x.name.startswith("_")
)


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestLaminar:
    def test_laminar_disabled_by_default(self, kube_version):
        """Test that laminar is disabled by default."""
        docs = render_chart(kube_version=kube_version)

        laminar_docs = [
            doc for doc in docs if str(doc.get("metadata", {}).get("labels", {}).get("chart", "")).startswith("laminar-")
        ]
        assert laminar_docs == []

    @pytest.mark.parametrize("plane_mode", ["control", "unified"])
    def test_laminar_gated_by_plane_mode(self, kube_version, plane_mode):
        """Test that laminar renders only when the plane is data/unified."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}}},
            show_only=LAMINAR_TEMPLATES,
        )

        if plane_mode == "control":
            assert len(docs) == 0
        else:
            assert len(docs) > 0
