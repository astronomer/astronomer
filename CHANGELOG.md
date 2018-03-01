# Changelog

All notable changes to this project will be documented in this file.

## [0.1.2] - 2018-03-01

* Add /healthz to default backend

## [0.1.1] - 2018-02-28

* Add platform default backend

## [0.1.0] - 2018-02-26

* Initial public release

## [0.0.34] - 2018-02-24

* Add relabelling rules to prometheus and updated metric names in grafana dashboard.

## [0.0.30] - 2018-02-21

* Added nginx image.
* Removed basic auth via env from registry in favor of nginx.

## [0.0.27] - 2018-02-04

* Bump commander and phoenix. Adds support for private docker registry.

## [0.0.23] - 2018-02-03

* Entrypoint script for docker registry.

## [0.0.22] - 2018-02-03

* Added Module/Component labels.
* Fixed phoenix image.

## [0.0.19] - 2018-02-02

* Added Registry.

## [0.0.18] - 2018-02-01

* Added Commander.
* Added Phoenix.

## [0.0.17] - 2018-01-26

* Added labels for open.

## [0.0.16] - 2018-01-12

* Changed Airflow worker-gc environment variable name.

## [0.0.15] - 2018-01-10

* Added support for clearing worker logs after x days.
* Removed Snakebite python package due to compatibility issues with python 3.

## [0.0.14] - 2018-01-08

* Fixed busted grafana build.

## [0.0.13] - 2018-01-07

* Added support for passing default prometheus host for grafana datasource.

## [0.0.12] - 2018-01-07

* Changed Prometheus config file name and paths.

## [0.0.11] - 2018-01-05

* Added Prometheus Marathon config.

## [0.0.10] - 2018-01-04

* Added Python and pip symlinks to python3 and pip3.
* Removed usage of .astro directory in start script.

## [0.0.9] - 2018-01-04

* Added vendor images.

## [0.0.8] - 2018-01-03

* Added Tini init system.

## [0.0.5] - 2017-12-15

* Added support for Airflow onbuild tags.

## [0.0.4] - 2017-12-15

* Added this Changelog
* Added StatsD package to Airflow
* Added StatsD exporter to stack.
* Added Prometheus to stack.
* Added Grafana to stack.
* Airflow scripts now run docker-compose with -d flag.
