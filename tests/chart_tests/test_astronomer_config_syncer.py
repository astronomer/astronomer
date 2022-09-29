from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions

cron_test_data = [
    ("development-angular-system-6091", 0, 5),
    ("development-arithmetic-phases-5695", 0, 5),
    ("development-empty-aurora-8527", 0, 5),
    ("development-explosive-inclination-4552", 0, 5),
    ("development-infrared-nadir-2873", 0, 5),
    ("development-barren-telemetry-6087", 6, 6),
    ("development-geocentric-cluster-5666", 6, 6),
    ("development-mathematical-supernova-1523", 6, 6),
    ("development-cometary-terrestrial-2880", 12, 7),
    ("development-nuclear-gegenschein-1657", 12, 7),
    ("development-quasarian-telescope-4189", 12, 7),
    ("development-traditional-universe-0643", 12, 7),
    ("development-asteroidal-space-6369", 18, 8),
    ("development-blazing-horizon-1542", 18, 8),
    ("development-boreal-inclination-4658", 18, 8),
    ("development-exact-ionosphere-3963", 18, 8),
    ("development-extrasolar-meteor-4188", 18, 8),
    ("development-inhabited-dust-4345", 18, 8),
    ("development-nebular-singularity-6518", 18, 8),
    ("development-arithmetic-sky-0424", 24, 9),
    ("development-true-century-8320", 24, 9),
    ("development-angular-radian-2199", 30, 10),
    ("development-scientific-cosmonaut-1863", 30, 10),
    ("development-uninhabited-wavelength-9355", 30, 10),
    ("development-false-spacecraft-1944", 36, 11),
    ("development-mathematical-equator-2284", 36, 11),
    ("development-amateur-horizon-3115", 54, 14),
    ("development-devoid-terminator-0587", 54, 14),
    ("development-optical-asteroid-4621", 54, 14),
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerConfigSyncer:
    def test_astronomer_config_syncer_rbac_namespace_pools_disabled(self, kube_version):
        """Test that if rbacEnabled but namespacePools disabled, helm renders
        ClusterRole and ClusterRoleBinding resources for config syncer."""

        # First rbacEnabled set to true and namespacePools disabled, should create a ClusterRole and ClusterRoleBinding
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "features": {
                        "namespacePools": {"enabled": False},
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/config-syncer/config-syncer-role.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-rolebinding.yaml",
            ],
        )

        cluster_role = docs[0]

        assert cluster_role["kind"] == "ClusterRole"
        assert len(cluster_role["rules"]) > 0

        cluster_role_binding = docs[1]

        expected_role_ref = {
            "kind": "ClusterRole",
            "apiGroup": "rbac.authorization.k8s.io",
            "name": "release-name-config-syncer",
        }
        expected_subjects = [
            {
                "kind": "ServiceAccount",
                "name": "release-name-config-syncer",
                "namespace": "default",
            }
        ]
        assert cluster_role_binding["kind"] == "ClusterRoleBinding"
        assert cluster_role_binding["roleRef"] == expected_role_ref
        assert cluster_role_binding["subjects"] == expected_subjects

    def test_astronomer_config_syncer_namespace_pools_rbac(self, kube_version):
        """Test that when namespacePools is enabled, helm renders a Role and a
        RoleBinding for each namespace in the pool + release namespace."""

        # rbacEnabled and clusterRoles and namespacePools set to true, should create Roles and Rolebindings for namespace in Pool
        # and ignore the cluster role configuration
        namespaces = ["my-namespace-1", "my-namespace-2"]
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "features": {
                        "namespacePools": {
                            "enabled": True,
                            "namespaces": {"create": True, "names": namespaces},
                        },
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/config-syncer/config-syncer-role.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-rolebinding.yaml",
            ],
        )

        assert len(docs) == 6

        expected_namespaces = [*namespaces, "default"]

        # assertions on Role objects
        for i in range(0, 3):
            role = docs[i]

            assert role["kind"] == "Role"
            assert len(role["rules"]) > 0
            assert role["metadata"]["namespace"] == expected_namespaces[i]

        for i in range(3, 6):
            role_binding = docs[i]

            expected_subject = {
                "kind": "ServiceAccount",
                "name": "release-name-config-syncer",
                "namespace": "default",
            }
            expected_role = {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "release-name-config-syncer",
            }

            assert role_binding["kind"] == "RoleBinding"
            assert role_binding["metadata"]["namespace"] == expected_namespaces[i - 3]
            assert role_binding["roleRef"] == expected_role
            assert role_binding["subjects"][0] == expected_subject

    def test_astronomer_config_syncer_rbac_all_disabled(self, kube_version):
        """Test that if rbacEnabled and namespacePools are disabled, we do not
        create any RBAC resources."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": False,
                    "features": {
                        "namespacePools": {"enabled": False},
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/config-syncer/config-syncer-role.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-rolebinding.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_config_syncer_cronjob_namespace_pool_enabled(
        self, kube_version
    ):
        """Test that when namespace pool is enabled, config-syncer's container
        is configured to use namespaces from the pool."""
        namespaces = ["my-namespace-1", "my-namespace-2"]
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "features": {
                        "namespacePools": {
                            "enabled": True,
                            "namespaces": {"create": True, "names": namespaces},
                        },
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/config-syncer/config-syncer-cronjob.yaml",
            ],
        )[0]

        container = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"][
            "containers"
        ][0]

        assert "--target-namespaces" in container["args"]
        assert ",".join(namespaces) in container["args"]

    def test_astronomer_config_syncer_cronjob_namespace_pool_disabled(
        self, kube_version
    ):
        """Test that when namespacePools is disabled, config-syncer cronjob is
        configured not to target any namespace."""
        namespaces = ["my-namespace-1", "my-namespace-2"]
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "features": {
                        "namespacePools": {
                            "enabled": False,
                        },
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/config-syncer/config-syncer-cronjob.yaml",
            ],
        )[0]

        container = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"][
            "containers"
        ][0]

        assert "--target-namespaces" not in container["args"]
        assert ",".join(namespaces) not in container["args"]

    @pytest.mark.parametrize(
        "test_data", cron_test_data, ids=[x[0] for x in cron_test_data]
    )
    def test_astronomer_config_syncer_cronjob_default_schedule(
        self, test_data, kube_version
    ):
        """Test that if no schedule is provided for configSyncer, helm
        automatically generates a random one."""

        doc = render_chart(
            name=test_data[0],
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/config-syncer/config-syncer-cronjob.yaml",
            ],
        )[0]

        cron_schedule = doc["spec"]["schedule"].split(" ")
        assert int(cron_schedule[0]) == test_data[1]
        assert int(cron_schedule[1]) == test_data[2]
