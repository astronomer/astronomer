---
title: "Astronomer Roadmap"
date: 2018-11-02T00:00:00.000Z
slug: "roadmap"
menu: ["Resources"]
position: [2]
---

Below is a summary of our current release plan. If you'd like to request a feature
or upvote something you really want, visit [our Github](https://github.com/astronomer/astronomer-ee/issues).

| Release | Features |
|---------------------------|------------|
| v0.7 | Advanced Alerts — First few synthesized, higher level alerts are introduced that provide higher-level monitoring of your Airflow deployments.<br />Deployment tuning — Users can now fine tune their Airflow deployment resources, including the introduction of AU (“Astronomer Units”). Each AU = 0.1 CPU, 384MB RAM.<br />Change in cloud edition pricing, each AU costs $10/mo.<br />Grafana dashboard improvements — new Grafana dashboards have been created that provide birds eye view of an Airflow deployment, and are a prototype for upcoming Metrics tab in our Orbit UI (our React-based web app) |
| v0.8 | New Logs tab in our Orbit UI for each Airflow deployment, which will present Airflow scheduler and Airflow webserver logs. This feature introduces an Elasticsearch infrastructure dependency, and DevOps gets a Kibana dashboard with access to the log data across Airflow Deployments.<br />Pipe Airflow task logs from Elasticsearch to Airflow UI. Improves core Airflow user experience with faster page load time.<br />New Container Status tab for Airflow deployments, gives end-users a view of how each part of their Airflow deployment is presently functioning.<br />Fix Airflow StatsD Metrics. The dagbag metric emitted from Airflow isn’t correct.<br />High-level metadata from every Astronomer deployment will be shipped periodically to a new service at Astronomer that gives us a birds eye view of all customer activity and configuration, to aid in our ability support customers. |
| v0.9 | Support for multiple Airflow versions & New Airflow RBAC model<br />Support for Kubernetes Executor
Support for executing remote Airflow commands with our Astro CLI<br />View All Image Tags - give end-users a view into their Docker Registry entries<br />Metrics tab for improved end-user monitoring |
| Later | Integration w/ Replicated for easier on-prem deployments<br />Add React to Airflow UI for real-time updates<br />Adoption metrics added to UI and shipped with telemetry - user engagement, Airflow usage growth - we need to give customers and ourselves the ability to measure how well they are adopting Airflow<br />User Audit Logging (Deployments, Configuration changes) - enterprise feature to keep track of who has done what |
