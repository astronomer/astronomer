from collections.abc import Iterable

import pytest

from tests import git_root_dir
from tests.multi_cluster.conftest import (
    create_kind_cluster,
    create_namespace,
    delete_kind_cluster,
    helm_install,
    kind_load_docker_images,
    setup_common_cluster_configs,
)


@pytest.fixture(scope="session")
def cluster_name():
    return "control"


@pytest.fixture(scope="session")
def control(request) -> Iterable[str]:
    """
    Fixture for the 'control' cluster.

    :param request: Pytest request object for accessing test metadata.
    :yield: Path to the kubeconfig file for the 'control' cluster.
    """
    kubeconfig_file = create_kind_cluster("control")
    kind_load_docker_images(cluster="control")
    create_namespace(kubeconfig_file)
    setup_common_cluster_configs(kubeconfig_file)
    helm_install(
        kubeconfig=str(kubeconfig_file),
        values=[
            f"{git_root_dir}/configs/local-dev.yaml",
            f"{git_root_dir}/tests/data_files/scenario-controlplane.yaml",
        ],
    )
    yield kubeconfig_file
    delete_kind_cluster("control", kubeconfig_file)
