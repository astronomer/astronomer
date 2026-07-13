"""Tests for the Control Plane HA (global.controlPlaneHA) chart wiring (PINF-768).

Covers:
  * cp-identity Secret: generated on every control/unified plane install regardless of
    HA state (PINF-760), so a stable cp_id exists from initial single-CP install and is
    already available if/when HA is later enabled; data-plane installs never generate it;
    required-globalBaseDomain guard still applies only when HA is enabled.
  * JWT signing keypair generation gating (jwks.generation.enabled / HA)
  * CP_ID env var on every CP reconciliation-loop pod, still gated on HA
    (Houston API + worker, dp-link, navigator)
  * helm.globalBaseDomain / cookieDomain / cookieName in the houston configmap
"""

from subprocess import CalledProcessError

import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

JWT_SECRET_FILE = "charts/astronomer/templates/houston/api/houston-jwt-certificate-secret.yaml"
CP_IDENTITY_FILE = "charts/astronomer/templates/houston/api/cp-identity-secret.yaml"
DB_MIGRATION_JOB_FILE = "charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml"
CONFIGMAP_FILE = "charts/astronomer/templates/houston/houston-configmap.yaml"
HOUSTON_API_FILE = "charts/astronomer/templates/houston/api/houston-deployment.yaml"
HOUSTON_WORKER_FILE = "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"
DP_LINK_FILE = "charts/astronomer/templates/dp-link/dp-link-deployment.yaml"
NAVIGATOR_FILE = "charts/astronomer/templates/navigator/navigator-deployment.yaml"

EXPECTED_CP_ID_ENV = {"secretKeyRef": {"name": "cp-identity", "key": "cp_id"}}


def _ha_values(**overrides):
    """global.controlPlaneHA enabled with a valid globalBaseDomain, control plane."""
    cpha = {"enabled": True, "globalBaseDomain": "astro.example.com"}
    cpha.update(overrides)
    return {"global": {"plane": {"mode": "control"}, "controlPlaneHA": cpha}}


def _any_container_has_cp_id(doc):
    """True if any container or initContainer in the pod has the CP_ID env wired to cp-identity."""
    for container in get_containers_by_name(doc, include_init_containers=True).values():
        env = get_env_vars_dict(container.get("env", []))
        if env.get("CP_ID") == EXPECTED_CP_ID_ENV:
            return True
    return False


