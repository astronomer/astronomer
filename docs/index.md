---
layout: page
homepage: true
isHome: true
title: Astronomer Open Edition
permalink: /
order: 1
---

## Overview

Astronomer Open Edition is a convenient way to experience the Astronomer
Platform on your own machine. It is made up of Dockerfiles, docker-compose
files, and bash scripts.

Astronomer Open is:

* a preview of the internal components that Astronomer Enterprise Edition is built on
* a demonstration that could be helpful to teams who are seeking to build something similar to our platform

Because Astronomer Open Edition is licensed Apache 2.0, you can use these
Docker containers however you'd like (subject to standard Apache 2.0
restrictions).

You may also be interested to look at
[Astronomer Enterprise Edition](https://enterprise.astronomer.io) which
makes it easy to deploy Apache Airflow clusters and deploy Airflow DAGs
in a multi-team, multi-user environment via Kubernetes.

## Requirements

The only requirement to get up and running is Docker Engine
and Docker Compose. If you don't have these installed already,
visit these links for more information.

* [Docker Engine](https://docs.docker.com/engine/installation/)
* [Docker Compose](https://docs.docker.com/compose/install/)

## Quickstart

To get up and running quickly, we have provided a several
docker-compose files for quickly spinning up different
components of the platform. Simply `cd` into
`examples/${component}` and run `docker-compose up`. Some
directories will have additional scripts to wrap some useful
functionality around `docker-compose up`. These are documented on
their respective sections.

Running just `docker-compose up` will download our prebuild images (see
Makefile for details) from our
[DockerHub Repository](https://hub.docker.com/u/astronomerinc/)
and spin up containers running the various platform systems.

## Building the Images

All platform images are built from a minimal
[Alpine Linux](https://alpinelinux.org/) base image to keep our
footprint minimal and secure.

To build the images from scratch run `make build` in your
terminal. If you've already downloaded the images from DockerHub,
this will replace them. These images will be used when running the
platform locally.

## Building the Documentation

Documentation is built on Jekyll and hosted on Google Cloud Storage.

Build the docs site locally:

```
cd docs
bundle install
```

Run it:

```
bundle exec jekyll serve
```

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

### Airflow Core vs Airflow Enterprise

Here's a comparison of the components included in the Airflow Core vs Airflow Enterprise examples:

{:.table.table-striped.table-bordered.table-hover}
| Component                 | Airflow Core | Airflow Enterprise |
|---------------------------|:------------:|:------------------:|
| Airflow scheduler         | x            | x                  |
| Airflow webserver         | x            | x                  |
| PostgreSQL                | x            | x                  |
| [Redis][redis]            |              | x                  |
| [Celery][celery]          |              | x                  |
| [Flower][flower]          |              | x                  |
| [Prometheus][prometheus]  |              | x                  |
| [Grafana][grafana]        |              | x                  |
| [StatsD exporter][statsd] |              | x                  |
| [cAdvisor][cadvisor]      |              | x                  |

[redis]: https://redis.io/
[celery]: http://www.celeryproject.org/
[flower]: http://flower.readthedocs.io/en/latest/
[grafana]: https://grafana.com
[prometheus]: https://prometheus.io
[cadvisor]: https://github.com/google/cadvisor
[statsd]: https://github.com/prometheus/statsd_exporter

### Airflow Core

To start the simple Airflow example:

```
cd examples/airflow-core
docker-compose up
```

Once everything is up and running, open a browser and visit <http://localhost:8080> for Airflow

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
running on Astronomer is straightforward. Within `examples/${component}`, we provide
a `start` script that can wire up a few things to help you develop on Airflow
quickly.

You'll also notice a small `.env` file next to the `docker-compose.yml` file.
This file is automatically sourced by `docker-compose` and it's variables are
interpolated into the service definitions in the `docker-compose.yml` file.

When running `./start` with no arguments, your Airflow home directory will be set to
`/tmp/astronomer`. If you want to load your own Airflow 
project into this system, just provide the project's path as an argument to run, 
like this: `./start ~/path/to/airflow-project`.

Under the hood, the start script will write a `Dockerfile`, `requirements.txt`, 
and `packages.txt` into your project directory.  A `dags` and `plugins` directory
will also be created if they don't exist.

* `Dockerfile` just links to a special `onbuild` version of our Airflow
  image that will automatically add certain files, within the `.astro` directory
  to the image.
* `requirements.txt` Python dependencies can be be installed using `pip` by adding 
  them to the requirements.txt like any other Python project. We will automatically
  build and install them when the containers are restarted.
* `packages.txt` In some cases, python modules will need to compile native modules and/or rely
  on other package that exist outside of the python ecosystem. In this case, we
  also provide a `packages.txt` file, where you can add 
  [Alpine packages](https://pkgs.alpinelinux.org/packages). The format is similar
  to `requirements.txt`, with a package on each line.

With this configuration, you can point the `./start` script at any Airflow home
directory and maintain distinct and separate environments for each, allowing you
to easily test different Airflow projects in isolation.

Should you have any other directories in your project other than `plugins` and `dags`
you will need to modify the example `docker-compose.yml` to mount `volumes` for them 
as well in the scheduler and webserver (and workers for the enterprise example)

#### Pause and Stop Scripts
You can run `./pause` to stop the Airflow containers but maintain data in the datbase
or you can run `./stop` which will stop and remove the Docker containers, deleting
all the database data.