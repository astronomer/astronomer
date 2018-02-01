# Astronomer Platform Kubernetes Deployment
This directory contains a set of [helm](http://helm.sh) charts to deploy the Astronomer Platform to an existing Kubernetes cluster. 

# Deployment Process
Astronomer is composed from a main "core" chart, and several subcharts representing Astronomer modules. These charts are all configured from the values.yaml file in the core Chart (`astronomer` directory). Subcharts can be configured by placing all options under a top-level key that matches the name of the subchart.

To deploy to a production environment, you'll need to override a few options to set up databases, at a minimum. You can also override any settings that have default values in the core values.yaml.

You can override any value in `astronomer/values.yaml` in your override file but only the values in `/override.tpl.yaml` template are necessary. To override those values, rename `/override.tpl.yaml` to `/override.yaml` and fill in missing values. 

Please note that this file is automatically ignored from git, as it will contain sensitive data, like database passwords. Once you have this file saved, run `helm install -f override.yaml astronomer`

# Charts
## Astronomer Core
The Astronomer Core chart creates a namespace for all components and adds core services.

## Astronomer Airflow
The Astronomer Airflow chart adds the following Airflow components:
- Airflow Webserver Service Deployment
- Airflow Scheduler Deployment
- Airflow Celery Workers (configurable amount) StatefulSet
- Flower UI Service Deployment
- StatsD Exporter
- Prometheus
- Grafana
- Ingress to serving components.
