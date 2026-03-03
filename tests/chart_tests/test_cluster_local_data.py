from tests.utils.chart import render_chart


def test_cluster_local_data_cm_defaults():
    """Test that cluster local data configmap is rendered correctly."""
    docs = render_chart(
        show_only=["charts/astronomer/templates/cluster-local-data.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]

    assert doc["metadata"]["annotations"]["helm.sh/hook"] == "pre-install,pre-upgrade"
    assert doc["metadata"]["annotations"]["helm.sh/hook-weight"] == "-1"
    assert doc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"

    assert doc["data"]["local_cluster_id"]
    assert doc["data"]["local_cluster_id"].lower() == doc["data"]["local_cluster_id"]

    assert not doc["data"].get("flightdeck_db_name")


def test_cluster_local_data_cm_with_features():
    """Test that cluster local data configmap is rendered correctly."""
    values = {"global": {"flightDeck": {"enabled": True}}}

    docs = render_chart(
        values=values,
        show_only=["charts/astronomer/templates/cluster-local-data.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]

    assert doc["metadata"]["annotations"]["helm.sh/hook"] == "pre-install,pre-upgrade"
    assert doc["metadata"]["annotations"]["helm.sh/hook-weight"] == "-1"
    assert doc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"

    assert doc["data"]["local_cluster_id"]
    # postgres changes capitals to lowercase, so local_cluster_id should always be lowercase.
    assert doc["data"]["local_cluster_id"].lower() == doc["data"]["local_cluster_id"]
    assert doc["data"].get("flightdeck_db_name")

    # db-bootstrapper changes dashes to underscores, so dashes are not allowed in the db name.
    allowed_characters = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    assert set(doc["data"]["flightdeck_db_name"]).issubset(allowed_characters)
