# Updating Astronomer
This guide contains information about upgrading and downgrading between Astronomer platform versions.

## Astronomer 0.10.0
With this release we modified how Houston's JWTs signing certificate is generated and stored in Kubernetes secrets. A standard `helm upgrade` may cause the original Houston pod to lock up, preventing the new pod from starting up. To avoid this, you can `helm delete --purge <relase-name>`, followed by a `helm install -n <release-name> -f my-config.yaml .`.

## Astronomer 0.9.5
With this release, we removed all individual oauth providers and replaced with a more generic OpenID Connect (OIDC) provider. As part of this upgrade the auth section of Houston's configuration has been slightly modified.

Most provider specific configuration has been moved under a new section, `auth.openidConnect`. For example, `auth.auth0.enabled` has been moved to `auth.openidConnect.auth0.enabled`. OIDC provider `baseDomain` fields have been switch to `discoveryUrl`.
