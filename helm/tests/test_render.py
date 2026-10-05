"""Render tests for the chart set, run locally with ``task helm:test``.

No cluster, no CI: ``helm lint`` and ``helmfile -e example template``, parsed as
YAML, with assertions over the objects. The whole ``helm/`` tree is copied to a
temporary directory first, because ``helm dependency update`` writes into it.

Every assertion names the change that turns it red.
"""

from __future__ import annotations

import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

HELM_DIR = Path(__file__).resolve().parent.parent
CHARTS = sorted(
    p.name for p in (HELM_DIR / "charts").iterdir() if (p / "Chart.yaml").is_file()
)

# The value that selected the removed ExternalSecret mode. Rendering with it set
# proves no chart still reads it.
FORMER_EXTERNAL_SECRETS_FLAG = "global.externalSecrets.enabled=true"


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
    shutil.copytree(
        HELM_DIR,
        dest,
        ignore=shutil.ignore_patterns(
            "Chart.lock", "tests", "__pycache__", ".pytest_cache"
        ),
    )
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


@pytest.fixture(scope="session")
def default_render(helm_copy: Path) -> list[dict]:
    """T0.1: the example environment renders, exit 0. *Red:* delete a `required` secret key."""
    return _render(helm_copy)


@pytest.fixture(scope="session")
def flagged_render(helm_copy: Path) -> list[dict]:
    return _render(helm_copy, "--set", FORMER_EXTERNAL_SECRETS_FLAG)


@pytest.mark.parametrize("chart", CHARTS)
@pytest.mark.parametrize(
    "extra", [[], ["--set", FORMER_EXTERNAL_SECRETS_FLAG]], ids=["default", "flagged"]
)
def test_every_chart_lints(helm_copy: Path, chart: str, extra: list[str]) -> None:
    """T0.3: `helm lint` passes on every chart. *Red:* break a template."""
    result = _run(["helm", "lint", f"charts/{chart}", *extra], helm_copy)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("render", ["default_render", "flagged_render"])
def test_no_external_secret_renders(
    render: str, request: pytest.FixtureRequest
) -> None:
    """The ExternalSecret mode is gone. *Red:* restore a chart's `externalsecret.yaml`
    and the `ds.externalSecret` helper: the flagged render emits ExternalSecret CRs."""
    objects = request.getfixturevalue(render)
    found = [_key(o) for o in objects if o["kind"] == "ExternalSecret"]
    assert not found, f"ExternalSecret objects rendered: {found}"


def test_every_release_with_a_secret_template_renders_its_secret(
    flagged_render: list[dict],
) -> None:
    """Every release of a chart that has `templates/secret.yaml` renders its Secret,
    even with the former ExternalSecret flag set. *Red:* restore the
    `externalSecrets.enabled` branch in `ds.createSecret`: the flagged render has no
    Secret at all."""
    charts_with_secret = {
        c
        for c in CHARTS
        if (HELM_DIR / "charts" / c / "templates" / "secret.yaml").is_file()
    }
    assert charts_with_secret, "no chart has templates/secret.yaml"

    kinds_by_release: dict[str, set[str]] = defaultdict(set)
    chart_of_release: dict[str, str] = {}
    for obj in flagged_render:
        labels = (obj.get("metadata") or {}).get("labels") or {}
        release = labels.get("app.kubernetes.io/instance")
        chart_label = labels.get("helm.sh/chart", "")
        chart = next(
            (c for c in charts_with_secret if chart_label.startswith(f"{c}-")), None
        )
        if release and chart:
            kinds_by_release[release].add(obj["kind"])
            chart_of_release[release] = chart

    assert set(chart_of_release.values()) == charts_with_secret, (
        f"charts with a secret template but no release in the example render: "
        f"{sorted(charts_with_secret - set(chart_of_release.values()))}"
    )
    missing = sorted(
        r for r, kinds in kinds_by_release.items() if "Secret" not in kinds
    )
    assert not missing, f"releases that render no Secret: {missing}"


def test_the_former_flag_changes_nothing(
    default_render: list[dict], flagged_render: list[dict]
) -> None:
    """Setting the former flag leaves the rendered object set (kind, namespace, name)
    unchanged. *Red:* any template still reading `global.externalSecrets`."""
    default_keys = sorted(_key(o) for o in default_render)
    flagged_keys = sorted(_key(o) for o in flagged_render)
    assert flagged_keys == default_keys


def _container_env(obj: dict) -> dict[str, str]:
    spec = ((obj.get("spec") or {}).get("template") or {}).get("spec") or {}
    env: dict[str, str] = {}
    for container in spec.get("containers") or []:
        for item in container.get("env") or []:
            if "value" in item:
                env[item["name"]] = str(item["value"])
    return env


def test_every_credential_verifier_reads_the_status_registers(
    default_render: list[dict],
) -> None:
    """R3: a service that accepts a user credential reads the anchor's status
    registers — its ProductionGuard refuses to start without the URL. *Red:*
    drop `*_CREDENTIAL_STATUS_URL` from a chart's `_env.tpl`."""
    seen = []
    for obj in default_render:
        if obj["kind"] != "Deployment":
            continue
        env = _container_env(obj)
        for prefix in ("CONNECTOR", "PROVENANCE"):
            if f"{prefix}_TRUST_ANCHOR_DID" in env:
                seen.append(obj["metadata"]["name"])
                url = env.get(f"{prefix}_CREDENTIAL_STATUS_URL", "")
                assert url.startswith("https://") and url.endswith("/status/1"), (
                    obj["metadata"]["name"],
                    url,
                )
                # Unset is required under DS_ENV=production; only an explicit
                # value may relax it, and the example sets none — so the
                # registry that binds the login must be named.
                assert f"{prefix}_PERSON_TOKEN_REQUIRED" not in env
                assert env.get(f"{prefix}_IDENTITY_REGISTRY_URL", "").startswith(
                    "http://ds-identity-registry."
                )
    assert seen, "no connector or provenance Deployment rendered"


