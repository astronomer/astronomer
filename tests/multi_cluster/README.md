# Multi-scenario testing for Astronomer "Software" 1.0

Astronomer "Software" version 1.0 introduces an optional separation of the control plane out from the data plane, allowing an app that was previously expected to run inside of a single cluster to run in N clusters, where there is 1 Control Plane and >=1 Data Planes. These two planes may be colocated inside of the same cluster. This presents us with three installation helm scenarios:

- Unified: both control and data plane exist in the same cluster
- Control: install only the control plane components into the cluster
- Data: install only the data plane components into the cluster

Our old functional tests were not meant to test this variety of installation scenarios, therefore this `multi_cluster` test directory was created with a new functional test framework that can be used to test these three scenarios.

## Things to know about this test setup

- All downloaded tools are stored in `~/.local/share/astronomer-software/bin`
- All generated kind configs are stored in `~/.local/share/astronomer-software/kubeconfig`
- All generated certificates are stored in `~/.local/share/astronomer-software/certs`
- There is one directory per test scenario: `tests/multi_cluster/unified`, `tests/multi_cluster/control`, `tests/multi_cluster/data`
- Common functions are stored in `tests/utils`
- Common configurations and fixtuers are in `tests/multi_cluster/conftest.py`
- Per-scenario configs and fixtures are in `tests/multi_cluster/<scenario/conftest.py`
