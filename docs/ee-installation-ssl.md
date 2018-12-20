---
title: "SSL"
description: "Getting an SSL certificate for Astronomer"
date: 2018-07-17T00:00:00.000Z
slug: "ee-installation-ssl"
---

## Installing on a Subdomain

The base domain requirement is an absolute must to install the Astronomer platform. In order to properly install each part of our platform, we'll need a base domain as a foundation.

We'd recommend doing the install either (1) on a subdomain or (2) acquiring a new domain, instead of installing it on your root domain. If you don't have a preference, a good default subdomain is `astro`. 

For the purpose of this guide, we'll continue to use `astro.mydomain.com` as an example.

## Obtaining an SSL Cert

You'll need to obtain a wildcard SSL certificate for `*.astro.mydomain.com` not
only to protect the web endpoints (so it's `https://app.astro.mydomain.com`)
but is also used by Astronomer inside the platform to use TLS encryption between
pods.

* Buy a wildcard certificate from wherever you normally buy SSL
* Get a free 90-day wildcard certificate from [Let's Encrypt](https://letsencrypt.org/)

We recommend purchasing a TLS certificate signed by a Trusted CA. Alternatively, you can follow the guide below to manually generate a trusted wildcard certificate via Let's Encrypt (90 day expiration).  This certificate generation process and renewal can be automated in a production environment with a little more setup.

**Note:** Self-signed certificates are not supported on the Astronomer Platform.

Run (Linux):

```shell
docker run -it --rm --name letsencrypt -v /etc/letsencrypt:/etc/letsencrypt -v /var/lib/letsencrypt:/var/lib/letsencrypt certbot/certbot:latest certonly -d "*.astro.mycompany.com" --manual --preferred-challenges dns --server https://acme-v02.api.letsencrypt.org/directory
```

Run (macOS):

```shell
docker run -it --rm --name letsencrypt -v /Users/<my-username>/<my-project>/letsencrypt1:/etc/letsencrypt -v /Users/<my-username>/<my-project>/letsencrypt2:/var/lib/letsencrypt certbot/certbot:latest certonly -d "*.astro.mycompany.com" --manual --preferred-challenges dns --server https://acme-v02.api.letsencrypt.org/directory
```

**Note:** This changes the 2 volume mount paths (beginning with `-v` before the colon) to host paths accessible to Docker for Mac.

Sample output:

```plain
Saving debug log to /var/log/letsencrypt/letsencrypt.log
Plugins selected: Authenticator manual, Installer None
Obtaining a new certificate
Performing the following challenges:
dns-01 challenge for astro.mycompany.com

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
NOTE: The IP of this machine will be publicly logged as having requested this
certificate. If you're running certbot in manual mode on a machine that is not
your server, please ensure you're okay with that.

Are you OK with your IP being logged?
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
(Y)es/(N)o: y

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Please deploy a DNS TXT record under the name
_acme-challenge.astro.mycompany.com with the following value:

0CDuwkP_vNOfIgI7RMiY0DBZO5lLHugSo7UsSVpL6ok

Before continuing, verify the record is deployed.
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Press Enter to Continue
```

Follow the directions in the output to perform the domain challenge by adding the DNS TXT record mentioned.  Follow your DNS provider's guidance for how to set the TXT record.

We recommend temporarily setting a short time to live (TTL) value for the DNS record should you need to retry creating the cert.

## Renewing your Cert

To renew your cert, you have two options:

- (1) Set to auto renew via a cert manager through kube-lego. More info about that here: http://docs.cert-manager.io/en/latest/index.html

- (2) Generate a new short lived certificate and follow the same process to recreate your astronomer-tls secret after deleting the current one.

**Note:** After updating your secret, you'll also want to restart the houston, nginx and registry pods to ensure they pick up the new certificate.
