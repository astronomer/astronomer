import pytest
import os
import yaml

def test_astro_yaml():
  a_yaml_file = os.popen('helm template ../astronomer --set global.baseDomain=example.com --kube-version=1.18.0 --show-only charts/astronomer/templates/registry/registry-configmap.yaml').read()
  assert yaml.safe_load(a_yaml_file)

test_astro_yaml()