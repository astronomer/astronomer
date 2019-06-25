# The Astronomer Platform

Astronomer makes it easy to run, monitor, and scale [Apache Airflow](https://github.com/apache/airflow) deployments in our cloud or yours. Source code is made available for the benefit of our customer base.

If you'd like to explore our offerings, [start a 14-Day Trial on Astronomer Cloud](https://astronomer.io/trial/) and take a look at our [Getting Started Guide](https://www.astronomer.io/docs/getting-started/) to get spun up. If you're interested in hosting Astronomer in your own environment, you'll have a chance to indicate interest when filling out the trial form above.

## Architecture

![Astronomer Architecture](https://assets2.astronomer.io/main/docs/ee/astronomer_architecture_v0.8.png "Astronomer Architecture")

## Installation Guides

* [Amazon Web Services EKS](https://www.astronomer.io/docs/ee-installation-eks/)
* [Google Cloud Platform GKE](https://www.astronomer.io/docs/ee-installation-gke/)
* [Digital Ocean Kubernetes](https://preview.astronomer.io/docs/ee-installation-do/)

## Components

* [apache airflow](https://github.com/apache/airflow) - Platform to programmatically author, schedule and monitor workflows.
* [astronomer](https://github.com/astronomer/astronomer) - This repo, Docker images for the platform
* [helm.astronomer.io](https://github.com/astronomer/helm.astronomer.io) - Helm charts for the platform
* [orbit-ui](https://github.com/astronomer/orbit-ui) - React UI for the platform
* [houston-api](https://github.com/astronomer/houston-api) - GraphQL API for the platform
* [commander](https://github.com/astronomer/commander)	- gRPC service to communicate between our API and Kubernetes
* [astro-cli](https://github.com/astronomer/astro-cli) - Go-based CLI for the platform
* [db-bootstrapper](https://github.com/astronomer/db-bootstrapper) - Init container for bootstrapping system databases

## Is it any good?

[Yes](https://news.ycombinator.com/item?id=3067434).

## Docker images

Docker images for deploying and running Astronomer are currently available on
[DockerHub](https://hub.docker.com/u/astronomerinc/).

## Contents of this repo

* The official Dockerfiles that build and install tagged releases of the
  services composing Astronomer.
* Example docker-compose files for running various pieces and configurations of
  the platform.
* Scripts to build, maintain and release tagged versions of the platform.

## Contribute

* Source Code: <https://github.com/astronomer>
* Issue Tracker: <https://github.com/astronomer/astronomer/issues>

## License

Usage of Astronomer requires an [Astronomer Platform Enterprise Edition license](https://github.com/astronomer/astronomer/blob/master/LICENSE).
