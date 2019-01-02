---
title: "Configuration"
description: "Configuring your EE Installation."
date: 2018-10-12T00:00:00.000Z
slug: "ee-configuration"
menu: ["Installation"]
position: [2]
---
This guide describes different ways of configuring your EE installation (AWS).


## Auth

Astronomer ships with [auth0](https://auth0.com/), which can be used to integrate different SSO accounts.

We leave it to you to integrate your auth system with auth0.

For example, if you wanted to integrate with Okta, you would need to your own auth0 account and plug your values here:

https://github.com/astronomer/helm.astronomer.io/blob/master/charts/astronomer/values.yaml#L44-L48
```
enabled: true
clientId: "rH2L4yKctlepniTyJW3MkuXuTreOHHn1"
baseDomain: "astronomerio.auth0.com"
externalLogin: false```

### Do you support MFA Authentication?

Yes, Multi-factor Authentication is pluggable with auth0 - you'll just have to enable it on your end.

Check out these docs: https://auth0.com/docs/multifactor-authentication

## Accessing the Platform

### Do I absolutely need a base domain?

Yes. There is unfortunately no work-around to the base domain requirement. In order to properly install each part of our platform, we absolutely need a base domain as a foundation.
For example, if companyx.com was your base domain, we’d create houston.companyx.com (our API), or astronomer.companyx.cloud.io etc. for you to access all parts of your deployment, and there’s unfortunately no way to abstract that.

Once you have a base domain set up, you can use a cert manager to generate a short-lived wildcard, which should be relatively easy. (Check out a blog from LetsEncrypt that might help [here](https://www.bennadel.com/blog/3420-obtaining-a-wildcard-ssl-certificate-from-letsencrypt-using-the-dns-challenge.htm])).

### How is the DNS configured? If I wanted to change or replace my base domain, could I?

Yes, you could! Currently, we have the domain setup with a wildcard CNAME record that points to the ELB DNS route. Swapping out domains would just require adding that CNAME record to your DNS, and recreating the `astronomer-tls` secret to use the updated wildcard certificate for your domain.

### How is SSL handled?
We handle ssl termination at the ssl layer, and the proxy request back to the SSL server is HTTP - so you don’t need to do any SSL stuff from your end!

It is possible to run a single NAT that all internet bound traffic flows through (we use this solution in for our Cloud product). If you are interested in this, please reach out to us.

### How does Astronomer command the cluster? (Add and remove pods, etc.)

Kubectl is the command line interface that can manipulate the cluster as needed, and setup helm/tiller services to deploy the astronomer platform. [Our Kubectl guide](https://www.astronomer.io/guides/kubectl/) might help.

If you are on EKS, you'll need a roll to manage the cluster. For the IAM policy, we should only need the `AmazonEKSServicePolicy` and the `AmazonEKSServicePolicy`.
Once the kubernetes cluster is created, the IAM user will need to be added to the cluster configMap as described [here](https://docs.aws.amazon.com/eks/latest/userguide/add-user-role.html).

### How much access do I need to give Astronomer?

It depends  The above permissions are primarily to help troubleshoot while you're getting setting up. There are a few added dependencies that need to be configured, such as grabbing the DNS name from the provisioned ELB and creating a CNAME record in the DNS. If broad access is a blocker, that can be done by someone on your end.
As long as we're able to authenticate an IAM user against the kubernetes cluster using those EKS policies, that should keep us moving.

A common route our customers go down is giving Astronomer access for installation, and then removing it down the line.

### Does it matter if I run RDS Postgres, CloudSQL or helm's stable postgres to run in Kubernetes?

In the long-term, a managed Postgres (RDS/CloudSQL) is probably the best option.
However, if you are just testing things out, stable postgres should be fine. Howeve,r you will run into limitations with it as you scale up the number of deployments.

Make sure to use the most explicit route to that RDS to ensure the Kubernetes cluster can connect to it.

### How do I get access to my Grafana dashboard?

By default, the account that set Astronomer up is the `admin` that has access to Grafana (at grafana.BASEDOMAIN).

To add users to Grafana, follow the steps outlined here:
https://forum.astronomer.io/t/as-an-ee-admin-how-do-i-give-someone-access-to-grafana/64

### Can Astronomer use AWS ECR (Elastic Container Registry) instead of its own private registry?

Unfortunately, that is not something we currently support. We use a private registry in order to leverage webhooks which auto-update deployments with the latest image.

If you've looked into private/public zones in your cluster, the cluster should in theory have one nodepool on the VPN and one nodepool publickly available.
If you're trying to reach the private registry from something like circle-ci, that might solve your problem.


## Cluster Sizing

### Does the size of my cluster matter?

It depends on your workload. At the lowest end we just need as much power from a virtual machine as your standard laptop.

You can stick to a standard or small machine type for the EC2.
A low base machine type should be fine for that, and you’ll just need to be able to run:
(1) Heptio authenticator
(2) Astronomer CLI
(3) Kubectl.

Note that we recommend using a few larger nodes than many smaller nodes for most workloads.

### What limits and quotas do you default to on our instance?

You can confgure the default settings on your installation [here](https://github.com/astronomer/helm.astronomer.io/tree/master/charts).
