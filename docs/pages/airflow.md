---
layout: page
title: Airflow
permalink: /airflow/
order: 1
---

## Quickstart
If you haven't already, clone the repository by running the following: `git clone https://github.com/astronomerio/astronomer.git` and change into the repository directory.

To get up and running quickly and poke around with Apache Airflow on Astronomer, pop open a terminal and run `cd examples/airflow && docker-compose up`. This will spin up a handful of containers to closely mimic a live Astronomer environment.

First, we spin up a [Postgres](https://www.postgresql.org/) container for the Airflow metadata database, and a [Redis](https://redis.io/) container to back [Celery](http://www.celeryproject.org/), which Airflow will use for its task queue. Once the storage containers have started, we start the Airflow Scheduler, Airflow Webserver, a Celery worker, and the [Flower UI](http://flower.readthedocs.io/en/latest/) to monitor the Celery task queue. Once everything is up and running, open a browser tab and visit http://localhost:8080 for the Airflow UI and http://localhost:5555 for the Celery UI.

Sweet! You're up and running with Apache Airflow and well on your way to automating all your data pipelines! The following sections will help you get started with your first pipelines, or get your existing pipelines running on the Astronomer Platform.

## Starting from Nothing
You need to write your first DAG. Review:

* [Core Airflow Concepts](https://docs.astronomer.io/v2/apache_airflow/tutorial/core-airflow-concepts.html)
* [Simple Sample DAG](https://docs.astronomer.io/v2/apache_airflow/tutorial/sample-dag.html)

We recommend managing your DAGs in a Git repo, but for the purposes of getting rolling, just make a directory on your machine with a `dags` directory, and you can copy the sample dag from the link above into the folder inside a file `test_dag.py`.

## Starting from an existing Airflow project
If you already have an Airflow project (Airflow home directory), getting things running on Astronomer should be pretty straightworard. Within `examples/airflow`, we also provide a `run` script that can wire up a few things to help you develop on Airflow quickly.

You'll also notice a small `.env` file next to the `docker-compose.yml` file. This file is automatically sourced by `docker-compose` and it's variables are interpolated into the service definitions in the `docker-compose.yml` file. If you run `docker-compose up`, like we did above, we mount volumes into your host machine's `/tmp` directory for Postgres and Redis. This will automatically be cleaned up for you.

This will also be the behaviour if you run `./run` with no arguments. If you want to load your own Airflow project into this system, just provide the project's path as an argument to run, like this: `./run ~/repos/airflow-project`.

Under the hood, we do a few things to make this work. We will write some simple `Dockerfile.astro` and `.dockerignore` files into your project directory. We will also create a `.astro` directory.
- `Dockerfile.astro` just links to a special `onbuild` version of our Airflow image that will automatically add certain files, within the `.astro` directory to the image.
- The `.astro` file will contain a `data` directory which will be used for mapping docker volumes into for Postgres and Redis. This lets you persist your current Airflow state between shutdowns. These files are automatically ignored by `git`.
- The `.astro` directory will also contain a `requirements.txt` file that you can add python packages to be installed using `pip`. We will automatically build and install them when the containers are restarted.
- In some cases, python modules will need to compile native modules and/or rely on other package that exist outside of the python ecosystem. In this case, we also provide a `packages.txt` file in the `.astro` directory, where you can add [Alpine packages](https://pkgs.alpinelinux.org/packages). The format is similar to `requirements.txt`, with a package on each line. If you run into a situation where you need more control or further assistance, please reach out to humans@astronomer.io.

With this configuration, you can point the `./run` script at any Airflow home directory and maintain distinct and separate environments for each, allowing you to easily work on different projects in isolation.
