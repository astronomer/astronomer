from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart
import pytest

@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAirflowOperator:
    def test_airflow_operator_cert_manager(self, kube_version):
        """Test Airflow operator cert manager with flags."""
        docs = render_chart(
            kube_version=kube_version,
            values={"airflow-operator": {
                            "certManager":
                            { 
                                "enabled": True
                            },
                            },
                        "global":
                            {
                                    "airflow_operator":
                                    {
                                        "enabled": True
                                    },
                            },
                    },      
                        
            show_only=["charts/airflow-operator/templates/certmanager/selfsigned-issuer.yaml",
                    "charts/airflow-operator/templates/certmanager/serving-cert-certificate.yaml",
                    ],
        )
        assert len(docs) == 2
    
