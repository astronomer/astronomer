# Multi-scenario testing for Astronomer "Software" 1.0

Astronomer "Software" version 1.0 introduces an optional separation of the control plane out from the data plane, allowing an app that was previously expected to run inside of a single cluster to run in N clusters, where there is 1 Control Plane and >=1 Data Planes. These two planes may be colocated inside of the same cluster. This presents us with three installation helm scenarios:

- unified: both control and data plane exist in the same cluster
- control: install only the control plane components into the cluster
- data: install only the data plane components into the cluster

When running these tests, you **MUST** `export TEST_SCENARIO` with one of the above values. (EG: `export TEST_SCENARIO=unified`)

## Things to know about this test setup

- All downloaded tools are stored in `~/.local/share/astronomer-software/bin`, which means we have one cached, consistent location to store tools with known versions that does not conflict with tools installed elsewhere in the OS.
- All generated kind configs are stored in `~/.local/share/astronomer-software/kubeconfig` which means we have one consistent location for kubeconfigs for each installation scenario that can be configured in developer tools, making it easier to debug the kind clusters used in testing.
- All generated certificates are stored in `~/.local/share/astronomer-software/certs`. These certificates are automatically recreated during test setup if they will expire within 4 weeks.
- There is one test directory per scenario: `tests/multi_cluster/unified`, `tests/multi_cluster/control`, `tests/multi_cluster/data`.
- Common functions are stored in `tests/utils`
- Common configurations and fixtuers are in `tests/multi_cluster/conftest.py`
- Per-scenario configs and fixtures are in `tests/multi_cluster/<scenario/conftest.py`
- `export DEBUG=1` will enable additional logging, `helm install --debug`, and `kubectl -v=9` output.
