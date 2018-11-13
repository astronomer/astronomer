---
title: "Installing Postgres for Astronomer"
description: "Install Postgres for Astronomer"
date: 2018-07-17T00:00:00.000Z
slug: "ee-installation-postgres"
---

## Create a Kubernetes secret with your PostgreSQL connection

If you do not already have a PostgreSQL cluster, we recommend using a service
like Compose, Amazon RDS, or Google Cloud SQL.

The PostgreSQL user needs permissions to create users, schemas, databases, and tables.

### Cloud SQL
If using Cloud SQL to host your postgres DB in Google Cloud, you can use the SQL Proxy service to enable the Kubernetes cluster to communicate with the Cloud SQL DB. More about setting up this esrvice via helm can be found [here](https://github.com/helm/charts/tree/master/stable/gcloud-sqlproxy)

```Note: It's important to note that the max connections allowed for your Cloud SQL postgres are dictaed but the RAM allocated to the instance. For a standard 2 airflow deployment install, we recommend a minimum of 150 max connections. More about Cloud SQL connection quotas [here](https://cloud.google.com/sql/docs/quotas).```

### RDS
If using RDS to host your postgres instance, ensure your kubernetes cluster can communicate with your RDS postgres instance. This may require modyfying your security groups and VPC rules to ensure access. More information about setting up your RDS Postgres can be found [here](https://aws.amazon.com/rds/postgresql/)


### Stable Postgres
For testing purposes, you can quickly get started using the PostgreSQL helm chart.

Run:

```shell
helm install --name astro-db stable/postgresql --namespace astronomer
```
