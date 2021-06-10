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


@pytest.fixture(autouse=True, scope="session")
def upgrade_helm(tmp_path_factory, worker_id="main"):
    """
    Upgrade Helm repo
    """

    def _upgrade_helm():
        subprocess.check_output(
            [
                "helm",
                "repo",
                "add",
                "stable",
                "--force-update",
                "https://charts.helm.sh/stable/",
            ]
        )
        # subprocess.check_output(["helm", "dep", "update", sys.path[0]])

    if worker_id == "main":
        # not executing in with multiple workers, just update
        _upgrade_helm()
        return

    tmp_path_root = tmp_path_factory.getbasetemp().parent
    lock_file = tmp_path_root / "upgrade_helm.lock"
    done_file = tmp_path_root / "upgrade_helm.done"

    with FileLock(str(lock_file)):
        if not done_file.is_file():
            _upgrade_helm()
            done_file.touch()
