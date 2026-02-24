import pytest

from tests.utils.chart import render_chart


class TestFlightDeckMigrations:
    @pytest.mark.parametrize("plane,docs_count", [("data", 0), ("control", 1), ("unified", 1)])
    def test_flightdeck_migrations_defaults(self, plane, docs_count):
        """Test that flightdeck migrations works as default."""

        docs = render_chart(
            values={"global": {"plane": {"mode": plane}}},
            show_only=["charts/astronomer/templates/commander/helm-hooks/flightdeck-db-migration-job.yaml"],
        )

        assert len(docs) == docs_count
        if docs_count > 0:
            assert docs[0]["kind"] == "Job"
            assert docs[0]["metadata"]["name"] == "release-name-flightdeck-db-migrations"
            init_containers = docs[0]["spec"]["template"]["spec"]["initContainers"]
            assert len(init_containers) == 2
            containers = docs[0]["spec"]["template"]["spec"]["containers"]
            assert len(containers) == 1