def _no_container_has_cp_id(doc):
    for container in get_containers_by_name(doc, include_init_containers=True).values():
        if "CP_ID" in get_env_vars_dict(container.get("env", [])):
            return False
    return True


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestCpIdentitySecret:
    @pytest.mark.parametrize("mode", ["control", "unified"])
    def test_generated_when_ha_disabled(self, kube_version, mode):
        """cp-identity Secret is generated on control/unified installs even with HA off (PINF-760).

        This is the core behavior change: a stable cp_id must exist from the initial
        single-CP install so it's already available if/when the customer later enables HA,
        rather than being minted for the first time at the HA-enable flip.
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE],
            values={"global": {"plane": {"mode": mode}, "controlPlaneHA": {"enabled": False}}},
        )
        assert len(docs) == 1
        secret = docs[0]
        assert secret["kind"] == "Secret"
        assert secret["metadata"]["name"] == "cp-identity"
        assert secret["data"]["cp_id"]  # non-empty (uuid, base64-encoded)

    def test_absent_on_data_plane_when_ha_disabled(self, kube_version):
        """Data-plane installs never generate cp-identity; the plane-mode gate still applies."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE],
            values={"global": {"plane": {"mode": "data"}, "controlPlaneHA": {"enabled": False}}},
        )
        assert docs == []

    def test_generated_when_ha_enabled(self, kube_version):
        """cp-identity Secret rendered with a base64 cp_id in HA mode (existing behavior preserved)."""
        docs = render_chart(kube_version=kube_version, show_only=[CP_IDENTITY_FILE], values=_ha_values())
        assert len(docs) == 1
        secret = docs[0]
        assert secret["kind"] == "Secret"
        assert secret["metadata"]["name"] == "cp-identity"
        assert secret["data"]["cp_id"]  # non-empty (uuid, base64-encoded)

    def test_explicit_cp_id_is_used(self, kube_version):
        """An explicit global.controlPlaneHA.cpId is used verbatim (deterministic for GitOps/offline render)."""
        import base64

        docs = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE],
            values=_ha_values(cpId="11111111-2222-3333-4444-555555555555"),
        )
        assert len(docs) == 1
        assert base64.b64decode(docs[0]["data"]["cp_id"]).decode() == "11111111-2222-3333-4444-555555555555"

    def test_requires_global_base_domain(self, kube_version):
        """Enabling HA without globalBaseDomain fails the render with a clear message."""
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(
                kube_version=kube_version,
                show_only=[CP_IDENTITY_FILE],
                values={"global": {"plane": {"mode": "control"}, "controlPlaneHA": {"enabled": True}}},
            )
        assert "global.controlPlaneHA.globalBaseDomain is required" in excinfo.value.stderr.decode("utf-8")

    def test_hook_annotations(self, kube_version):
        """cp-identity is a pre-install/pre-upgrade hook so it exists before the hook jobs that mount CP_ID (PINF-934).

        resource-policy keep protects the hook-created Secret from the main-phase prune on the
        release that converts it from a regular resource, and preserves cp_id across HA toggles.
        """
        docs = render_chart(kube_version=kube_version, show_only=[CP_IDENTITY_FILE], values=_ha_values())
        annotations = docs[0]["metadata"]["annotations"]
        assert annotations["helm.sh/hook"] == "pre-install,pre-upgrade"
        assert annotations["helm.sh/hook-weight"] == "-1"
        assert annotations["helm.sh/hook-delete-policy"] == "before-hook-creation"
        assert annotations["helm.sh/resource-policy"] == "keep"

    def test_hook_runs_before_db_migration_hook_job(self, kube_version):
        """Regression for the HA-enable upgrade deadlock (PINF-934).

        The db-migration job runs as a pre-upgrade hook and mounts CP_ID from cp-identity,
        so the Secret hook must run in the same phase with a strictly lower weight.
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE, DB_MIGRATION_JOB_FILE],
            values=_ha_values(),
        )
        by_kind = {doc["kind"]: doc for doc in docs}
        secret_annotations = by_kind["Secret"]["metadata"]["annotations"]
        job_annotations = by_kind["Job"]["metadata"]["annotations"]
        assert "pre-upgrade" in job_annotations["helm.sh/hook"]
        assert "pre-upgrade" in secret_annotations["helm.sh/hook"]
        assert int(secret_annotations["helm.sh/hook-weight"]) < int(job_annotations["helm.sh/hook-weight"])

    def test_data_plane_render_not_gated_on_global_base_domain(self, kube_version):
        """A data-plane render with HA enabled (e.g. shared values) must not require globalBaseDomain.

        globalBaseDomain is control-plane-only, so the fail guard is scoped to control/unified;
        the data plane renders cleanly and emits no cp-identity Secret.
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE],
            values={"global": {"plane": {"mode": "data"}, "controlPlaneHA": {"enabled": True}}},
        )
        assert docs == []

    def test_cp_id_survives_ha_disable_then_reenable(self, kube_version):
        """cp_id minted at single-CP install time is preserved across an HA disable/re-enable toggle.

        `helm template` has no cluster to run `lookup` against (it always sees an empty
        cluster), so the `lookup`-finds-the-existing-Secret branch can't be exercised directly
        in this render-only test harness. This instead pins the cp_id captured from the initial
        HA-off render via the explicit `global.controlPlaneHA.cpId` override for the later
        renders — the same value the chart would read back from the real cp-identity Secret
        (protected by `helm.sh/resource-policy: keep`) during an actual `helm upgrade` toggle.
        """
        import base64

        # Single-CP install: cp-identity is generated for the first time (HA off).
        initial = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE],
            values={"global": {"plane": {"mode": "control"}, "controlPlaneHA": {"enabled": False}}},
        )
        assert len(initial) == 1
        cp_id = base64.b64decode(initial[0]["data"]["cp_id"]).decode()

        # HA-enable: on a real cluster `lookup` would find the Secret above and reuse cp_id.
        enabled = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE],
            values=_ha_values(cpId=cp_id),
        )
        assert base64.b64decode(enabled[0]["data"]["cp_id"]).decode() == cp_id

        # HA-disable again: the same cp_id remains in place for a future re-enable.
        disabled_again = render_chart(
            kube_version=kube_version,
            show_only=[CP_IDENTITY_FILE],
            values={
                "global": {
                    "plane": {"mode": "control"},
                    "controlPlaneHA": {"enabled": False, "cpId": cp_id},
                }
            },
        )
        assert base64.b64decode(disabled_again[0]["data"]["cp_id"]).decode() == cp_id


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestJwtKeypairGating:
    def test_generated_by_default(self, kube_version):
        """JWT signing key + certificate secrets generated on a default install."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[JWT_SECRET_FILE],
            values={"global": {"plane": {"mode": "control"}}},
        )
        assert len(docs) == 2

    def test_skipped_when_ha_enabled(self, kube_version):
        """HA mode skips chart-generated JWT keypair (shared material is provided externally)."""
        docs = render_chart(kube_version=kube_version, show_only=[JWT_SECRET_FILE], values=_ha_values())
        assert docs == []

    def test_skipped_when_generation_disabled(self, kube_version):
        """jwks.generation.enabled=false skips keypair generation independently of HA."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[JWT_SECRET_FILE],
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"houston": {"jwks": {"generation": {"enabled": False}}}},
            },
        )
        assert docs == []

    def test_generated_when_ha_with_bootstrap(self, kube_version):
        """bootstrapJwks=true overrides the HA-mode block (fresh HA first-CP bootstrap)."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[JWT_SECRET_FILE],
            values=_ha_values(bootstrapJwks=True),
        )
        assert len(docs) == 2

    def test_bootstrap_skipped_when_generation_disabled(self, kube_version):
        """jwks.generation.enabled=false wins over bootstrapJwks (explicit disable)."""
        values = _ha_values(bootstrapJwks=True)
        values["astronomer"] = {"houston": {"jwks": {"generation": {"enabled": False}}}}
        docs = render_chart(kube_version=kube_version, show_only=[JWT_SECRET_FILE], values=values)
        assert docs == []


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize(
    "component_file,extra_values",
    [
        (HOUSTON_API_FILE, {}),
        (HOUSTON_WORKER_FILE, {"astronomer": {"houston": {"worker": {"enabled": True}}}}),
        (DP_LINK_FILE, {"astronomer": {"dpLink": {"enabled": True}}}),
        (NAVIGATOR_FILE, {"astronomer": {"navigator": {"enabled": True}}}),
    ],
)
class TestCpIdEnvVar:
    @staticmethod
    def _merge(base, extra):
        merged = {**base}
        for key, value in extra.items():
            if key in merged and isinstance(merged[key], dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    def test_cp_id_present_in_ha_mode(self, kube_version, component_file, extra_values):
        """CP_ID (from cp-identity) is mounted on every CP reconciliation-loop pod in HA mode."""
        values = self._merge(_ha_values(), extra_values)
        docs = render_chart(kube_version=kube_version, show_only=[component_file], values=values)
        assert len(docs) == 1
        assert _any_container_has_cp_id(docs[0])

    def test_cp_id_absent_when_ha_disabled(self, kube_version, component_file, extra_values):
        """No CP_ID env on any component when HA is off (no behavior change)."""
        values = self._merge({"global": {"plane": {"mode": "control"}}}, extra_values)
        docs = render_chart(kube_version=kube_version, show_only=[component_file], values=values)
        assert len(docs) == 1
        assert _no_container_has_cp_id(docs[0])


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestHoustonConfigHelmValues:
    @staticmethod
    def production_yaml_prod_helm(docs):
        assert len(docs) == 1
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        return prod["helm"]

    def test_no_ha_values_when_disabled(self, kube_version):
        """HA-off configmap keeps baseDomain only — no global domain / cookie keys."""
        helm = self.production_yaml_prod_helm(
            render_chart(
                kube_version=kube_version,
                show_only=[CONFIGMAP_FILE],
                values={"global": {"plane": {"mode": "control"}, "baseDomain": "example.com"}},
            )
        )
        assert "controlPlaneHA" not in helm
        assert "globalBaseDomain" not in helm
        assert "cookieDomain" not in helm
        assert "cookieName" not in helm

    def test_global_base_domain_emitted_in_ha(self, kube_version):
        """HA-on configmap emits the HA-enabled signal + globalBaseDomain; cookie keys omitted unless overridden."""
        values = _ha_values()
        values["global"]["baseDomain"] = "example.com"
        helm = self.production_yaml_prod_helm(render_chart(kube_version=kube_version, show_only=[CONFIGMAP_FILE], values=values))
        assert helm["controlPlaneHA"]["enabled"] is True
        assert helm["globalBaseDomain"] == "astro.example.com"
        assert "cookieDomain" not in helm
        assert "cookieName" not in helm

    def test_cookie_overrides_emitted_when_set(self, kube_version):
        """cookieDomain / cookieName pass through only when explicitly set."""
        values = _ha_values(cookieDomain=".example.com", cookieName="astronomer_custom_auth")
        values["global"]["baseDomain"] = "example.com"
        helm = self.production_yaml_prod_helm(render_chart(kube_version=kube_version, show_only=[CONFIGMAP_FILE], values=values))
        assert helm["cookieDomain"] == ".example.com"
        assert helm["cookieName"] == "astronomer_custom_auth"
