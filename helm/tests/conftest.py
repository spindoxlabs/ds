"""Shared harness for the render tests, run locally with ``task helm:test``.

No cluster, no CI: ``helm lint`` and ``helmfile template``, parsed as YAML, with
assertions over the objects. The whole ``helm/`` tree is copied to a temporary
directory first, because ``helm dependency update`` writes into it.

Two ways in:

* ``_render`` — ds's own ``example`` environment, from the committed
  ``secrets.example.yaml``;
* ``render_pilot`` — **a deployment's own helmfile** in a directory outside
  ``helm/``, taking ds's helmfile as a sub-helmfile and passing its values and
  secrets down (secrets plan M1). The values are ``tests/pilot/values.yaml``: an
  anchor and two participants shaped like a real deployment (a community that
  both provides and consumes, a grid operator that provides), non-default
  namespaces, an external Keycloak realm. Its secrets are generated per test
  session, so nothing secret-looking is committed and no placeholder is in them.
"""

from __future__ import annotations

import copy
import json
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Any
from collections.abc import Callable

import pytest
import yaml

HELM_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = HELM_DIR.parent
PILOT_VALUES = Path(__file__).resolve().parent / "pilot" / "values.yaml"
CHARTS = sorted(
    p.name for p in (HELM_DIR / "charts").iterdir() if (p / "Chart.yaml").is_file()
)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def _objects(manifest: str) -> list[dict]:
    return [
        doc
        for doc in yaml.safe_load_all(manifest)
        if isinstance(doc, dict) and doc.get("kind")
    ]


def _key(obj: dict) -> tuple[str, str, str]:
    meta = obj.get("metadata") or {}
    return (obj["kind"], meta.get("namespace") or "", meta["name"])


@pytest.fixture(scope="session")
def helm_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dest = tmp_path_factory.mktemp("render") / "helm"
    patterns = shutil.ignore_patterns(
        "Chart.lock", "__pycache__", ".pytest_cache", "secrets.sops.yaml", ".certs"
    )

    def ignore(directory: str, names: list[str]) -> set[str]:
        # This directory, not every `tests/`: the charts' `templates/tests/`
        # hold the `helm test` Pods.
        skipped = set(patterns(directory, names))
        if Path(directory) == HELM_DIR:
            skipped.add("tests")
        return skipped

    shutil.copytree(HELM_DIR, dest, ignore=ignore)
    for chart in CHARTS:
        vendored = dest / "charts" / chart / "charts"
        if vendored.exists():
            shutil.rmtree(vendored)
        result = _run(["helm", "dependency", "update", f"charts/{chart}"], dest)
        assert result.returncode == 0, (
            f"helm dependency update {chart}:\n{result.stderr}"
        )
    return dest


def _render(helm_copy: Path, *extra: str) -> list[dict]:
    result = _run(
        ["helmfile", "-e", "example", "template", "--skip-deps", *extra], helm_copy
    )
    assert result.returncode == 0, (
        f"helmfile -e example template {' '.join(extra)}:\n{result.stderr}"
    )
    objects = _objects(result.stdout)
    assert objects, "the render produced no objects"
    return objects


# ── Reading rendered objects ──────────────────────────────────────────────────


def chart_of(obj: dict) -> str:
    labels = (obj.get("metadata") or {}).get("labels") or {}
    return labels.get("helm.sh/chart", "")


def release_of(obj: dict) -> str:
    labels = (obj.get("metadata") or {}).get("labels") or {}
    return labels.get("app.kubernetes.io/instance", "")


def pod_spec(obj: dict) -> dict:
    if obj["kind"] == "Pod":
        return obj.get("spec") or {}
    return ((obj.get("spec") or {}).get("template") or {}).get("spec") or {}


def containers(obj: dict, init: bool = False) -> list[dict]:
    spec = pod_spec(obj)
    found = list(spec.get("containers") or [])
    if init:
        found += list(spec.get("initContainers") or [])
    return found


def container_env(obj: dict, name: str | None = None) -> dict[str, Any]:
    """Plain values as strings, references as their ``valueFrom`` dict."""
    env: dict[str, Any] = {}
    for container in containers(obj):
        if name and container["name"] != name:
            continue
        for item in container.get("env") or []:
            env[item["name"]] = (
                str(item["value"]) if "value" in item else item.get("valueFrom")
            )
    return env


def find(objects: list[dict], kind: str, name: str, namespace: str | None = None):
    hits = [
        o
        for o in objects
        if o["kind"] == kind
        and o["metadata"]["name"] == name
        and (namespace is None or o["metadata"].get("namespace") == namespace)
    ]
    assert len(hits) == 1, f"{kind}/{name} in {namespace}: {len(hits)} found"
    return hits[0]


# ── The pilot-shaped deployment ───────────────────────────────────────────────


def _token() -> str:
    return secrets.token_hex(24)


def _b64url() -> str:
    return secrets.token_urlsafe(32).rstrip("=")


def edr_key_pair() -> tuple[str, str]:
    """A private JWK and its public half, as the deployment's file holds them.

    The coordinates are random, not a curve point: nothing renders them into a
    signature, and the policy only compares the halves and the fixtures.
    """
    private = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(),
        "y": _b64url(),
        "d": _b64url(),
        "kid": "edr-key-1",
        "use": "sig",
    }
    public = {k: v for k, v in private.items() if k != "d"}
    return json.dumps(private), json.dumps(public)


