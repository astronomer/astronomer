# Updating Astronomer
This guide contains information about upgrading and downgrading between Astronomer platform versions.

## Astronomer v0.10.0
With this release we modified how Houston's JWT signing certificate is generated and stored in Kubernetes secrets. A typical `helm upgrade` will lock Houston up, preventing the system from fully booting up. To avoid this, you can `helm delete --purge <relase-name>`, followed by a `helm install -n <release-name> -f my-config.yaml . --namespace <my-namespace>` The -n flag on the re-install, must match your old platform name. This ensures Houston re-associates with the correct database.

Once the platform has been upgraded, the airflow webservers will become unavailable (although the scheduler and tasks are still running). To re-gain access, click the "Upgrade" button in the UI to upgrade the airflow deployment. Once the deployment has been upgraded, update the image name in your `Dockerfile` to be `FROM quay.io/astronomer/ap-airflow:0.10.0-1.10.4` and deploy the update. You will need to do this for each airflow deployment.

## Astronomer v0.9.5
With this release, we removed all individual oauth providers and replaced with a more generic OpenID Connect (OIDC) provider. As part of this upgrade the auth section of Houston's configuration has been slightly modified.

Most provider specific configuration has been moved under a new section, `auth.openidConnect`. For example, `auth.auth0.enabled` has been moved to `auth.openidConnect.auth0.enabled`. OIDC provider `baseDomain` fields have been switch to `discoveryUrl`.
