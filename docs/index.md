---
layout: page
homepage: true
isHome: true
title: Astronomer Open Edition
permalink: /
order: 1
---

## Overview

Astronomer Open Edition is a convenient way to experience the
modules of the Astronomer Platform on your own machine. It is
made up of Dockerfiles, docker-compose files, and bash scripts.

Astronomer Open is:

* a preview of the internal components that Astronomer Enterprise Edition is built on
* a demonstration that could be helpful to teams who are seeking to build something similar to our platform

<div class="licensing">
A note on <a href="https://enterprise.astronomer.io">Astronomer
Enterprise Edition</a>: You may be tempted to try to run Open
Edition yourself as a way to save a buck, but you’d be reinventing
the wheel that is Enterprise Edition. Better to just grab an
Enterprise license from us, and then you’ll get support for
everything from us, while still having full access to all the
source code.

To see the value we have added with Astronomer Enterprise, we
suggest you get started with the [astro-cli](https://github.com/astronomerio/astro-cli).
It can be used to run the platform locally. If you like what you
see - it can then be used to manager and deploy Astronomer 
Enterprise Edition on your cluster.
</div>

Because Astronomer Open Edition modules are licensed Apache 2.0,
you can use these Docker containers however you'd like
(subject to standard Apache 2.0 restrictions).

## Requirements

The only requirement to get up and running are the Docker Engine
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
their respective pages.

Running `docker-compose up` will download our prebuild images (see
Makefile for details) from our
[DockerHub Repository](https://hub.docker.com/u/astronomerinc/)
and spin up containers running the various platform systems.

## Guides

Check out our
[various setup guides](https://enterprise.astronomer.io/guides/)
to get started with Astronomer on Kubernetes.

## Modules

* [Clickstream](/clickstream) — Docker images for an
  [Analytics.js](https://github.com/segmentio/analytics.js)-based
  clickstream system with server-side event processing. Includes a
  Go Event API, Apache Kafka, Go Event Router, and server-side
  integration workers that push data off to ~50 common APIs.
* [Airflow](/airflow) — Docker images for
  [Apache Airflow](https://airflow.apache.org/)-based ETL system
  that is pre-configured to run Airflow, Celery, Flower, StatsD,
  Prometheus, and Grafana.

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
