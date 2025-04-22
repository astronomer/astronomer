def test_cp(cp_cluster):
    assert cp_cluster == "cp_cluster"
    assert "foo" == "bar"


def test_dp(dp_cluster):
    assert dp_cluster == "dp_cluster"
    assert "foo" == "bar"
