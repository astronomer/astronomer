"""Tests for bin/adopt-bootstrap-secrets-pre-upgrade.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = REPO_ROOT / "bin" / "adopt-bootstrap-secrets-pre-upgrade.py"
_spec = importlib.util.spec_from_file_location("adopt_bootstrap_secrets_pre_upgrade", _SCRIPT_PATH)
adopt_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = adopt_mod
_spec.loader.exec_module(adopt_mod)


def _secret(labels=None, annotations=None, name="astronomer-flightdeck-backend"):
    return {"metadata": {"name": name, "labels": labels or {}, "annotations": annotations or {}}}


def _owned_by(release, namespace):
    return _secret(
        labels={adopt_mod.MANAGED_BY_LABEL: "Helm"},
        annotations={
            adopt_mod.RELEASE_NAME_ANNOTATION: release,
            adopt_mod.RELEASE_NAMESPACE_ANNOTATION: namespace,
        },
    )


# ---- needs_adoption (pure logic) ----------------------------------------


def test_needs_adoption_true_for_unmanaged():
    assert adopt_mod.needs_adoption(_secret(), "astronomer", "astronomer") is True


def test_needs_adoption_false_when_already_ours():
    secret = _owned_by("astronomer", "astronomer")
    assert adopt_mod.needs_adoption(secret, "astronomer", "astronomer") is False


def test_needs_adoption_raises_for_other_release():
    secret = _owned_by("other-release", "astronomer")
    with pytest.raises(RuntimeError, match="different release"):
        adopt_mod.needs_adoption(secret, "astronomer", "astronomer")


def test_needs_adoption_raises_for_other_namespace():
    secret = _owned_by("astronomer", "other-ns")
    with pytest.raises(RuntimeError, match="different release"):
        adopt_mod.needs_adoption(secret, "astronomer", "astronomer")


def test_needs_adoption_raises_on_partial_foreign_metadata():
    # Annotation present but managed-by label missing -> still someone else's, do not clobber.
    secret = _secret(annotations={adopt_mod.RELEASE_NAME_ANNOTATION: "someone"})
    with pytest.raises(RuntimeError, match="different release"):
        adopt_mod.needs_adoption(secret, "astronomer", "astronomer")


# ---- kubectl_base -------------------------------------------------------


def test_kubectl_base_without_context():
    assert adopt_mod.kubectl_base("kubectl", "astronomer", None) == [
        "kubectl",
        "--namespace",
        "astronomer",
    ]


def test_kubectl_base_with_context():
    assert adopt_mod.kubectl_base("/bin/kubectl", "ns", "kind-x") == [
        "/bin/kubectl",
        "--namespace",
        "ns",
        "--context",
        "kind-x",
    ]


# ---- main (I/O faked via module-level run) ------------------------------


class FakeKubectl:
    """Records label/annotate calls and serves canned `get secret` results."""

    def __init__(self, secrets: dict[str, dict | None]):
        self.secrets = secrets
        self.mutations: list[list[str]] = []

    def __call__(self, cmd, *, check=True):
        verb = cmd[cmd.index("secret") - 1] if "secret" in cmd else cmd[-1]
        name = cmd[cmd.index("secret") + 1]
        if verb == "get":
            obj = self.secrets.get(name, "missing")
            if obj == "missing":
                return subprocess.CompletedProcess(cmd, 1, "", f'secrets "{name}" not found')
            return subprocess.CompletedProcess(cmd, 0, json.dumps(obj), "")
        # label / annotate
        self.mutations.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _run_main(monkeypatch, secrets, argv):
    fake = FakeKubectl(secrets)
    monkeypatch.setattr(adopt_mod, "run", fake)
    rc = adopt_mod.main(argv)
    return rc, fake


def test_main_skips_when_secret_absent(monkeypatch, capsys):
    rc, fake = _run_main(monkeypatch, {}, ["--release-name", "astronomer", "--namespace", "astronomer"])
    assert rc == 0
    assert fake.mutations == []
    assert "not found" in capsys.readouterr().out


def test_main_adopts_unmanaged_secret(monkeypatch, capsys):
    secrets = {"astronomer-flightdeck-backend": _secret()}
    rc, fake = _run_main(monkeypatch, secrets, ["--release-name", "astronomer", "--namespace", "astronomer"])
    assert rc == 0
    verbs = [c[c.index("secret") - 1] for c in fake.mutations]
    assert verbs == ["label", "annotate"]
    label_cmd = fake.mutations[0]
    assert f"{adopt_mod.MANAGED_BY_LABEL}=Helm" in label_cmd
    annotate_cmd = fake.mutations[1]
    assert f"{adopt_mod.RELEASE_NAME_ANNOTATION}=astronomer" in annotate_cmd
    assert f"{adopt_mod.RELEASE_NAMESPACE_ANNOTATION}=astronomer" in annotate_cmd


def test_main_idempotent_when_already_owned(monkeypatch):
    secrets = {"astronomer-flightdeck-backend": _owned_by("astronomer", "astronomer")}
    rc, fake = _run_main(monkeypatch, secrets, [])
    assert rc == 0
    assert fake.mutations == []


def test_main_dry_run_mutates_nothing(monkeypatch, capsys):
    secrets = {"astronomer-flightdeck-backend": _secret()}
    rc, fake = _run_main(monkeypatch, secrets, ["--dry-run"])
    assert rc == 0
    assert fake.mutations == []
    assert "[dry-run]" in capsys.readouterr().out


def test_main_errors_on_cross_release_conflict(monkeypatch, capsys):
    secrets = {"astronomer-flightdeck-backend": _owned_by("other", "astronomer")}
    rc, fake = _run_main(monkeypatch, secrets, [])
    assert rc == 1
    assert fake.mutations == []
    assert "different release" in capsys.readouterr().err


def test_main_custom_secret_names(monkeypatch):
    secrets = {"rel-flightdeck-backend": _secret(name="rel-flightdeck-backend")}
    rc, fake = _run_main(monkeypatch, secrets, ["--secret", "rel-flightdeck-backend"])
    assert rc == 0
    assert fake.mutations[0][fake.mutations[0].index("secret") + 1] == "rel-flightdeck-backend"
