---
layout: page
title: Airflow
permalink: /airflow/
order: 1
---

## Quickstart
First things first. If you have not already, clone the repository by running the following: `git clone https://github.com/astronomerio/astronomer.git` and change into the repository directory.

To get up and running quickly and poke around with Apache Airflow on Astronomer, pop open a terminal and run `cd examples/airflow && docker-compose up`. This will spin up a handful of containers to closely mimic a live Astronomer environment.

First, we spin up a [Postgres](https://www.postgresql.org/) container for the Airflow metadata database, and a [Redis](https://redis.io/) container to back [Celery](http://www.celeryproject.org/), which Airflow will use for its task queue. Once the storage containers have started, we start the Airflow Scheduler, Airflow Webserver, a Celery worker, and the [Flower UI](http://flower.readthedocs.io/en/latest/) to monitor the Celery task queue. Once everything is up and running, open a browser tab and visit http://localhost:8080 for the Airflow UI and http://localhost:5555 for the Celery UI.

Sweet! You're up and running with Apache Airflow and well on your way to automating all your data pipelines! The following sections will help you get started with your first pipelines, or get your existing pipelines running on the Astronomer Platform.

## Starting from Nothing

## Starting from an existing Airflow project.