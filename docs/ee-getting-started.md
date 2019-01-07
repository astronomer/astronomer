---
title: "Getting Started with Astronomer Enterprise Edition"
date: 2018-10-12T00:00:00.000Z
slug: "ee-getting-started"
menu: ["Enterprise Edition"]
position: [3]
---

Astronomer Enterprise is designed to be a cloud agnostic solution for running Apache Airflow at scale.


<iframe width="560" height="315" src="https://www.youtube.com/embed/02au2O3vDTk" frameborder="0" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>

## Install
We've written installation docs for various Kubernetes distributions:

- [Astronomer on Kubernetes](https://www.astronomer.io/docs/ee-installation-general-kubernetes/)
- [Amazon Web Services - EKS](https://www.astronomer.io/docs/ee-installation-eks/)
- [Google Cloud Platform - GKE](https://www.astronomer.io/docs/ee-installation-gke/)

## Trying it out

If you want to get a sense of what using Astronomer Enterprise is like, we have a few options:

1. **Astronomer Cloud.**

At its core, Astronomer Cloud is a large scale deployment of Astronomer Enterprise, fully managed by Astronomer's team.
Astronomer Cloud is a SaaS version of Astronomer Enterprise so you'll be able to deploy DAGs and manage Airflow environments the same way as Enterprise, but:

- Astronomer Cloud runs in Astronomer's Cloud, whereas Astronomer Enterprise will run in **your** cloud.
- Astronomer Cloud is billed by usage, whereas Enterprise is billed through an annual license.
- Astronomer Cloud does **not** give users access to the back-end Prometheus/Grafana monitoring stack.
- Astronomer Cloud does **not** give users access to the Kibana interface for logs (coming soon as an Enterprise feature).
- Astronomer Cloud does **not** give you `kubectl` access to your environment.

If this seems like it could be a good way for you to test the platform out, head over to our [cloud sign up page](https://trial.astronomer.io) to start a free 1 month trial!


2. **Try it yourself.**

If you have Kubernetes experience, you are welcome to kick the tires on our platform. Check out our [helm charts](https://github.com/astronomer/helm.astronomer.io) and our install section below to get started. If you are going down this route, contact us at humans@astronomer.io so we can guide you along the way.
