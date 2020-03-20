# Testing and the Astronomer Platform

Astronomer has a set of test suites to help you
determine if you are ready for the next installation step
or to help you debug issues during this process.
The current test suites are:

- __prereq-tests__ - testing steps used during installation to ensure readiness
- __platform-tests__ - tests run post installation to verify the platform


## prereq-tests

Located in `astronomer/bin/prereq-tests`, these tests use
BATS (a bash testing framework) to ensure you are ready
for the next step of installation.


__0. Prepare for running the tests__

In `astronomer/bin/prereq-tests/config.sh`, there are some
top-level parameters for things like version, domain, and database.


__1. Do I have the right tools?__

```shell
./bin/prereq-tests/run.sh -T
```

This test for tools needed for both user and admin tasks.


__2. Am I ready to install Kubernetes?__

You will need to use the flag that corresponds to the cloud provider.

```shell
# AWS
./bin/prereq-tests/run.sh -A

# GCP
./bin/prereq-tests/run.sh -G
```

This will check that you have the cloud procider tools and permissions.


__3. Is my database available?__

If you are using an existing database, this will check that the installation
process will be able to access it. This will use the configuration set in
`./bin/prereq-tests/config.sh`. You can also choose to have installation
create a database for you, in which case, this test is not needed.

```shell
./bin/prereq-tests/run.sh -D
```


__4. I've installed Kubernetes, is it ready for Astronomer?__

You have now installed Kubernetes, but have you configured
all of the permissions and requirements for Astronomer to install properly?
These tests will let you know.

```shell
# Is my Kubernetes setup correctly??
./bin/prereq-tests/run.sh -K
```


__5. I've installed Astronomer, is it running and accessible?__

There are two test suites to make some basic sanity checks.

```shell
# Are all of the Astronomer components running?
./bin/prereq-tests/run.sh -P

# Can I access from the external domain securely?
./bin/prereq-tests/run.sh -E
```

The first does a simple check to see if the components are
running and not restarting in Kubernetes.
The next section will cover the advanced tests
for ensuring the platform is working as expected.

The second test here tries to use the DNS record you setup
and ensures the TLS certificate is in place and correct.

If you have made it this far, great!
Your Astronomer platform is ready to go.
The next section will tell you how to
run the E2E test for a final verification.


#### Example output for prereq-tests

Passing the tools tests:

```shell
$ ./bin/prereq-tests/run.sh -T

Starting Astronomer prereqs tests


User Tools:
 ✓ Docker
 ✓ Astronomer CLI

2 tests, 0 failures


Admin Tools:
 ✓ Terraform
 ✓ Kubectl
 ✓ Helm

3 tests, 0 failures


Done checking Astronomer prereqs
```

Failing the tools tests:

```shell
$ ./bin/prereq-tests/run.sh -T

Starting Astronomer prereqs tests


User Tools:
 ✓ Docker
 ✓ Astronomer CLI

2 tests, 0 failures


Admin Tools:
 ✗ Terraform
   (in test file bin/prereq-tests/tools/admin.bats, line 19)
     `[ "$output" -ne -1 ]' failed
   Terraform version '0.11.13' does not meet minimum of '0.12.0'
 ✓ Kubectl
 ✓ Helm

3 tests, 1 failure


Done checking Astronomer prereqs
```

In the terminal, failing tests are colored red.


## platform-tests

The platform tests are run against an installed Astronomer platform.
They run a series of suites to ensure that the system and features
are operating correctly from both the CLI and API.
Astronomer runs thes tests against the full platform
for each commit and pull request across five versions of Kubernetes.
(see .circleci/config.yml for details.)

The platform tests exist in https://github.com/astronomer/astronomer_e2e_tests
where you can find more specfic documentation.
They are bundled into a docker image to make it easy to run them
in cluster, but you can also run them directly from that repository.

For most installations, the first step is to run these with Helm.

```shell
# Previously, you installed Astronomer with
helm install ....

# To run the full test suite in cluster...
helm test astronomer
```

You can inspect the pod and logs to see that it completed,
or if it failed, where and why.

You can also run these tests manually, either from your local machine
or from a container in-cluster. To run in-cluster:

```shell
# Create the same pod as using in “helm test”
kubectl apply -f bin/e2e_test/e2e-pod.yaml

# Log into the container to run tests
kubectl exec -it -n astronomer manual-ap-e2e-test bash
```

For more information about what you can do with these
tests, whether you are in-cluster or local,
please see the documenation at
https://github.com/astronomer/astronomer_e2e_tests
.





