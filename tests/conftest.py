# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import subprocess
import pytest
from filelock import FileLock
from . import git_root_dir
import docker


@pytest.fixture(autouse=True, scope="session")
def upgrade_helm(tmp_path_factory, worker_id):
    """
    Add stable helm repo, upgrade helm repos, and do helm dep upgrade.
    """

    def _upgrade_helm():
        try:
            subprocess.check_output(
                "helm repo add stable --force-update https://charts.helm.sh/stable/".split()
            )
            # The following command may modify any requirements.yaml with updated metadata
            subprocess.check_output(
                f"find {git_root_dir} -type f -name requirements.yaml -print -execdir helm dep update ;".split()
            )
            subprocess.check_output("helm repo update".split())
        except subprocess.CalledProcessError as e:
            print(e.output)

    if worker_id == "master":
        _upgrade_helm()
        return

    root_tmp_dir = tmp_path_factory.getbasetemp().parent
    lock_fn = root_tmp_dir / "upgrade_helm.lock"
    flag_fn = root_tmp_dir / "upgrade_helm.done"

    with FileLock(str(lock_fn)):
        if not flag_fn.is_file():
            _upgrade_helm()
            flag_fn.touch()


@pytest.fixture(scope="session")
def docker_client(request):
    """This is a text fixture for the docker client,
    should it be needed in a test
    """
    client = docker.from_env()
    yield client
    client.close()
