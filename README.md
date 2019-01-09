# The Astronomer Platform

Astronomer is a commercial "Airflow as a Service" platform that runs on Kubernetes. Source code is made avaialable for the benefit of our customers, if you'd like to use the platform reach out for a license or try out [Astronomer Cloud](https://www.astronomer.io/cloud/).

## Components

* [airflow](https://github.com/apache/airflow) - Airflow is the star of the show
* [astronomer](https://github.com/astronomer/astronomer) - This repo, Docker images for the platform
* [helm.astronomer.io](https://github.com/astronomer/helm.astronomer.io) - Helm charts for the platform
* [orbit-ui](https://github.com/astronomer/orbit-ui) - React UI for the platform
* [houston-api](https://github.com/astronomer/houston-api) - GraphQL API for the platform
* [houston-api-2](https://github.com/astronomer/houston-api-2) - Prisma-based GraphQL API for the platform (coming soon)
* [commander](https://github.com/astronomer/commander)	- gRPC service to communicate between our API and Kubernetes
* [astro-cli](https://github.com/astronomer/astro-cli) - Go-based CLI for the platform
* [db-bootstrapper](https://github.com/astronomer/db-bootstrapper) - used to setup database for new Airflow deployments

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

* Source Code: <https://github.com/astronomer/astronomer>
* Issue Tracker: <https://github.com/astronomer/astronomer/issues>

## License

Usage of Astronomer requires an [Astronomer Platform Enterprise Edition license](https://github.com/astronomer/astronomer/blob/master/LICENSE).
