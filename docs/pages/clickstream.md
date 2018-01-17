---
layout: page
title: Clickstream
permalink: /clickstream/
order: 2
---

## Architecture

The Astronomer Clickstream module consists of nine components, and you must bring
your own Kafka, Postgres and Redis database, as well as a container deployment
strategy for your cloud.

![Clickstream Module]({{ "/assets/img/clickstream_module.png" | absolute_url }})

## How To's

* [Add Clickstream Destination](/astronomer/clickstream/add_destination)
