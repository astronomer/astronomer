# Docker Images for the Astronomer Platform

[![Maintainability](https://api.codeclimate.com/v1/badges/d69163d70f7c0c4aeeb1/maintainability)](https://codeclimate.com/github/astronomerio/astronomer/maintainability)

Docker images for deploying and running Astronomer Open Edition.
The images are currently available on
[DockerHub](https://hub.docker.com/u/astronomerinc/).

Full documentation for using the images can be found
[here](https://open.astronomer.io).

## Contents

* The official Dockerfiles that build and install tagged releases of the
  services composing Astronomer Open Edition.
* Example docker-compose files for running various pieces and configurations of
  the platform.
* Scripts to build, maintain and release tagged versions of the platform.
* Documentation on running the platform locally for testing and hacking.

## Deploy Docs Site

### Setup

1. Ask Greg to add GCP IAM permissions for the Astronomer prod project.

	- Storage > Storage Admin - to view deployment artifacts
	- Storage > Storage Object Admin - to deploy

1. Ensure jekyll is installed.

1. Ensure python2 is in your $PATH for gsutil.

	For example, if using [pyenv](https://github.com/pyenv/pyenv), run in the project root:

	```sh
	pyenv local 2.7.14
	```

### Deploy

Run:

```sh
make build-docs
make push-docs
```

## Contribute

* Source Code: <https://github.com/astronomerio/astronomer>
* Issue Tracker: <https://github.com/astronomerio/astronomer>

## License

The project is licensed under the Apache 2 license. For more information on the
licenses for each of the individual Astronomer Platform components packaged in
the images, please refer to the respective
[Astronomer Platform documentation for each component](https://open.astronomer.io).
