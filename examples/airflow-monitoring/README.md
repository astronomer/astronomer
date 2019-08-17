# Airflow monitoring stack

This docker-compose file loads up:

* postgres
* statsd-exporter
* prometheus
* grafana
* cadvisor

## Requirements

### Python 3.6

Using pyenv is good on Mac, this might help you install if you get an error:

```
CFLAGS="-I$(brew --prefix readline)/include -I$(brew --prefix openssl)/include -I$(xcrun --show-sdk-path)/usr/include" \
LDFLAGS="-L$(brew --prefix readline)/lib -L$(brew --prefix openssl)/lib" \
PYTHON_CONFIGURE_OPTS=--enable-unicode=ucs2 \
pyenv install -v 3.6.8
```

## docker-compose

Run Docker on your machine, and fire up these containers with `docker-compose up`

You may need to nuke Docker from time-to-time, these commands are useful:

```
docker-compose down -v
docker system prune
```

## virtualenv

Run Airflow yourself using `virtualenv` and `virtualenvwrapper`. This lets you run and tweak Airflow from a checked-out repository which allows you to iterate on Airflow features without having to rebuild Docker images for each change.

Switch to your locally checked out Airflow source directory and

```
# if using virtualenvwrapper
workon airflow

# if using virtualenv
source {virtualenv_install_dir}/bin/activate
```

Install python packages in editable mode:

```
pip install -e ".[statsd,postgres]"
```

if you are installing from apache/master, you will need to setup the node environment described [here](https://github.com/apache/airflow/blob/master/CONTRIBUTING.md#setting-up-the-node--npm-javascript-environment)

In particular, be sure to run these commands:

```
cd airflow/www/
npm install
```

From there you can run Airflow commands such as:

```
airflow initdb
airflow version
```

At this point, if you want to use postgres instead of sqllite, you can modify you airflow.cfg to point to postgres running in your docker-compose stack:

```
executor = LocalExecutor
sql_alchemy_conn = postgres://postgres:postgres@localhost:5432
```

Then init the db again

```airflow initdb```

# create a user

```
airflow users create --username admin --password admin --role Admin --email me@example.org --firstname admin --lastname admin
```

## Airflow project

From your Airflow project's airflow.cfg (~/airflow)

Set these:

```
statsd_on = True
statsd_port = 9102
```

## Starting up Airflow

Run Airflow Webserver and Scheduler in terminal tabs:

```
airflow webserver
airflow scheduler
```

## Server URLs

* Airflow Webserver: http://localhost:8080
* StatsD-Exporter: http://localhost:9102
* Prometheus: http://localhost:9090
* Grafana: http://localhost:3000
