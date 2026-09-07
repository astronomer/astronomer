import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

DEFAULT_SCHEMA = "houston$default"

# Every template that has to agree on which Postgres schema Houston's tables live
# in. The bootstrapper containers read SCHEMA_NAME to create the schema and to
# write it into the connection secret; the prometheus filesd-reloader queries the
# Houston tables directly and needs the same value (APC-859).
#
# houston-cp-refresh-job is covered separately: it renders only in HA mode.
SCHEMA_TEMPLATES = {
    "charts/astronomer/templates/houston/api/houston-deployment.yaml": ("houston-bootstrapper", "SCHEMA_NAME"),
    "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml": (
        "houston-bootstrapper",
        "SCHEMA_NAME",
    ),
    "charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml": (
        "houston-bootstrapper",
        "SCHEMA_NAME",
    ),
    "charts/astronomer/templates/houston/helm-hooks/houston-upgrade-deployments-job.yaml": (
        "houston-bootstrapper",
        "SCHEMA_NAME",
    ),
    "charts/prometheus/templates/prometheus-statefulset.yaml": ("filesd-reloader", "DATABASE_SCHEMA_NAME"),
}


def _schema_value(kube_version, template, container, env_var, values=None):
    """Render one template and return the schema env var on the given container."""
    docs = render_chart(kube_version=kube_version, values=values, show_only=[template])
    assert len(docs) == 1, f"{template} did not render"
    containers = get_containers_by_name(docs[0], include_init_containers=True)
    assert container in containers, f"{template} has no container named {container}"
    return get_env_vars_dict(containers[container]["env"])[env_var]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestHoustonDbSchema:
    @pytest.mark.parametrize("template", SCHEMA_TEMPLATES)
    def test_schema_defaults_to_houston_default(self, kube_version, template):
        """Test that every template defaults to houston$default.

        Existing installs have their tables in this schema, so the default must not
        move. Changing it points Houston at an empty schema.
        """
        container, env_var = SCHEMA_TEMPLATES[template]
        assert _schema_value(kube_version, template, container, env_var) == DEFAULT_SCHEMA

    @pytest.mark.parametrize("template", SCHEMA_TEMPLATES)
    def test_schema_honours_override(self, kube_version, template):
        """Test that global.houston.schemaName overrides the default everywhere.

        The value is global because it spans the astronomer and prometheus
        subcharts, and a partial override would leave prometheus querying a schema
        Houston is not using.
        """
        container, env_var = SCHEMA_TEMPLATES[template]
        values = {"global": {"houston": {"schemaName": "public"}}}
        assert _schema_value(kube_version, template, container, env_var, values) == "public"

    def test_schema_reaches_the_ha_only_cp_refresh_job(self, kube_version):
        """Test the HA-gated cp-refresh job, which the parametrised cases cannot render."""
        template = "charts/astronomer/templates/houston/helm-hooks/houston-cp-refresh-job.yaml"
        values = {
            "global": {
                "plane": {"mode": "control"},
                "controlPlaneHA": {"enabled": True, "globalBaseDomain": "astro.example.com"},
                "houston": {"schemaName": "public"},
            }
        }
        docs = render_chart(kube_version=kube_version, values=values, show_only=[template])

        assert len(docs) == 1
        containers = get_containers_by_name(docs[0], include_init_containers=True)
        assert get_env_vars_dict(containers["houston-bootstrapper"]["env"])["SCHEMA_NAME"] == "public"

    @pytest.mark.parametrize("schema_name", [DEFAULT_SCHEMA, "my_custom"])
    def test_schema_reaches_the_postgres_exporter_queries(self, kube_version, schema_name):
        """Test that the exporter's search_path follows the configured schema.

        These queries read Houston's tables through search_path, so a stale
        "houston$default, public" would find nothing on an install using another
        schema -- the query errors rather than degrading. Only a "public" override
        would have survived by coincidence.
        """
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "prometheusPostgresExporter": {"enabled": True},
                    "houston": {"schemaName": schema_name},
                }
            },
            show_only=["charts/prometheus-postgres-exporter/templates/configmap.yaml"],
        )

        assert len(docs) == 1
        queries = docs[0]["data"]["config.yaml"]
        assert f'SET search_path TO "{schema_name}", public;' in queries
        # The whole query must survive templating, not just the search_path.
        assert 'from "Deployment"' in queries

    def test_schema_is_consistent_across_the_whole_release(self, kube_version):
        """Test that a full render never mixes schema values.

        The failure this guards against is a new template hardcoding the literal
        again, which would silently point one component at a different schema.
        """
        docs = render_chart(kube_version=kube_version, values={"global": {"houston": {"schemaName": "public"}}})

        found = set()
        for doc in docs:
            pod_containers = get_containers_by_name(doc, include_init_containers=True) if "spec" in doc else {}
            for container in pod_containers.values():
                env = get_env_vars_dict(container.get("env") or [])
                for name in ("SCHEMA_NAME", "DATABASE_SCHEMA_NAME"):
                    if name in env:
                        found.add(env[name])

        assert found == {"public"}, f"schema values disagree across the release: {found}"
