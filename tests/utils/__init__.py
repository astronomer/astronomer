from tests.utils.chart import render_chart  # noqa: F401


def get_env_vars_dict(container_env):
    """
    Convert container environment variables list to a dictionary.
    Args:
        container_env: List of environment variable dictionaries from container spec
    Returns:
        Dictionary mapping env var names to their values or valueFrom references
    """
    return {x["name"]: x["value"] if "value" in x else x["valueFrom"] for x in container_env}
