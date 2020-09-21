# Astronomer functional testing

## Prerequisites

- Helm 3 installed as 'helm3'
- Astronomer-internal is added to Helm 3 repositories and up-to-date
- Kubernetes cluster, with Astronomer already installed from this chart in test
- HELM_CHART_PATH environment variable is set to a path to the chart in test

## How does it work?

This is a pytest suite that assumes the current shell is authenticated to a kubernetes cluster running Astronomer. It is not safe to run against a production system and does perform mutations on the system. This is designed to work running locally using Kind (kubernetes in docker).

The tests will connect into the live pods and make various assertions about them. This suite can also make calls against the kubernetes API to make assertions about the kubernetes state. Also, this suite may inspect the source code in a few situations to make static assertions, for example checking that versioning is correctly configured.

### Test fixtures

Test fixtures are in the file called [conftest.py](https://docs.pytest.org/en/stable/fixture.html#conftest-py-sharing-fixture-functions).

This is where the test fixtures go. A test fixture is any object to be made available to one or more test functions, for example a kubernetes client or a connection to a pod. These fixtures are made available to all other test files. The file name 'conftest.py' is a pytest convention for naming the test fixture file.

### Testinfra

For connections to pods, we are using the [testinfra](https://testinfra.readthedocs.io/en/latest/) pip module, which is a simple library that simplifies making assertions about remote environments. Originally designed to help test remote systems over SSH, it also now supports connecting to docker containers or kubernetes pods.

Let's consider this simple test:

```python
def test_prometheus_user(prometheus):
    user = prometheus.check_output('whoami')
    assert user == "nobody", \
        f"Expected prometheus to be running as 'nobody', not '{user}'"
```

This function name starts with "test_", a pytest convention to indicate this is a pytest function. Pytest function parameters are test fixtures. Since this test has a parameter 'prometheus', pytest will match this name to a pytest fixture of the same name, and provide it as an argument in this function. In this case, it will consume the following test fixture:

```python
@pytest.fixture(scope='session')
def prometheus(request):
    yield testinfra.get_host(f'kubectl://astronomer-prometheus-0?container=prometheus&namespace=astronomer')
```

This test fixture is making use of both 'pytest' and 'testinfra'. The `@pytest.fixture` decorator indicate to pytest that this is a fixture. testinfra is used to simplify the connection logic. We can see that the test function above makes use of the testinfra host object (the result of the get_host call that is provided by this fixture) with the `check_output` function:

This line:
```python
user = prometheus.check_output("whoami")
```

Is a simplified way of doing:
```
kubectl exec -it -n astronomer astronomer-prometheus-0 whoami
```

Long story short, testinfra allows for connections to various places (in this case kuberentes pods) and you can make assertions by executing commands there or using other function provided by the testinfra "Host" class.

### Kubernetes client

pytest fixtures can also be used to provide connections to kubernetes, for example a kubernetes client.

## What does it do?

### test_config.py

This test file makes assertions about the configuration of the platform by live-inspecting various components.

### test_versioning.py

This test file makes assertions about versioning:
  - This version should not already by published
  - Patch versions support downgrade and upgrade
  - Versioning is in a valid configuration
