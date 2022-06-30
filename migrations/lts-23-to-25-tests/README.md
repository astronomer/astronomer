# Astronomer LTS 0.23 upgrade testing

## Prerequisites

- helm>=3.6
- Astronomer is added to Helm 3 repositories and up-to-date
- Kubernetes cluster, with Astronomer already installed of version 0.23
- `HELM_CHART_PATH` environment variable is set to a path to the chart in test
- pytest <https://docs.pytest.org/en/stable/getting-started.html>
- testinfra <https://testinfra.readthedocs.io/en/latest/>

## Set up the environment and run the tests
