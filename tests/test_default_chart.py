from tests.helm_template_generator import render_chart
import pytest


@pytest.mark.xfail(reason="Validator fails empty ['livenessProbe']['periodSeconds']")
def test_basic_ingress():
    docs = render_chart()
    assert len(docs) == 1
