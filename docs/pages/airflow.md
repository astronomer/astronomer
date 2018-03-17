---
layout: page
title: Airflow
permalink: /airflow/
order: 1
---

## Architecture

The Astronomer Airflow module consists of seven components, and you must bring
your own Postgres and Redis database, as well as a container deployment strategy
for your cloud.

![Airflow Module]({{ "/assets/img/airflow_module.png" | absolute_url }})

## Quickstart

Clone Astronomer Open:

```
git clone https://github.com/astronomerio/astronomer.git
cd astronomer
```

We provide two examples for Apache Airflow.  Each will spin up a handful of containers to mimic a live Astronomer environment.

### Airflow Lite vs Airflow Enterprise

Here's a comparison of the components included in Airflow Lite vs Airflow Enterprise:

| Component | Airflow Lite | Airflow Enterprise |
|--------- |:----:|:----------:|
| Airflow scheduler | x | x |
| Airflow webserver | x | x |
| PostgreSQL | x | x |
| [Redis](https://redis.io/) |  | x |
| [Celery](http://www.celeryproject.org/) |  | x |
| [Flower](http://flower.readthedocs.io/en/latest/) |  | x |
| [Prometheus](https://prometheus.io) |  | x |
| [Grafana](https://grafana.com) |  | x |
| [StatsD exporter](https://github.com/prometheus/statsd_exporter) |  | x |
| [cAdvisor](https://github.com/google/cadvisor) |  | x |

### Airflow Lite

To start the simple Airflow example:

```
cd examples/airflow-lite
docker-compose up
```

### Airflow Enterprise

To start the more sophisticated Airflow example:

```
cd examples/airflow-enterprise
docker-compose up
```

Once everything is up and running, open a browser and visit <http://localhost:8080> for Airflow and <http://localhost:5555> for Celery.

Sweet! You're up and running with Apache Airflow and well on your way to
automating all your data pipelines! The following sections will help you get
started with your first pipelines, or get your existing pipelines running on
the Astronomer Platform.

## Start from Scratch

You need to write your first DAG. Review:

* [Core Airflow Concepts](https://docs.astronomer.io/v2/apache_airflow/tutorial/core-airflow-concepts.html)
* [Simple Sample DAG](https://docs.astronomer.io/v2/apache_airflow/tutorial/sample-dag.html)

We recommend managing your DAGs in a Git repo, but for the purposes of getting
rolling, just make a directory on your machine with a `dags` directory, and you
can copy the sample dag from the link above into the folder inside a file
`test_dag.py`. We typically advise first testing locally on your machine, before
pushing changes to your staging environment. Once fully tested you can deploy
to your production instance.

When ready to commit new source or destination hooks/operators, our best
practice is to commit these into separate repositories for each plugin.

## Start from Existing Code

If you already have an Airflow project (Airflow home directory), getting things
running on Astronomer is straightforward. Within `examples/airflow`, we provide
a `start` script that can wire up a few things to help you develop on Airflow
quickly.

You'll also notice a small `.env` file next to the `docker-compose.yml` file.
This file is automatically sourced by `docker-compose` and it's variables are
interpolated into the service definitions in the `docker-compose.yml` file. If
you run `docker-compose up`, like we did above, we mount volumes into your host
machine's `/tmp` directory for Postgres and Redis. This will automatically be
cleaned up for you.

This will also be the behavior if you run `./start` with no arguments. If you
want to load your own Airflow project into this system, just provide the
project's path as an argument to run, like this:
`./start ~/repos/airflow-project`.

Under the hood, a few things make this work. `Dockerfile.astro` and
`.dockerignore` files are written into your project directory. And an `.astro`
directory is created.

* `Dockerfile.astro` just links to a special `onbuild` version of our Airflow
  image that will automatically add certain files, within the `.astro` directory
  to the image.
* The `.astro` file will contain a `data` directory which will be used for
  mapping docker volumes into for Postgres and Redis. This lets you persist
  your current Airflow state between shutdowns. These files are automatically
  ignored by `git`.
* The `.astro` directory will also contain a `requirements.txt` file that you
  can add python packages to be installed using `pip`. We will automatically build
  and install them when the containers are restarted.
* In some cases, python modules will need to compile native modules and/or rely
  on other package that exist outside of the python ecosystem. In this case, we
  also provide a `packages.txt` file in the `.astro` directory, where you can add
  [Alpine packages](https://pkgs.alpinelinux.org/packages). The format is similar
  to `requirements.txt`, with a package on each line.

With this configuration, you can point the `./start` script at any Airflow home
directory and maintain distinct and separate environments for each, allowing you
to easily test different Airflow projects in isolation.

## Limitations

### HDFSHook not supported

Astronomer is built on the latest stable versions of everything, including
Python 3. With that said, it doesn't support Airflow's `HDFSHook` and HDFS
operators (we `pip uninstall snakebite` in our dockerfile).

The `HDFSHook`
[depends on](https://github.com/apache/incubator-airflow/blob/b75367bb572e8bbfc1bfd539fbb34a76a5ed484d/setup.py#L129)
the package spotify/snakebite which does not support Python 3. If you are
interested in that package getting Python 3 support, you can follow and
comment on the issue at
[snakebite #62](https://github.com/spotify/snakebite/issues/62). In the
comments, Spotify engineers have stated that the compatibility issue is due to
their library's dependency on protobuf 2.x which doesn't support Python 3.

You can read more info on this issue at:

* [https://issues.apache.org/jira/browse/AIRFLOW-1316](https://issues.apache.org/jira/browse/AIRFLOW-1316)
* [https://github.com/apache/incubator-airflow/pull/2398](https://github.com/apache/incubator-airflow/pull/2398)
* [https://github.com/puckel/docker-airflow/issues/77](https://github.com/puckel/docker-airflow/issues/77)

One workaround you may consider to work with HDFS is putting calls inside in a
Docker container running Python 2 and using Airflow's `DockerOperator`.
