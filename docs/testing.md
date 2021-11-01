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
