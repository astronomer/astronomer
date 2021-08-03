# Chart Tests

## Summer 2021 chart test changes

Astronomer is moving from using the `helm-unittest` software to using a `pytest` setup for testing our helm chart. This mirrors the Airflow community's effort in chart testing. There are many good reasons reasons for choosing `pytest` over the more helm-specific `helm-unittest` software:

- pytest skills are something you can learn and take with you pretty much anywhere.
- pytest skills are something engineers can bring to the table without having any inside knowledge of Astronomer, Airflow, kubernetes or helm.
- pytest is extensively documented, has many useful plugins, and is debuggable though all the normal python testing tools.

## Writing chart tests

### Filtering the fire hose

When testing helm, it's easy to run into a firehose of data. To help filter out things that are not needed, we can run `helm template` with the `--show-only` flag, which will render only the given template.

For example:
```sh
helm template . --set global.baseDomain=example.com --kube-version=1.18.0 --show-only charts/astronomer/templates/ingress.yaml
```

*N.B.: If you see the error `Error: unknown flag: --kube-version` you need to upgrade your helm client to >=3.6.0*

The above command will render the full chart for kubernetes version 1.18.0, but give us only the output of that one template. The output would be something like:

```yaml
kind: Ingress
apiVersion: networking.k8s.io/v1beta1
metadata:
  name: RELEASE-NAME-public-ingress
  labels:
    component: public-ingress
    tier: astronomer
    release: RELEASE-NAME
    chart: "astronomer-0.25.2"
    heritage: Helm
  annotations:
    kubernetes.io/ingress.class: "RELEASE-NAME-nginx"
    kubernetes.io/tls-acme: "false"
    nginx.ingress.kubernetes.io/custom-http-errors: "404"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      if ($host = 'example.com' ) {
        rewrite ^ https://app.example.com$request_uri permanent;
      }
spec:
  tls:
    - secretName: astronomer-tls
      hosts:
        - example.com
        - app.example.com
        - houston.example.com
        - registry.example.com
        - install.example.com
  rules:
  - host: example.com
    http:
      paths:
        - path: /
          backend:
            serviceName: RELEASE-NAME-astro-ui
            servicePort: astro-ui-http
```

With that data, we can begin coming up with assertions to make. We will create a new python test file and put some boilerplate in.

### Starting a new pytest file

We create a new file, `tests/test_ingress_example.py`, with the following content:

```python
from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
```

The `render_chart` function does exactly what you would think, and lets us specify which version of kubernetes we want to use, and what templates we want to render so we can make assertions against them.

Let's write a simple test in the same `tests/test_ingress_example.py` file we created above, below the imports:

```python
def test_basic_ingress():
    docs = render_chart(
        show_only=["charts/astronomer/templates/ingress.yaml"],
    )
    assert len(docs) == 1
```

This very simple test will render the helm chart using the default kubernetes version, show only the templates listed in `show_only`, and assert that there should only be one yaml doc in the output.

### Running pytest tests

To run python tests, it's best to use a virtual environment. From the root of the git repository, we will create a virtual environment named `venv` and install the required files in it.

```
$ virtualenv venv -p python3
created virtual environment CPython3.9.5.final.0-64 in 299ms
  creator CPython3Posix(dest=/Users/danielh/a/astronomer/venv, clear=False, no_vcs_ignore=False, global=False)
  seeder FromAppData(download=False, pip=bundle, setuptools=bundle, wheel=bundle, via=copy, app_data_dir=/Users/danielh/Library/Application Support/virtualenv)
    added seed packages: pip==21.1.2, setuptools==57.0.0, wheel==0.36.2
  activators BashActivator,CShellActivator,FishActivator,PowerShellActivator,PythonActivator,XonshActivator
$ venv/bin/pip3 install -r requirements/chart-tests.txt
Collecting docker
  Using cached docker-5.0.0-py2.py3-none-any.whl (146 kB)
Collecting filelock
  Using cached filelock-3.0.12-py3-none-any.whl (7.6 kB)
Collecting jmespath
  Using cached jmespath-0.10.0-py2.py3-none-any.whl (24 kB)

... LOTS OF OUTPUT ...
$
```

The above setup only needs to be done once, or whenever you need to recreate your virtual environment. Now let's run our tests from the root of the repository:

