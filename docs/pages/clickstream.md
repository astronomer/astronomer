---
layout: page
title: Clickstream
permalink: /clickstream/
order: 2
---

## Architecture

The Astronomer Clickstream module consists of six components:

* Event API is built in Go, and its only job is to drop events into Kafka
* Apache Kafka is the data store
* The Event Router republishes events from the main topic to destination-specific topics
* Serverside workers pull data from destination-specific topics and send them to the destination's API
* Metrics from all the containers are scraped by Prometheus
* And the Prometheus metrics are visualized in Grafana

![Clickstream Module]({{ "/assets/img/clickstream_module.png" | absolute_url }})

## How To's

* [Add Clickstream Destination](/astronomer/clickstream/add_destination)
