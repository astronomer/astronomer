import pytest


@pytest.fixture(scope="session")
def cluster_name():
    return "control"
