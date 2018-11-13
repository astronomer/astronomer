---
title: "General Kubernetes"
description: "Installing Astronomer Enterprise to your Kubernetes cluster."
date: 2018-10-12T00:00:00.000Z
slug: "ee-installation-general-kubernetes"
menu: ["Installation"]
position: [1]
---

This guide describes the process to install Astronomer on a Kubernetes Cluster

## Are you admin-y enough to do this alone?

You will need to be able to:

* Obtain a wildcard SSL certificate
* Edit your DNS records
* Install/run Kubernetes command line tools to your machine

## Pre-requisites

Before running the Astronomer install command you must:

1. [Select a base domain](/docs/ee-installation-base-domain)
1. [Get your machine setup with needed dev tools](/docs/ee-installation-dev-env)
1. [Get a Postgres server running](/docs/ee-installation-postgres)
1. [Obtain SSL](/docs/ee-installation-ssl)
1. [Setup DNS](/docs/ee-installation-dns)
1. [Install Helm and Tiller](/docs/ee-installation-helm)
1. [Set a few Kubernetes secrets](/docs/ee-installation-k8s-secrets)
1. [Build your config.yaml](/docs/ee-installation-config)

## Install Astronomer

You're ready to go!

```shell
$ helm install -f config.yaml . --namespace astronomer
```

Click the link in the output notes to log in to the Astronomer app.

Feel free to check out our video walkthrough of the Install below:

[![Install](https://img.youtube.com/vi/IoeesuFNG9Q/0.jpg)](https://www.youtube.com/watch?v=IoeesuFNG9Q "Install Video")
