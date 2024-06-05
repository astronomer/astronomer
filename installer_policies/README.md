

## Why

1. Because users frequently won't have ClusterAdmin so we need to test to make sure we know what permissions they do need.
2. Because in single-namespace mode, we allow them to pre-create the commander role manually and the permissions required
   vary based on what features they want to enable.
3. Because in namespace pools mode, when they don't opt-out of automatic namespace role creation the user helm runs as needs
   every permission it grants to that role even if it doesnt create the resource due to kubernetes guarding against privilege
   escalation. Name roles needed for privilege esecalation only to contain `-delegate-only-`.

## Usage:

When defining testing criteria involving the installation of an Astronomer Software or Astronomer
Features that require Kubernetes API permissions always specify one of the presonas defined in this document.

Prior to installing Astronomer:

Replace `<astronomer-platform-namespace>` in `personas.yaml`
If using namespace pools mode, also replace `<astronomer-platform-namespace>` in `namespace-personas.yaml`

Use kubectl apply to install all the personas and then select the one you with to use by adding
 `--kube-as-user <persona-service-account-name>` when you perfrom the Astronomer helm chart installation.

e.g. For a standard namespace installation

```
kubectl -n astronomer apply -f personas.yaml
helm --kube-as-user astronomer-installer-persona-lowbie -n upgrade --install astronomer astronomer/astronomer
```

e.g. For a namespacepools installation

```
kubectl -n astronomer apply -f personas.yaml
kubectl -n some-airflow-namespace-1 apply -f namespace-personas.yaml
kubectl -n some-airflow-namespace-2 apply -f namespace-personas.yaml
kubectl -n some-airflow-namespace-3 apply -f namespace-personas.yaml
helm --kube-as-user astronomer-installer-persona-lowbie -n upgrade --install astronomer astronomer/astronomer
```

When testing, a brief throw-away installation with `--no-hooks --timeout 10s` will catch a lot of common errors
quickly without waiting for a full platform install. Make sure to delete the install since installation hooks won't have run.

## Personas
These personas likely need fixup.
* astronomer-installer-persona-superadmin - every permission you neeed to use every feature
* astronomer-installer-persona-lowbie - a user with almost no permissions that should have no access to any cluster-role scoped resources, quotas, limitranges, etc. (please review this persona, that may not be currnently the case)
* other tbd personas

## Roles and Cluster/Roles
Note: role names listed here have the prefix of `astronomer-installer-` replaced with `-`.
* -clusterrole-management - manage clusterroles
* -namespace-management - manage namespaces
* -essential - misc permissions that are always required
* -namespace-essential - misc permissions that are always required in each namespace when using namespace pools mode
* -namespace-essential-contenious - misc permissions that users wont be allowed - should probably be split into multiple more-descriptive roles
* -namespace-possibly-obsolete - misc permissions that may or may not be required

## Persona-role matrix
To make the table easier to read, please note that:
* role names listed here have the prefix of `astronomer-installer-` replaced with `-`.
* persona names listed here have the prefix of `astronomer-installer-persona-lowbie` replaced with `-`.
* Roles with `cluster` in the Cluster column are actually ClusterRoles, not Roles

| Role/ClusterRole Name    | Scope   | -superadmin | -lowbie |
| ------------------------ | ------- | ----------- | ------- |
| -clusterrole-management  | cluster | yes         |         |
| -namespace-management    | cluster | yes         |         |
| -essential               |         | yes         | yes     |
| -namespace-essential     |         | yes         | yes     |
| -namespace-contentious   |         | yes         |         |

