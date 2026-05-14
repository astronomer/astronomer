# Astro Private Cloud Helm Chart

This repository contains the helm charts for deploying [Astro Private Cloud (APC)](https://www.astronomer.io/product/astro-private-cloud/) into a Kubernetes cluster.

Astro Private Cloud is your Kubernetes hosted enterprise data platform. Source code is made available for the benefit of our customers. [Contact our sales team](https://www.astronomer.io/get-astronomer) if you'd like to use the platform.

## Documentation

You can read the Astronomer platform documentation at <https://www.astronomer.io/docs/astro-private-cloud>.

## Contributing

We welcome any contributions:

* Report all enhancements, bugs, and tasks as [GitHub issues](https://github.com/astronomerio/helm.astronomer.io/issues)
* Provide fixes or enhancements by opening pull requests in GitHub

## Local Development

See [docs/local-development.md](docs/local-development.md) for instructions on setting up a local development environment, running chart tests, and developing against a local cluster (k3d-based CP/DP setup, or a simpler KinD-based single-cluster setup).

## License

The code in this repo is licensed Apache 2.0 with Commons Clause, however it installs Astronomer components that have a commercial license, and requires a commercial subscription from Astronomer, Inc.

## Optional schema validation

The ./values.schema.json.example file can be used to validate the helm values you are using work with the default airflow chart shipped with this repo. To use it remove the .example postfix from the file and proceed with the helm lint, install, and upgrade commands as normal.
