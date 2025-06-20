import pytest

from tests import git_root_dir, supported_k8s_versions, get_containers_by_name
from tests.chart_tests.helm_template_generator import render_chart
from tests.chart_tests import get_all_features, get_chart_containers
import yaml

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet", "CronJob", "Job"]

customize_all_probes = yaml.safe_load(
    ((git_root_dir) / "tests" / "chart_tests" / "test_data" / "enable_all_probes.yaml").read_text()
)


class TestCustomProbes:
    docs = render_chart(values=customize_all_probes)
    filtered_docs = [get_containers_by_name(doc) for doc in docs if doc["kind"] in include_kind_list]

    @pytest.mark.parametrize("doc", filtered_docs)
    def test_template_probes_with_custom_values(self, doc):
        """Ensure all containers have the ability to customize liveness probes."""

        for container in doc.values():
            assert "livenessProbe" in container
            assert "readinessProbe" in container
            assert container["livenessProbe"] != {}
            assert container["readinessProbe"] != {}

    filtered_docs = [doc for doc in docs if doc["kind"] in include_kind_list]

    @pytest.mark.parametrize("doc", filtered_docs)
    def test_init_containers_have_no_probes(self, doc):
        """Ensure init containers do not have liveness or readiness probes."""

        if not (spec := doc.get("spec", {})):
            pytest.skip("doc has no .spec")
        template_spec = spec.get("template", {}).get("spec", {}) if "template" in spec else spec
        init_containers = template_spec.get("initContainers", [])

        for init_container in init_containers:
            container_name = init_container.get("name")
            assert "livenessProbe" not in init_container, f"Init container '{container_name}' should not have livenessProbe"
            assert "readinessProbe" not in init_container, f"Init container '{container_name}' should not have readinessProbe"
            assert "startupProbe" not in init_container, f"Init container '{container_name}' should not have startupProbe"


class TestDefaultProbes:
    """Test the default probes. This test is to ensure we keep the default probes during refactoring."""

    def init_test_probes():
        chart_values = get_all_features()
        containers = {}
        for k8s_version in supported_k8s_versions:
            k8s_version_containers = get_chart_containers(k8s_version, chart_values)
            print(f"Containers before processing: {k8s_version_containers.keys()}")
            containers = {**containers, **k8s_version_containers}
        return dict(sorted(containers.items()))

    chart_containers = init_test_probes()

    # Trim the k8s version because it's not important for this test.
    containers = {
        k.removeprefix(f"{supported_k8s_versions[-1]}_release-name-"): v
        for k, v in chart_containers.items()
        if supported_k8s_versions[-1] in k
    }
    print(f"Container keys after processing: {containers.keys()}")

    # Show only containers that have a liveness or readiness probe.
    current_clp = {k: v["livenessProbe"] for k, v in containers.items() if v.get("livenessProbe")}
    current_crp = {k: v["readinessProbe"] for k, v in containers.items() if v.get("readinessProbe")}

    # Expected container liveness probes. This block should contain all of the expected default liveness probes.
    with open(f"{git_root_dir}/tests/chart_tests/test_data/default_container_liveness_probes.yaml") as f:
        expected_clp = yaml.safe_load(f.read())

    # Expected container readiness probes. This block should contain all of the expected default readiness probes.
    with open(f"{git_root_dir}/tests/chart_tests/test_data/default_container_readiness_probes.yaml") as f:
        expected_crp = yaml.safe_load(f.read())

    # liveness probe data and ids
    lp_data = zip(current_clp.keys(), current_clp.values(), expected_clp.values())
    lp_ids = current_clp.keys()

    # If any other tests fail, this will not run, so they have to be commented out for this to actually show you where the problem is.
    @pytest.mark.parametrize("current,expected", [(current_clp, expected_clp), (current_crp, expected_crp)])
    def test_probe_lists(self, current, expected):
        """Test that the list of probes matches between what is rendered by the current chart version and what is expected."""
        set_difference = set(current.keys()) ^ set(expected.keys())
        assert set_difference == set(), f"Containers not in both lists: {set_difference}"

    @pytest.mark.parametrize("container,current,expected", lp_data, ids=lp_ids)
    def test_individual_liveness_probes(self, container, current, expected):
        """Test the default livenessProbes for each container."""
        assert current == expected, f"container {container} has unexpected livenessProbe"

    rp_data = zip(current_crp.keys(), current_crp.values(), expected_crp.values())
    rp_ids = current_crp.keys()

    @pytest.mark.parametrize("container,current,expected", rp_data, ids=rp_ids)
    def test_individual_readiness_probes(self, container, current, expected):
        """Test the default readinessProbes for each container."""
        assert current == expected, f"container {container} has unexpected readinessProbe"
