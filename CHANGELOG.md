# Changelog

All notable changes to this project will be documented in this file. For more detail on notable features and changes, refer to our [Release Notes](https://www.astronomer.io/docs/release-notes/).

## [0.12.1] - 2020-03-19
- New banner in the Deployment Config page that tells trial users they can't touch configs until they upgrade (Cloud only)
- Limit resource allocation for trials (Cloud only)
- Bugfix: Environment variable key input loses focus on change
- Bugfix: Deployment settings changes not saved
- Bugfix: Allow POST requests to Airflow's REST API
- Bugfix: Recurring /houston-down page
- Bugfix: Auth check redirecting users when it shouldn't (e.g. on reset-password, etc.)
- Bugfix: Airflow version and config links broken

## [0.12.0] - 2020-03-09
- New Astronomer UI
- Zero config platform DB support for initial installation (Enterprise Only)
- Updater service that alerts users when a new version of the platform is available (Enterprise Only)
- Remove Wildcart SSL Certificate Requirement for Astronomer Installation (Enterprise Only)
- Improve SingleNamespace Mode role definitions
- Add `conn:schema` param and update link provided in default airflow_settings.yaml file

## [0.11.0] - 2020-01-24
- Official Debian Image
- Platform-level support for multiple Airflow images
- Support for pre-pushing shared image layers to the platform for faster deploys
- Automated Airflow Deployment Updates
- Alert for Pods Failing to Schedule at Platform Level
- Report current image tag to users
- Improved user search
- Cleanup Airflow Deployment pods that have been evicted/failed/succeeded (adjust config)
- Control Airflow Deployment migrations
- Auto delete deployments that have expired
- Clean up deleted Airflow Deployment data (database, images)
- Allow Service Accounts access to Airflow Webserver / API
- Support for custom node pool for dynamic pods
- Support for Helm 2.15.2
- Support for Global Service Accounts
- Support for customizing what permissions normal users have in platform
- Bugfix: Missing role on Users tab
- Bugfix: Liveness probe for Fluentd
- Bugfix: Exclude curator from restart alarm
- Bugfix: VerifyEmail mutation

## [0.10.3] - 2019-10-28
- Bug fixes

## [0.10.2] - 2019-10-02
- Upgrade commander to pass optional namespace labels (eg: istio)
- Service account query bug fix
- Upgraded / new platform alerts

## [0.10.1] - 2019-09-30
- Upgrade to Airflow 1.10.5
- Kubernetes 1.14+ support
- Improved metrics in Grafana and the UI
- Support for Istio
- Scheduler hangup mitigations
- Admin Panel deployment list
- Fixes for ephemeral storage in Airflow pods
- Added security scans on platform images
- Added multiple integration test suites

## [0.10.0] - 2019-08-22
- Upgrade to Airflow 1.10.4
- Refactored astro subcommands
- Fixes to log viewer in UI
- Updated metrics tab in UI
- System Admin panel
- Security patches in the API
- Limit ephemeral storage on all airflow pods
- Default additional 10AU for KubeExecutor
- Can now set roles for Service Accounts
- Login to CLI with service account
- API standardiztaion and stablilization
- Fix airflow access after reinstalling the platform
- Addressed security issues flagged by clair

## [0.9.7] - 2019-08-09
- Fix incorrect image tag deployment bug
- Fix KubernetesExecutor + custom environment variables bug

## [0.9.6] - 2019-07-19
- Enable in HTTP(S) proxy support for OpenId Connect providers via GLOBAL_AGENT_HTTPS_PROXY environment variable

## [0.9.5] - 2019-07-18
- Update Houston to use OpenId Connect instead of individual providers
- Fix KubernetesExecutor pod-launching RBAC issue
- Pass fernet key to KubernesExecutor pods
- Fix the Astronomer SecurityManager permissions

## [0.9.4] - 2019-07-11
- Pin werkzeug dependency in Airflow image

## [0.9.3] - 2019-07-09
- CLI bug fixes
- Azure internal loadbalancer support
- Houston migration from 0.9.x

## [0.9.2] - 2019-06-24
- Fix local env link and user/password in CLI
- Fix early data load issue in UI metrics
- Fix deployment listing issue in the UI

## [0.9.1] - 2019-06-17
- Support for Okta as oauth integration
- CLI compatibility fixes
- RBAC enabled locally
- Workspace level billing
- Stopped creation of default workspace
- Support for helm 2.14
- Disable email/password auth by default
- Expose deployment metrics in UI and API
- Bug fixes

## [0.9.0] - 2019-05-17
- Full support for the KubernetesExecutor (beta).
- Switched to Airflow RBAC dashboard by default, and integrated with Astronomer RBAC.
- Support for configurable registry backend.
- Fixed createServiceAccount and updateServiceAccount mutations.
- Fix UI caching bug.
- Fix for cascading deletes of Astronomer RoleBindings.
- Fix to prevent logs being truncated in the UI.
- Add streaming logs support to CLI.
- Smarter default backend for NGINX to show custom error pages.
- Fix CLI workflow around switching workspaces.
- Other bug fixes.

## [0.8.2] - 2019-03-15
* Fix bug where custom env vars are not synced to pods.

## [0.8.1] - 2019-03-13
* CLI bug fixes.
* Houston bug fixes.
* Fixed warm shutdown issue in Airflow image.

## [0.8.0] - 2019-03-06
* Replace Houston1 with Houston2, with lots of new configuration available.
* Add Prisma as backend on top of Postgres.
* Adds Elasticsearch, Fluentd and Kibana (EFK) to base platform.
* Implemented elasticsearch task handler in Airflow.
* Streaming webserver/scheduler/worker logs from API, available in the UI.
* Default deployments are now Deployments and not StatefulSets, meaning faster deploys.
* Upgraded Grafana.
* Grafana dashboard improvements.
* Security patches for NGINX ingress.
* Single namespace mode.
* Airflow 1.10.2.

## [0.7.5] - 2018-12-13
* Support upgrades from 0.5.x charts.

## [0.7.4] - 2018-12-06
* Support airflow 1.10.1 environment variables.

## [0.7.3] - 2018-12-05
* Fixed prometheus healthchecks.

## [0.7.2] - 2018-12-02
* Fixed a deployment upgrade issue.

## [0.7.1] - 2018-11-29
* Fixed a migration issue in houston when upgrading.

## [0.7.0] - 2018-11-28
* Added support for platform and airflow deployment alerts on prometheus data.
* Added support for injecting airflow environment variables at runtime through the UI.
* Added support for different airflow executors.
* Added user controls for dynamically adjusting resource allocation and constrains.
* Added airflow chart upgrade functionality.
* Added lots of new grafana dashboards for persistent storage, prometheus, registry, elastic, fluentd, airflow container state and more.
* Updated prometheus chart to fix healthcheck.
* Initial airflow 1.10.1 support.

## [0.6.1] - 2018-09-27
* Bug fixes

## [0.6.0] - 2018-09-26
* Support for Service Accounts and deploying from CI/CD pipelines
* Fixed ingress redirect issue
* Updated to Alpine 3.8 for all images including Airflow
* New automated build pipeline

## [0.5.1] - 2018-09-13
* Support for upgrading individual airflow deployments to latest chart.
* Fix for airflow task logs link on taskinstances page.

## [0.5.0] - 2018-09-10
* Support for the KubernetesPodOperator. Every deployment goes into its own namespace with resource quotas, limits and defaults.
* Support node auto-scaling. All containers are now assigned resource requests/limits.
* Support for database connection pooling. pgbouncer is now deployed with every deployment to pool connections to postgres for all airflow pods (webserver/scheduler/workers/kubepodoperators/etc)
* Grafana enhancements. New pgbouncer and nginx dashboards, fixed some queries (smooth out container metric graphs), and added deployment dropdowns to all dashboards to drill down into specific deployments.
* Fixed worker logs garbage collector
* Faster deploys. Fixed containers from restarting on initial boot, especially noticeable with flower.
* Larger default volume size for workers/prometheus/registry.
* Updated NGINX ingress controller.
* Some new options and configurations in the airflow chart (choosing executor, horizontal pod autoscaling, connection pooling, etc) that will make their way into the deployment configuration in the future.
* Other minor bug fixes and backend enhancements

## [0.4.1] - 2018-08-17
* Added local email/password authentication option
* Integration with Auth0
* Default installation can now use local, Google, or Github as auth providers
* Fixed some Airflow webserver stability issues with a better healthcheck
* Fixed Grafana healthcheck
* Updated Grafana to v5.2.2
* Removed unused Prometheus target
* Larger default volume size on airflow workers

## [0.3.2] - 2018-07-29

* Prevent redis and flower from restarting during deployments.
* All charts protected with NetworkPolicies.
* Improved docker caching, resulting in faster development and faster deployments.

## [0.2.1] - 2018-05-17

* Added nginx-auth secret to houston, fixing issue with airflow deploys being created unsecured

## [0.2.0] - 2018-05-08

* Set astronomer to be the only chart to install by default
* Updated houston chart to save global values as an env
* Updated commander chart to have elevated tiller permissions
* Updated all chart to include version in the chart label

## [0.1.4] - 2018-04-03

* Update airflow docker image to pull in latest setuptools

## [0.1.3] - ---------

* Fix bug with tlsSecret and acme values.

## [0.1.2] - 2018-03-01

* Add /healthz to default backend

## [0.1.1] - 2018-02-28

* Add platform default backend

## [0.1.0] - 2018-02-26

* Initial release
