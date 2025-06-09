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
    return "unified"


@pytest.fixture(scope="session")
def unified(request) -> Iterable[str]:
    """
    Fixture for the 'unified' cluster.

    :param request: Pytest request object for accessing test metadata.
    :yield: Path to the kubeconfig file for the 'unified' cluster.
    """
    kubeconfig_file = create_kind_cluster("unified")
    kind_load_docker_images(cluster="unified")
    create_namespace(kubeconfig_file)
    setup_common_cluster_configs(kubeconfig_file)
    helm_install(
        kubeconfig=str(kubeconfig_file),
        values=[
            f"{git_root_dir}/configs/local-dev.yaml",
            f"{git_root_dir}/tests/data_files/scenario-unified.yaml",
        ],
    )
    yield kubeconfig_file
    delete_kind_cluster("unified", kubeconfig_file)
