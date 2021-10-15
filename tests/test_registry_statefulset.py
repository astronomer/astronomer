import tempfile

import pytest
import yaml

from tests.helm_template_generator import render_chart


def test_basic_cases():
    """Test some things that should apply to all cases."""
    docs = render_chart(
        show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
    )
    assert len(docs) == 1

    doc = docs[0]

    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-registry"
    expected_env = {
        "name": "REGISTRY_NOTIFICATIONS_ENDPOINTS_0_HEADERS",
        "valueFrom": {
            "secretKeyRef": {
                "name": "RELEASE-NAME-registry-auth-key",
                "key": "authHeaders",
            }
        },
    }
    assert expected_env in doc["spec"]["template"]["spec"]["containers"][0]["env"]
