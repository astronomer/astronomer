# This file tests the functionality of the control cluster. Each test definition must contain the "control" fixture.
# TODO: see if we can autouse=True if we put the control fixture in the control conftest.py file


def test_houston_check_db_info(houston_api, control):
    """Make assertions about Houston's configuration."""
    houston_db_info = houston_api.check_output("env | grep DATABASE_URL")
    assert "astronomer_houston" in houston_db_info
