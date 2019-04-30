# The Astronomer Platform

Astronomer is a commercial "Airflow as a Service" platform that runs on Kubernetes. Source code is made avaialable for the benefit of our customers, if you'd like to use the platform [reach out for a license](https://www.astronomer.io/enterprise/) or try out [Astronomer Cloud](https://www.astronomer.io/cloud/).

## Architecture

![Astronomer Architecture](https://assets2.astronomer.io/main/docs/ee/astronomer_architecture_v0.8.png "Astronomer Architecture")

## Installation Guides

* [Amazon Web Services EKS](https://www.astronomer.io/docs/ee-installation-eks/)
* [Google Cloud Platform GKE](https://www.astronomer.io/docs/ee-installation-gke/)

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