```
$ venv/bin/python -m pytest -sv tests/test_ingress_example.py
Test session starts (platform: darwin, Python 3.9.5, pytest 6.2.4, pytest-sugar 0.9.4)
cachedir: .pytest_cache
rootdir: /Users/danielh/a/astronomer
plugins: sugar-0.9.4
collecting ...
 tests/test_ingress_example.py::test_basic_ingress ✓                     100% ██████████

Results (1.02s):
       1 passed
```

### Testing many versions of kubernetes

Using `pytest.parametrize` (notice it's "trize" not "terize") We can test many versions of kubernetes. Let's modify the test we created above using parametrize, and the list of kubernetes versions supported by Astronomer. To do this we add a decorator that handles the `kube_version` keyword argument, and modify our function definition to take that keyword argument, and also to pass that argument on to `render_chart`:

```python
@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_basic_ingress(kube_version):
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/astronomer/templates/ingress.yaml"],
    )
    assert len(docs) == 1
```

When we run this test, all versions found in the `supported_k8s_version` list that we imported will be tested:

```
$ venv/bin/python -m pytest -sv tests/test_ingress_example.py
Test session starts (platform: darwin, Python 3.9.5, pytest 6.2.4, pytest-sugar 0.9.4)
cachedir: .pytest_cache
rootdir: /Users/danielh/a/astronomer
plugins: sugar-0.9.4
collecting ...
 tests/test_ingress_example.py::test_basic_ingress[1.16.0] ✓     20% ██
 tests/test_ingress_example.py::test_basic_ingress[1.17.0] ✓     40% ████
 tests/test_ingress_example.py::test_basic_ingress[1.18.0] ✓     60% ██████
 tests/test_ingress_example.py::test_basic_ingress[1.19.0] ✓     80% ████████
 tests/test_ingress_example.py::test_basic_ingress[1.20.0] ✓    100% ██████████

Results (3.45s):
       5 passed
```

Let's write a new test where testing the kubernetes version would be important. In our chart, we use the Ingress v1 syntax starting with kubernetes 1.19, but v1beta1 with anything before 1.19. We will once again extend the function that we originally started, doing additional assertions depending on what version of kubernetes we are testing against. We can inspect the data produced for different versions of kubernetes by substituting `--kube-version=1.18.0` in our original command with `--kube-version=1.19.0`, allowing us to easily see what kind of assertions we can make for the various kubernetes versions. Here is the full content of our test file:

```python
from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_basic_ingress(kube_version):
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/astronomer/templates/ingress.yaml"],
    )
    assert len(docs) == 1

    major, minor, patch = [int(x) for x in kube_version.split(".")]
    if major == 1 and minor >= 19:
        assert docs[0]["apiVersion"] == "networking.k8s.io/v1"
    if major == 1 and minor < 19:
        assert docs[0]["apiVersion"] == "networking.k8s.io/v1beta1"
```

The output of this test will be exactly the same as it was before, so there's no reason to show it again, but the fact that it does not die gives us a pretty good idea that things went the way we wanted them to. If you want to make extra sure they did, keep reading.

### Inspecting tests with print

Adding print statements to view what is happening as code runs is a common debugging technique that works with pytest as long as you run pytest with `--capture=no/-s`. If we add `print(f'{kube_version=} {docs[0]["apiVersion"]=}')` to our code above each of the last two assertions and run `pytest -s`, we will see:

```
$ venv/bin/python -m pytest -s tests/test_ingress_example.py
Test session starts (platform: darwin, Python 3.9.5, pytest 6.2.4, pytest-sugar 0.9.4)
rootdir: /Users/danielh/a/astronomer
plugins: sugar-0.9.4
collecting ...
kube_version='1.16.0' docs[0]["apiVersion"]='networking.k8s.io/v1beta1'
 tests/test_ingress_example.py ✓                                               20% ██
kube_version='1.17.0' docs[0]["apiVersion"]='networking.k8s.io/v1beta1'
 tests/test_ingress_example.py ✓✓                                              40% ████
kube_version='1.18.0' docs[0]["apiVersion"]='networking.k8s.io/v1beta1'
 tests/test_ingress_example.py ✓✓✓                                             60% ██████
kube_version='1.19.0' docs[0]["apiVersion"]='networking.k8s.io/v1'
 tests/test_ingress_example.py ✓✓✓✓                                            80% ████████
kube_version='1.20.0' docs[0]["apiVersion"]='networking.k8s.io/v1'
 tests/test_ingress_example.py ✓✓✓✓✓                                          100% ██████████

Results (5.08s):
       5 passed
```

I cleaned up the output a little bit because pytest-sugar interfered with the printing.

It is important to know that these `print` statements will not show up if you do not run `pytest` with `--capture=no/-s`.

### Debugging with pdb

The python debugger `pdb` can be really useful when things don't go your way. For instance, what if helm is returning a data structure that you are unfamliar with, and are having a hard time finding the right assertion to make? pdb is a great tool to help you solve that. `pytest` interferes with the normal operation of pdb, so it offers its own `--pdb` flag to help you gain functionality back. Let's modify our tests by adding a `breakpoint()`, which will cause pdb to stop at that line in the code:

```python
@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_basic_ingress(kube_version):
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/astronomer/templates/ingress.yaml"],
    )
    breakpoint()
    assert len(docs) == 1
```

Then we run that test like so:

```
$ venv/bin/python -m pytest -s --pdb tests/test_ingress_example.py
Test session starts (platform: darwin, Python 3.9.5, pytest 6.2.4, pytest-sugar 0.9.4)
rootdir: /Users/danielh/a/astronomer
plugins: sugar-0.9.4
collecting ...
>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> PDB set_trace >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
> /Users/danielh/a/astronomer/tests/test_ingress_example.py(16)test_basic_ingress()
-> assert len(docs) == 1
(Pdb)
```

This is a standard `pdb` prompt. From here, we can see where we are in the code:

```
(Pdb) ll
  6      @pytest.mark.parametrize(
  7          "kube_version",
  8          supported_k8s_versions,
  9      )
 10      def test_basic_ingress(kube_version):
 11          docs = render_chart(
 12              kube_version=kube_version,
 13              show_only=["charts/astronomer/templates/ingress.yaml"],
 14          )
 15          breakpoint()
 16  ->        assert len(docs) == 1
 17
 18          major, minor, patch = [int(x) for x in kube_version.split(".")]
 19          if major == 1 and minor >= 19:
 20              print(f'{kube_version=} {docs[0]["apiVersion"]=}')
 21              assert docs[0]["apiVersion"] == "networking.k8s.io/v1"
 22          if major == 1 and minor < 19:
 23              print(f'{kube_version=} {docs[0]["apiVersion"]=}')
 24              assert docs[0]["apiVersion"] == "networking.k8s.io/v1beta1"
```

And we can drop into an interactive python shell to inspect things as they exist at our current point of execution:
```
(Pdb) interact
*interactive*
>>>
```

This is a normal python repl that we can type python code into:
```
>>> type(docs[0])
<class 'dict'>
>>> import pprint
>>> pp = pprint.PrettyPrinter(indent=4).pprint
>>> pp(docs[0]["spec"]["rules"][0])
{   'host': 'example.com',
    'http': {   'paths': [   {   'backend': {   'serviceName': 'RELEASE-NAME-astro-ui',
                                                'servicePort': 'astro-ui-http'},
                                 'path': '/'}]}}
>>> import yaml
>>> print(yaml.dump(docs[0]["spec"]["rules"][0]))
host: example.com
http:
  paths:
  - backend:
      serviceName: RELEASE-NAME-astro-ui
      servicePort: astro-ui-http
    path: /
```

This gives us an interactive playground for our tests where we can try out assertions, data reformatting with `jmespath.search` or comprehensions, etc..

## Where to go from here

Read the [Astronomer chart tests](https://github.com/astronomer/astronomer/tree/master/tests) and the [Airflow chart tests](https://github.com/apache/airflow/tree/master/chart/tests) for more examples of how to write chart tests.

[Pytest](https://docs.pytest.org) is an incredibly powerful test suite with a huge community of users and developers, and well worth exploring. There is a great book called [Python Testing with pytest](https://pragprog.com/titles/bopytest/python-testing-with-pytest/) by Brian Okken at [Python Bytes](https://pythonbytes.fm).

[PDB](https://docs.python.org/3/library/pdb.html) is powerful so if you're unfamiliar with it then that is definitely a great avenue to explore.

Here is an [example of porting helm-unittest to pytest](https://github.com/astronomer/astronomer/commit/cd1719da0488a28cf7da185c3b5cf10ed781ffa1). Be sure to expand the deleted file to see the helm-unittest code.
