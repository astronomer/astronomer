from airflow.hooks.mysql_hook import MySqlHook
from airflow.hooks.postgres_hook import PostgresHook
from airflow.utils.decorators import apply_defaults
from airflow.models import BaseOperator

class MySQLToPostgresOperator(BaseOperator):
    @apply_defaults
    def __init__(self, mysql_query, postgres_table, mysql_conn_id='mysql_default', postgres_conn_id='postgres_default', *args, **kwargs):
        super(MySQLToPostgresOperator, self).__init__(*args, **kwargs)
        self.mysql_query = mysql_query
        self.mysql_conn_id = mysql_conn_id
        self.postgres_table = postgres_table
        self.postgres_conn_id = postgres_conn_id

    def execute(self, context):
        mysql_hook = MySqlHook(mysql_conn_id=self.mysql_conn_id)
        records = mysql_hook.get_records(self.mysql_query)

        pg_hook = PostgresHook(postgres_conn_id=self.postgres_conn_id)
        pg_hook.insert_rows(table=self.postgres_table, rows=records)
