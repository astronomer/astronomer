import pytest

from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


def test_nginx_service_basics():
    nginx_cp_service_docs = render_chart(
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
        ],
    )

    assert len(nginx_cp_service_docs) == 1
    expected_names = ["release-name-cp-nginx"]
    for doc in nginx_cp_service_docs:
        assert doc["kind"] == "Service"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] in expected_names
        assert "loadBalancerIP" not in doc["spec"]
        assert "loadBalancerSourceRanges" not in doc["spec"]

    nginx_dp_service_docs = render_chart(
        show_only=[
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
        values={"global": {"plane": {"mode": "data"}}},
    )
    assert len(nginx_dp_service_docs) == 1
    expected_names = ["release-name-dp-nginx"]
    for doc in nginx_dp_service_docs:
        assert doc["kind"] == "Service"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] in expected_names
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
def test_nginx_service_servicetype(service_type, external_traffic_policy, preserve_source_ip):
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
    docs = render_chart(
        values=values,
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        assert doc["spec"]["type"] == service_type
        assert doc["spec"].get("externalTrafficPolicy") == external_traffic_policy


def test_nginx_with_ingress_annotations():
    """Deployment should contain the given ingress annotations when they
    are specified."""
    docs = render_chart(
        values={"nginx": {"ingressAnnotations": {"foo1": "foo", "foo2": "foo", "foo3": "foo"}}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        expected_annotations = {"foo1": "foo", "foo2": "foo", "foo3": "foo"}
        assert all(doc["metadata"]["annotations"][x] == y for x, y in expected_annotations.items())


def test_nginx_type_loadbalancer():
    """Deployment works with type LoadBalancer and some LB
    customizations."""
    docs = render_chart(
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
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        assert doc["spec"]["type"] == "LoadBalancer"
        assert doc["spec"]["loadBalancerIP"] == "5.5.5.5"
        assert doc["spec"]["loadBalancerSourceRanges"] == [
            "1.1.1.1/32",
            "2.2.2.2/32",
            "3.3.3.3/32",
        ]


def test_nginx_type_clusterip():
    docs = render_chart(
        values={"nginx": {"serviceType": "ClusterIP"}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        assert doc["spec"]["type"] == "ClusterIP"


def test_nginx_type_nodeport():  # sourcery skip: class-extract-method
    docs = render_chart(
        values={"nginx": {"serviceType": "NodePort"}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
        ],
    )

    assert len(docs) == 1
    for doc in docs:
        assert doc["spec"]["type"] == "NodePort"

    docs = render_chart(
        values={"nginx": {"serviceType": "NodePort"}, "global": {"plane": {"mode": "data"}}},
        show_only=[
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )

    assert len(docs) == 1
    for doc in docs:
        assert doc["spec"]["type"] == "NodePort"


def test_nginx_type_loadbalancer_omits_nodeports():
    httpNodePort, httpsNodePort, metricsNodePort = [30401, 30402, 30403]
    docs = render_chart(
        values={
            "nginx": {
                "serviceType": "LoadBalancer",
                "httpNodePort": httpNodePort,
                "httpsNodePort": httpsNodePort,
                "metricsNodePort": metricsNodePort,
            }
        },
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        ports = doc["spec"]["ports"]
        assert not [x for x in ports if "nodePort" in x]


def test_nginx_type_nodeport_doesnt_require_nodeports():
    docs = render_chart(
        values={
            "nginx": {
                "serviceType": "NodePort",
                "httpsNodePort": None,
            }
        },
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        assert doc["spec"]["type"] == "NodePort"


def test_nginx_type_nodeport_specifying_nodeports():
    httpNodePort, httpsNodePort = [30401, 30402]
    docs = render_chart(
        values={
            "nginx": {
                "serviceType": "NodePort",
                "httpNodePort": httpNodePort,
                "httpsNodePort": httpsNodePort,
            }
        },
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        ports = doc["spec"]["ports"]
        ports_by_name = {x["name"]: x["nodePort"] for x in ports}
        assert ports_by_name["http"] == httpNodePort
        assert ports_by_name["https"] == httpsNodePort


def test_nginx_enabled_externalips():
    docs = render_chart(
        values={"nginx": {"externalIPs": "1.2.3.4"}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        assert len(doc["spec"]["externalIPs"]) > 0
        assert "1.2.3.4" in doc["spec"]["externalIPs"]


def test_nginx_metrics_service_type():
    docs = render_chart(
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-metrics-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-metrics-service.yaml",
        ],
    )
    for doc in docs:
        assert doc["spec"]["type"] == "ClusterIP"
        assert doc["spec"]["ports"][0]["port"] == 10254


def test_nginx_externalTrafficPolicy_defaults():
    docs = render_chart(
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        assert "Cluster" == doc["spec"]["externalTrafficPolicy"]


def test_nginx_externalTrafficPolicy_overrides():
    docs = render_chart(
        values={"nginx": {"preserveSourceIP": True}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-service.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-service.yaml",
        ],
    )
    for doc in docs:
        assert "Local" == doc["spec"]["externalTrafficPolicy"]


def test_nginx_allowSnippetAnnotations_defaults():
    docs = render_chart(
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-configmap.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-configmap.yaml",
        ],
    )
    for doc in docs:
        assert doc["data"]["allow-snippet-annotations"] == "true"
        assert doc["data"]["annotations-risk-level"] == "Critical"


def test_nginx_backend_serviceaccount_defaults():
    """Test nginx ingress deployment service account defaults."""
    docs = render_chart(
        show_only=["charts/nginx/templates/nginx-default-backend-serviceaccount.yaml"],
    )
    for doc in docs:
        assert "release-name-nginx-default-backend" == doc["metadata"]["name"]


@pytest.mark.parametrize("plane_mode", ["unified", "control", "data"])
def test_nginx_deployment_defaults(plane_mode):
    """Test nginx ingress deployment template defaults."""
    docs = render_chart(
        values={"global": {"plane": {"mode": plane_mode}}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-deployment.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-deployment.yaml",
        ],
    )
    expected_security_context = {
        "runAsUser": 101,
        "runAsNonRoot": True,
        "capabilities": {"drop": ["ALL"]},
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
    }

    forbidden_args = [
        "--election-ttl",
        "--enable-topology-aware-routing",
        "--enable-annotation-validation",
        "--disable-leader-election",
    ]

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "Deployment"
    names = {
        "unified": "release-name-cp-nginx",
        "control": "release-name-cp-nginx",
        "data": "release-name-dp-nginx",
    }
    assert doc["metadata"]["name"] == names[plane_mode]
    assert doc["apiVersion"] == "apps/v1"
    assert doc["spec"]["minReadySeconds"] == 0
    assert doc["spec"]["template"]["spec"]["volumes"] == [
        {"name": "tmp", "emptyDir": {}},
        {"name": "etc-ingress-controller", "emptyDir": {}},
        {"name": "etc-nginx", "emptyDir": {}},
    ]

    c_by_name = get_containers_by_name(doc, include_init_containers=True)
    assert len(c_by_name) == 2

    assert c_by_name["etc-nginx-copier"]["image"].startswith("quay.io/astronomer/ap-nginx:")
    assert c_by_name["etc-nginx-copier"]["securityContext"]["readOnlyRootFilesystem"]
    assert c_by_name["etc-nginx-copier"]["volumeMounts"] == [
        {"name": "etc-nginx", "mountPath": "/etc/nginx_copy"},
        {"name": "tmp", "mountPath": "/tmp"},
        {"name": "etc-ingress-controller", "mountPath": "/etc/ingress-controller"},
    ]

    assert c_by_name["nginx"]["image"] == c_by_name["etc-nginx-copier"]["image"]
    assert c_by_name["nginx"]["securityContext"] == c_by_name["etc-nginx-copier"]["securityContext"]
    assert c_by_name["nginx"]["securityContext"] == expected_security_context
    assert c_by_name["nginx"]["image"].startswith("quay.io/astronomer/ap-nginx:")
    assert "--election-id=ingress-controller-leader-release-name-nginx" in c_by_name["nginx"]["args"]
    assert "--enable-annotation-validation=true" in c_by_name["nginx"]["args"]
    for arg in forbidden_args:
        assert arg not in c_by_name["nginx"]["args"]
    assert c_by_name["nginx"]["volumeMounts"] == [
        {"name": "tmp", "mountPath": "/tmp"},
        {"name": "etc-ingress-controller", "mountPath": "/etc/ingress-controller"},
        {"name": "etc-nginx", "mountPath": "/etc/nginx"},
    ]


def test_nginx_min_ready_seconds_overrides():
    """Test nginx ingress deployment template with min ready seconds overrides."""
    minReadySeconds = 300
    docs = render_chart(
        values={"nginx": {"minReadySeconds": minReadySeconds}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-deployment.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-deployment.yaml",
        ],
    )
    for doc in docs:
        assert doc["spec"]["minReadySeconds"] == minReadySeconds


def test_nginx_election_ttl_overrides():
    """Test nginx ingress deployment template with election ttl overrides."""
    docs = render_chart(
        values={"nginx": {"electionTTL": "30s"}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-deployment.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-deployment.yaml",
        ],
    )
    electionTTL = "--election-ttl=30s"
    for doc in docs:
        c_by_name = get_containers_by_name(doc)
        assert electionTTL in c_by_name["nginx"]["args"]


def test_nginx_topology_aware_routing_overrides():
    """Test nginx ingress deployment template with topology aware routing overrides."""
    docs = render_chart(
        values={"nginx": {"enableTopologyAwareRouting": True}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-deployment.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-deployment.yaml",
        ],
    )
    topologyAwareRouting = "--enable-topology-aware-routing=true"
    for doc in docs:
        c_by_name = get_containers_by_name(doc)
        assert topologyAwareRouting in c_by_name["nginx"]["args"]


def test_nginx_disable_leader_election_overrides():
    """Test nginx ingress deployment template with leader election overrides."""
    docs = render_chart(
        values={"nginx": {"disableLeaderElection": True}},
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-deployment.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-deployment.yaml",
        ],
    )
    disableLeaderElection = "--disable-leader-election=true"
    for doc in docs:
        c_by_name = get_containers_by_name(doc)
        assert disableLeaderElection in c_by_name["nginx"]["args"]


def test_nginx_security_context_overrides():
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

    docs = render_chart(
        values=values,
        show_only=[
            "charts/nginx/templates/controlplane/nginx-cp-deployment.yaml",
            "charts/nginx/templates/dataplane/nginx-dp-deployment.yaml",
        ],
    )
    expected_security_context = {
        "runAsUser": 101,
        "runAsNonRoot": True,
        "capabilities": {"drop": ["ALL"], "add": ["NET_BIND_SERVICE"]},
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
    }
    for doc in docs:
        c_by_name = get_containers_by_name(doc)
        assert expected_security_context == c_by_name["nginx"]["securityContext"]


def test_nginx_default_backend_default():
    """Test nginx default backend with defaults."""
    docs = render_chart(
        show_only=[
            "charts/nginx/templates/nginx-deployment-default.yaml",
        ]
    )
    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "Deployment"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["spec"]["template"]["spec"]["volumes"] == [{"name": "tmp", "emptyDir": {}}]
    assert len(doc["spec"]["template"]["spec"]["containers"]) == 1
    container = doc["spec"]["template"]["spec"]["containers"][0]
    assert container["image"].startswith("quay.io/astronomer/ap-default-backend:")
    assert container["imagePullPolicy"] == "IfNotPresent"
    assert container["volumeMounts"] == [{"name": "tmp", "mountPath": "/tmp"}]


def test_nginx_backend_overrides():
    """Test nginx default backend disabled."""
    docs = render_chart(
        values={
            "nginx": {
                "defaultBackend": {"enabled": False},
            }
        },
        show_only=[
            "charts/nginx/templates/nginx-default-backend-networkpolicy.yaml",
            "charts/nginx/templates/nginx-default-backend-pod-disruption-budget.yaml",
            "charts/nginx/templates/nginx-default-backend-serviceaccount.yaml",
            "charts/nginx/templates/nginx-deployment-default.yaml",
            "charts/nginx/templates/nginx-service-default.yaml",
        ],
    )

    assert len(docs) == 0
