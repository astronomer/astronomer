---
layout: page
title: The Astronomer Platform
permalink: /
order: 1
---

## Overview
This repository contains everything you need to get up and running with the Astronomer Platform. It is made up of Dockerfiles, docker-compose files, and some bash scripts.

## Requirements
The only requirement to get up and running are the Docker Engine and Docker Compose. If you don't have these installed already, visit these links for more information.
- [Docker Engine](https://docs.docker.com/engine/installation/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Quickstart
To get up and running quickly, we have provided a several docker-compose files for quickly spinning up different components of the platform. Simply `cd` into `examples/${component}` and run `docker-compose up`. Some directories will have additional scripts to wrap some useful functionality around `docker-compose up`. These are documented on their respective pages.

Running `docker-compose up` will download our prebuild images (see Makefile for details) from our [DockerHub Repository](https://hub.docker.com/u/astronomerinc/) and spin up containers running the various platform systems.

## Building the Images
All platform images are built from a minimal [Alpine Linux](https://alpinelinux.org/) base image to keep our footprint minimal and secure.
To build the images from scratch run `make build-alpine` in your terminal. If you've already downloaded the images from DockerHub, this will replace them. These images will be used when running the platform locally.

## Building the Documentation
Documentation is built on jekyll and currently hosted on GitHub pages. To run the docs site locally:
- `cd docs`
- `bundle install`
- `bundle exec jekyll serve`