@pytest.fixture(scope="session")
def provider_with_governance_render(helm_copy: Path) -> list[dict]:
    """The example with governance mounted on its provider — the only shape in
    which the connector's sync job renders."""
    return _render(
        helm_copy,
        "--state-values-set",
        "participants[0].connector.governanceConfigMap=gov",
    )


def test_the_sync_job_asks_the_organisation_client_for_the_publish_grant(
    provider_with_governance_render: list[dict],
) -> None:
    """ADR-0026: `connector.provider.write` is optional on the organisation
    client, so the hook that publishes with it must request it, or the sync is a
    403 and the release fails. *Red:* drop `SYNC_SCOPE` from `syncjob.yaml`."""
    jobs = [
        obj
        for obj in provider_with_governance_render
        if obj["kind"] == "Job" and "SYNC_CLIENT_ID" in _container_env(obj)
    ]
    assert jobs, "no connector sync job rendered"
    for job in jobs:
        env = _container_env(job)
        script = " ".join(
            " ".join(c.get("command") or [])
            for c in job["spec"]["template"]["spec"]["containers"]
        )
        assert "SYNC_SCOPE" in script, job["metadata"]["name"]
        if env["SYNC_CLIENT_ID"].startswith("svc-ds-connector-"):
            assert env.get("SYNC_SCOPE") == "connector.provider.write", job[
                "metadata"
            ]["name"]
        else:
            assert "SYNC_SCOPE" not in env, job["metadata"]["name"]


def _chart_of(obj: dict) -> str:
    labels = (obj.get("metadata") or {}).get("labels") or {}
    return labels.get("helm.sh/chart", "")


def test_every_edc_names_the_management_audience(default_render: list[dict]) -> None:
    """R12: the runtime refuses to boot without `ds.management.audience`, and the
    audience is the one the `edc.management` scope adds (`svc-ds-edc`), as in
    `services/connector/config/*.properties`. *Red:* drop the line from the
    ds-edc configmap."""
    configmaps = [
        obj
        for obj in default_render
        if obj["kind"] == "ConfigMap" and _chart_of(obj).startswith("ds-edc-")
    ]
    assert configmaps, "no ds-edc ConfigMap rendered"
    for cm in configmaps:
        props = (cm.get("data") or {}).get("edc.properties", "").splitlines()
        assert "ds.management.audience=svc-ds-edc" in [p.strip() for p in props], cm[
            "metadata"
        ]["name"]


def test_every_provenance_reads_its_pseudonym_key_from_its_secret(
    default_render: list[dict],
) -> None:
    """R19, ADR-0025: the record's hash chain covers a keyed pseudonym of every
    person id, and the ProductionGuard refuses the dev key under the chart's
    DS_ENV=production — so the chart must supply one, from the release's Secret.
    *Red:* drop `PROVENANCE_SUBJECT_PSEUDONYM_KEY` from the provenance
    `_env.tpl` or `secret.yaml`."""
    secrets = {
        obj["metadata"]["name"]: obj
        for obj in default_render
        if obj["kind"] == "Secret" and _chart_of(obj).startswith("ds-provenance-")
    }
    deployments = [
        obj
        for obj in default_render
        if obj["kind"] == "Deployment" and _chart_of(obj).startswith("ds-provenance-")
    ]
    assert deployments, "no ds-provenance Deployment rendered"
    for dep in deployments:
        name = dep["metadata"]["name"]
        refs = [
            item["valueFrom"]["secretKeyRef"]
            for c in dep["spec"]["template"]["spec"]["containers"]
            for item in c.get("env") or []
            if item["name"] == "PROVENANCE_SUBJECT_PSEUDONYM_KEY"
            and "secretKeyRef" in (item.get("valueFrom") or {})
        ]
        assert refs, f"{name}: PROVENANCE_SUBJECT_PSEUDONYM_KEY not from a Secret"
        ref = refs[0]
        secret = secrets.get(ref["name"])
        assert secret, f"{name}: Secret {ref['name']} not rendered"
        assert (secret.get("stringData") or {}).get(ref["key"]), (
            f"{name}: {ref['key']} empty in {ref['name']}"
        )


def test_a_provenance_without_a_pseudonym_key_does_not_render(
    helm_copy: Path,
) -> None:
    """The key is `required`, like the database password: the chart always runs
    DS_ENV=production, where the service refuses the dev key, so an empty value
    must fail the render, not the pod. *Red:* drop the `required`."""
    result = _run(
        [
            "helm",
            "template",
            "p",
            "charts/ds-provenance",
            "--set",
            "secrets.dbPassword=x",
        ],
        helm_copy,
    )
    assert result.returncode != 0
    assert "secrets.subjectPseudonymKey is required" in result.stderr
    result = _run(
        [
            "helm",
            "template",
            "p",
            "charts/ds-provenance",
            "--set",
            "secrets.dbPassword=x",
            "--set",
            "secrets.subjectPseudonymKey=k",
        ],
        helm_copy,
    )
    assert result.returncode == 0, result.stderr
