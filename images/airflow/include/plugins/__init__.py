from airflow.plugins_manager import AirflowPlugin
from plugins import executors, hooks, operators


class AstronomerPlugin(AirflowPlugin):
    name = "astronomer_plugin"
    executors = [
        executors.AstronomerMesosExecutor,
    ]

    hooks = [
        hooks.FacebookAdsHook
    ]

    operators = [
        operators.MySQLToPostgresOperator
    ]