def pilot_values() -> dict:
    return yaml.safe_load(PILOT_VALUES.read_text())


def pilot_secrets(values: dict) -> dict:
    """Every secret the pilot values need, generated: no placeholder, no dev
    default, every custody key distinct, every agreement pair equal."""
    svc_edc = _token()
    participants = {}
    postgres = {"identity_registry": _token()}
    for p in values["participants"]:
        name = p["name"]
        db = name.replace("-", "_")
        for prefix in ("identity_registry", "connector", "provenance", "edc"):
            postgres[f"{prefix}_{db}"] = _token()
        private, public = edr_key_pair()
        participants[name] = {
            "organisationClientSecret": _token(),
            "edcCallbackKey": _token(),
            "connectorAtRestKeys": _token(),
            "connectorKeyIndexSecret": _token(),
            "provenanceSubjectPseudonymKey": _token(),
            "edcControlApiKey": _token(),
            # Every EDC logs in as the one realm client `svc-edc`, so this is
            # the same value for every participant (and `svcEdcSecret`).
            "connectorClientSecret": svc_edc,
            "edcVault": {
                "edrSigningPrivateJwk": private,
                "edrSigningPublicJwk": public,
            },
            "stsSecret": _token(),
            "identityRegistryEncryptionKey": _token(),
        }
    return {
        "secrets": {
            "identityRegistryEncryptionKey": _token(),
            "oauth2ProxyCookieSecret": secrets.token_urlsafe(32),
            "svcDsIdentityRegistrySecret": _token(),
            "svcDsOnboardingSecret": _token(),
            "svcDsPortalSecret": _token(),
            "svcDsConnectorSecret": _token(),
            "svcDsFederatedCatalogSecret": _token(),
            "svcDsDatasetApiSecret": _token(),
            "svcEdcSecret": svc_edc,
            "oauth2ProxyClientSecret": _token(),
            "keycloakAdminUsername": "",
            "keycloakAdminPassword": "",
            "organisationClients": {},
            "postgres": postgres,
            "participants": participants,
        }
    }


PARENT_HELMFILE = """\
# A deployment's own helmfile: ds's helmfile is its base (secrets plan M1).
environments:
  {env}:
    values:
      - values.yaml
      - secrets.yaml
---
helmfiles:
  - path: {sub}
    values:
      - {{{{ toYaml .Values | nindent 8 }}}}
"""


class PilotRender:
    def __init__(
        self,
        result: subprocess.CompletedProcess[str],
        namespaces: dict[str, str] | None = None,
    ) -> None:
        self.returncode = result.returncode
        self.stderr = result.stderr
        self.stdout = result.stdout
        self.objects = _objects(result.stdout) if result.returncode == 0 else []
        # `helm template` leaves `metadata.namespace` unset unless a chart
        # templates it, and these charts do not: the release's namespace is
        # where an object lands, so it is stamped on from `helmfile list`.
        for obj in self.objects:
            meta = obj.setdefault("metadata", {})
            release = release_of(obj)
            release = release.removesuffix("-test")
            if not meta.get("namespace") and release in (namespaces or {}):
                meta["namespace"] = namespaces[release]

    def ok(self) -> list[dict]:
        assert self.returncode == 0, self.stderr
        assert self.objects, "the render produced no objects"
        return self.objects


@pytest.fixture(scope="session")
def pilot_base_secrets() -> dict:
    return pilot_secrets(pilot_values())


@pytest.fixture(scope="session")
def render_pilot(
    helm_copy: Path, tmp_path_factory: pytest.TempPathFactory, pilot_base_secrets: dict
) -> Callable[..., PilotRender]:
    """Render the pilot through a parent helmfile outside ``helm/``.

    ``values`` / ``secrets`` mutators get deep copies and change them in place;
    ``env`` is the parent's environment name.
    """

    def render(
        values: Callable[[dict], None] | None = None,
        secrets_: Callable[[dict], None] | None = None,
        env: str = "staging",
        omit_secrets: bool = False,
    ) -> PilotRender:
        work = tmp_path_factory.mktemp("deployment")
        v = pilot_values()
        if values:
            values(v)
        s = copy.deepcopy(pilot_base_secrets)
        if secrets_:
            secrets_(s)
        (work / "values.yaml").write_text(yaml.safe_dump(v, sort_keys=False))
        (work / "secrets.yaml").write_text(
            "{}\n" if omit_secrets else yaml.safe_dump(s, sort_keys=False)
        )
        (work / "helmfile.yaml.gotmpl").write_text(
            PARENT_HELMFILE.format(env=env, sub=helm_copy / "helmfile.yaml.gotmpl")
        )
        result = _run(["helmfile", "-e", env, "template", "--skip-deps"], work)
        namespaces = {}
        if result.returncode == 0:
            listed = _run(["helmfile", "-e", env, "list", "--output", "json"], work)
            assert listed.returncode == 0, listed.stderr
            namespaces = {r["name"]: r["namespace"] for r in json.loads(listed.stdout)}
        return PilotRender(result, namespaces)

    return render


@pytest.fixture(scope="session")
def pilot(render_pilot: Callable[..., PilotRender]) -> list[dict]:
    """T0.2: the pilot-shaped deployment renders through its own helmfile."""
    return render_pilot().ok()
