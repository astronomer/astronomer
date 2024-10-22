from tests.chart_tests.helm_template_generator import render_chart
from tests import get_containers_by_name
import pytest


class TestNginx:
    def test_nginx_service_basics(self):
        docs = render_chart(
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "Service"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-nginx"
        assert "loadBalancerIP" not in doc["spec"]
        assert "loadBalancerSourceRanges" not in doc["spec"]

    @pytest.mark.parametrize(
        "service_type,external_traffic_policy,preserve_source_ip",
        [
            ("ClusterIP", None, False),
            ("NodePort", "Cluster", False),
            ("LoadBalancer", "Cluster", False),
            ("ExternalName", "Cluster", False),
            ("ClusterIP", None, True),
            ("NodePort", "Local", True),
            ("LoadBalancer", "Local", True),
            ("ExternalName", "Local", True),
        ],
    )
    def test_nginx_service_servicetype(self, service_type, external_traffic_policy, preserve_source_ip):
        """Verify that ClusterIP never has an externalTrafficPolicy, and other
        configurations are correct according to spec.

        More details and links about this behavior linked in PR
        https://github.com/astronomer/astronomer/pull/1726
        """
        values = {
            "nginx": {
                "serviceType": service_type,
                "preserveSourceIP": preserve_source_ip,
            }
        }
        doc = render_chart(
            values=values,
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]
        assert doc["spec"]["type"] == service_type
        assert doc["spec"].get("externalTrafficPolicy") == external_traffic_policy

    def test_nginx_with_ingress_annotations(self):
        """Deployment should contain the given ingress annotations when they
        are specified."""
        doc = render_chart(
            values={"nginx": {"ingressAnnotations": {"foo1": "foo", "foo2": "foo", "foo3": "foo"}}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]

        expected_annotations = {"foo1": "foo", "foo2": "foo", "foo3": "foo"}
        assert all(doc["metadata"]["annotations"][x] == y for x, y in expected_annotations.items())

    def test_nginx_type_loadbalancer(self):
        """Deployment works with type LoadBalancer and some LB
        customizations."""
        doc = render_chart(
            values={
                "nginx": {
                    "serviceType": "LoadBalancer",
                    "loadBalancerIP": "5.5.5.5",
                    "loadBalancerSourceRanges": [
                        "1.1.1.1/32",
                        "2.2.2.2/32",
                        "3.3.3.3/32",
                    ],
                }
            },
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]

        assert doc["spec"]["type"] == "LoadBalancer"
        assert doc["spec"]["loadBalancerIP"] == "5.5.5.5"
        assert doc["spec"]["loadBalancerSourceRanges"] == [
            "1.1.1.1/32",
            "2.2.2.2/32",
            "3.3.3.3/32",
        ]

    def test_nginx_type_clusterip(self):
        doc = render_chart(
            values={"nginx": {"serviceType": "ClusterIP"}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]

        assert doc["spec"]["type"] == "ClusterIP"

    def test_nginx_type_nodeport(self):  # sourcery skip: class-extract-method
        docs = render_chart(
            values={"nginx": {"serviceType": "NodePort"}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["type"] == "NodePort"

    def test_nginx_type_loadbalancer_omits_nodeports(self):
        httpNodePort, httpsNodePort, metricsNodePort = [30401, 30402, 30403]
        doc = render_chart(
            values={
                "nginx": {
                    "serviceType": "LoadBalancer",
                    "httpNodePort": httpNodePort,
                    "httpsNodePort": httpsNodePort,
                    "metricsNodePort": metricsNodePort,
                }
            },
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]

        ports = doc["spec"]["ports"]
        assert not [x for x in ports if "nodePort" in x]

    def test_nginx_type_nodeport_doesnt_require_nodeports(self):
        doc = render_chart(
            values={
                "nginx": {
                    "serviceType": "NodePort",
                    "httpsNodePort": None,
                }
            },
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]

        assert doc["spec"]["type"] == "NodePort"

    def test_nginx_type_nodeport_specifying_nodeports(self):
        httpNodePort, httpsNodePort = [30401, 30402]
        doc = render_chart(
            values={
                "nginx": {
                    "serviceType": "NodePort",
                    "httpNodePort": httpNodePort,
                    "httpsNodePort": httpsNodePort,
                }
            },
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]

        ports = doc["spec"]["ports"]
        ports_by_name = {x["name"]: x["nodePort"] for x in ports}
        assert ports_by_name["http"] == httpNodePort
        assert ports_by_name["https"] == httpsNodePort

    def test_nginx_enabled_externalips(self):
        doc = render_chart(
            values={"nginx": {"externalIPs": "1.2.3.4"}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]

        assert len(doc["spec"]["externalIPs"]) > 0
        assert "1.2.3.4" in doc["spec"]["externalIPs"]

    def test_nginx_metrics_service_type(self):
        doc = render_chart(
            show_only=["charts/nginx/templates/nginx-metrics-service.yaml"],
        )[0]
        assert doc["spec"]["type"] == "ClusterIP"
        assert doc["spec"]["ports"][0]["port"] == 10254

    def test_nginx_externalTrafficPolicy_defaults(self):
        doc = render_chart(
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]
        assert "Cluster" == doc["spec"]["externalTrafficPolicy"]

    def test_nginx_externalTrafficPolicy_overrides(self):
        doc = render_chart(
            values={"nginx": {"preserveSourceIP": True}},
            show_only=["charts/nginx/templates/nginx-service.yaml"],
        )[0]
        assert "Local" == doc["spec"]["externalTrafficPolicy"]

    def test_nginx_allowSnippetAnnotations_defaults(self):
        doc = render_chart(
            show_only=["charts/nginx/templates/nginx-configmap.yaml"],
        )[0]
        assert doc["data"]["allow-snippet-annotations"] == "true"

    def test_nginx_enableAnnotationValidations_overrides(self):
        doc = render_chart(
            values={"nginx": {"enableAnnotationValidations": True}},
            show_only=["charts/nginx/templates/nginx-deployment.yaml"],
        )[0]
        annotationValidation = "--enable-annotation-validation=true"
        assert annotationValidation in doc["spec"]["template"]["spec"]["containers"][0]["args"]

    def test_nginx_backend_serviceaccount_defaults(self):
        """Test nginx ingress deployment service account defaults."""
        doc = render_chart(
            values={},
            show_only=["charts/nginx/templates/nginx-default-backend-serviceaccount.yaml"],
        )[0]

        assert "release-name-nginx-default-backend" == doc["metadata"]["name"]

    def test_nginx_defaults(self):
        """Test nginx ingress deployment template defaults."""
        doc = render_chart(
            values={},
            show_only=["charts/nginx/templates/nginx-deployment.yaml"],
        )[0]
        expected_security_context = {
            "runAsUser": 101,
            "runAsNonRoot": True,
            "capabilities": {"drop": ["ALL"]},
            "allowPrivilegeEscalation": False,
        }

        electionTTL = "--election-ttl"
        electionId = "--election-id=ingress-controller-leader-release-name-nginx"
        topologyAwareRouting = "--enable-topology-aware-routing"
        annotationValidation = "--enable-annotation-validation"
        disableLeaderElection = "--disable-leader-election"

        c_by_name = get_containers_by_name(doc)
        assert doc["spec"]["minReadySeconds"] == 0
        assert electionId in c_by_name["nginx"]["args"]
        assert electionTTL not in c_by_name["nginx"]["args"]
        assert topologyAwareRouting not in c_by_name["nginx"]["args"]
        assert annotationValidation not in c_by_name["nginx"]["args"]
        assert disableLeaderElection not in c_by_name["nginx"]["args"]
        assert expected_security_context == c_by_name["nginx"]["securityContext"]

    def test_nginx_min_ready_seconds_overrides(self):
        """Test nginx ingress deployment template with min ready seconds overrides."""
        minReadySeconds = 300
        doc = render_chart(
            values={"nginx": {"minReadySeconds": minReadySeconds}},
            show_only=["charts/nginx/templates/nginx-deployment.yaml"],
        )[0]

        assert doc["spec"]["minReadySeconds"] == minReadySeconds

    def test_nginx_election_ttl_overrides(self):
        """Test nginx ingress deployment template with election ttl overrides."""
        doc = render_chart(
            values={"nginx": {"electionTTL": "30s"}},
            show_only=["charts/nginx/templates/nginx-deployment.yaml"],
        )[0]
        electionTTL = "--election-ttl=30s"
        c_by_name = get_containers_by_name(doc)
        assert electionTTL in c_by_name["nginx"]["args"]

    def test_nginx_topology_aware_routing_overrides(self):
        """Test nginx ingress deployment template with topology aware routing overrides."""
        doc = render_chart(
            values={"nginx": {"enableTopologyAwareRouting": True}},
            show_only=["charts/nginx/templates/nginx-deployment.yaml"],
        )[0]
        topologyAwareRouting = "--enable-topology-aware-routing=true"
        c_by_name = get_containers_by_name(doc)
        assert topologyAwareRouting in c_by_name["nginx"]["args"]

    def test_nginx_disable_leader_election_overrides(self):
        """Test nginx ingress deployment template with leader election overrides."""
        doc = render_chart(
            values={"nginx": {"disableLeaderElection": True}},
            show_only=["charts/nginx/templates/nginx-deployment.yaml"],
        )[0]
        c_by_name = get_containers_by_name(doc)
        disableLeaderElection = "--disable-leader-election=true"
        assert disableLeaderElection in c_by_name["nginx"]["args"]

    def test_nginx_security_context_overrides(self):
        """Test nginx ingress deployment template with security context overrides."""

        values = {
            "nginx": {
                "securityContext": {
                    "runAsUser": 101,
                    "runAsNonRoot": True,
                    "capabilities": {
                        "drop": ["ALL"],
                        "add": ["NET_BIND_SERVICE"],
                    },
                    "allowPrivilegeEscalation": False,
                }
            }
        }

        doc = render_chart(
            values=values,
            show_only=["charts/nginx/templates/nginx-deployment.yaml"],
        )[0]
        expected_security_context = {
            "runAsUser": 101,
            "runAsNonRoot": True,
            "capabilities": {"drop": ["ALL"], "add": ["NET_BIND_SERVICE"]},
            "allowPrivilegeEscalation": False,
        }

        c_by_name = get_containers_by_name(doc)
        assert expected_security_context == c_by_name["nginx"]["securityContext"]
