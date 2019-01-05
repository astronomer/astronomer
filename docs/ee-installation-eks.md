---
title: "AWS EKS"
description: "Installing Astronomer on AWS EKS."
date: 2018-10-12T00:00:00.000Z
slug: "ee-installation-eks"
menu: ["Installation"]
position: [2]
---
This guide describes the prerequisite steps to install Astronomer on Amazon Web Services (AWS).

## Are you devops-y enough to do this alone?

You will need to be able to:

* Obtain a wildcard SSL certificate
* Edit your DNS records
* Create resources on AWS
* Install/run Kubernetes command line tools to your machine

## Prerequisites

Before running the Astronomer install command you must:

1. [Set up an EKS cluster](https://docs.aws.amazon.com/eks/latest/userguide/getting-started.html)
2. [Select a base domain](https://astronomer.io/docs/ee-installation-base-domain)
3. [Get your machine setup with needed dev tools](https://astronomer.io/docs/ee-installation-dev-env)
4. [Create a stateful storage set](https://astronomer.io/docs/ee-installation-aws-stateful-set)
5. [Get a Postgres server running](https://astronomer.io/docs/ee-installation-postgres)
6. [Obtain SSL](https://astronomer.io/docs/ee-installation-ssl)
7. [Install Helm and Tiller](https://astronomer.io/docs/ee-installation-helm)
8. [Set a few Kubernetes secrets](https://astronomer.io/docs/ee-installation-k8s-secrets)
9. [Build your config.yaml](https://astronomer.io/docs/ee-installation-config)


## Install Astronomer

You're ready to go!

```shell
helm install -f config.yaml . --namespace astronomer
```

## DNS routing

Your final step is to setup your DNS to route traffic to your airflow resources following [these steps](https://astronomer.io/docs/ee-installation-aws-dns).

Click the link in the output notes to log in to the Astronomer app.

---
