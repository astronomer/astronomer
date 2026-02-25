import pytest

from tests.utils.chart import render_chart


class TestFlightDeckMigrations:
    @pytest.mark.parametrize(
        "plane,docs_count,init_containers_count,containers_count", [("data", 0, 0, 0), ("control", 1, 2, 1), ("unified", 1, 2, 1)]
    )
    def test_flightdeck_enabled(self, plane, docs_count, init_containers_count, containers_count):
        """Test that flightdeck works when enabled with various configs."""

        docs = render_chart(
            values={
                "global": {
                    "plane": {"mode": plane},
                    "flightDeck": {"enabled": True},
                },
            },
            show_only=["charts/astronomer/templates/commander/helm-hooks/flightdeck-db-migration-job.yaml"],
        )

        assert len(docs) == docs_count
        if len(docs) > 0:
            assert docs[0]["kind"] == "Job"
            assert docs[0]["metadata"]["name"] == "release-name-flightdeck-db-migrations"
            init_containers = docs[0]["spec"]["template"]["spec"]["initContainers"]
            assert len(init_containers) == init_containers_count
            containers = docs[0]["spec"]["template"]["spec"]["containers"]
            assert len(containers) == containers_count

    @pytest.mark.parametrize(
        "plane,docs_count,init_containers_count,containers_count", [("data", 0, 0, 0), ("control", 1, 2, 1), ("unified", 1, 2, 1)]
    )
    def test_flightdeck_enabled_with_customer_managed_db(self, plane, docs_count, init_containers_count, containers_count):
        """Test that flightdeck works as expected when the customer is providing the logical DB."""

        docs = render_chart(
            values={
                "global": {
                    "plane": {"mode": plane},
                    "flightDeck": {"enabled": True},
                },
            },
            show_only=["charts/astronomer/templates/commander/helm-hooks/flightdeck-db-migration-job.yaml"],
        )

        assert len(docs) == docs_count
        if len(docs) > 0:
            assert docs[0]["kind"] == "Job"
            assert docs[0]["metadata"]["name"] == "release-name-flightdeck-db-migrations"
            init_containers = docs[0]["spec"]["template"]["spec"]["initContainers"]
            assert len(init_containers) == init_containers_count
            containers = docs[0]["spec"]["template"]["spec"]["containers"]
            assert len(containers) == containers_count
