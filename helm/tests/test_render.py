"""Render tests for the chart set, run locally with ``task helm:test``.

No cluster, no CI: ``helm lint`` and ``helmfile -e example template``, parsed as
YAML, with assertions over the objects. The whole ``helm/`` tree is copied to a
temporary directory first, because ``helm dependency update`` writes into it.

Every assertion names the change that turns it red.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest
import yaml
from conftest import (
    CHARTS,
    HELM_DIR,
    PilotRender,
    _key,
    _render,
    _run,
    container_env,
    containers,
    find,
    pod_spec,
    release_of,
)

# The value that selected the removed ExternalSecret mode. Rendering with it set
# proves no chart still reads it.
FORMER_EXTERNAL_SECRETS_FLAG = "global.externalSecrets.enabled=true"


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
        if labels.get("app.kubernetes.io/component") == "test":
            continue  # a `helm test` Pod, not a release
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
        "participants[0].connector.governance.configMap=gov",
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
            assert env.get("SYNC_SCOPE") == "connector.provider.write", job["metadata"][
                "name"
            ]
        else:
            assert "SYNC_SCOPE" not in env, job["metadata"]["name"]


def test_the_catalogue_test_matches_ids_and_accepts_an_empty_catalogue(
    provider_with_governance_render: list[dict],
) -> None:
    """The `catalogue` helm test proves the governance against what is
    offered — the asset ids must match; nothing exposed and nothing offered is a
    configured state and passes. *Red:* compare counts again, or refuse an empty
    catalogue whatever the governance says."""
    pods = [
        obj
        for obj in provider_with_governance_render
        if obj["kind"] == "Pod" and obj["metadata"]["name"].endswith("-test-catalogue")
    ]
    assert pods, "no catalogue test pod rendered"
    for pod in pods:
        script = " ".join(
            " ".join((c.get("command") or []) + (c.get("args") or []))
            for c in pod["spec"]["containers"]
        )
        assert "asset_id_for" in script, pod["metadata"]["name"]
        assert "offered - expected" in script and "expected - offered" in script
        assert "the catalogue is empty" not in script, pod["metadata"]["name"]


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


ORG_SYNC = [
    "--state-values-set",
    "global.keycloak.sync.enabled=true,"
    "global.keycloak.sync.organizationsConfigMap=orgs,"
    "global.keycloak.sync.organisations.example-org.collectsConsent=true,"
    "global.keycloak.sync.organisations.other-org.collectsConsent=false,"
    "secrets.organisationClients.other-org.connectorSecret=s,"
    "secrets.keycloakAdminUsername=a,"
    "secrets.keycloakAdminPassword=b",
]


def test_org_sync_gets_the_connector_and_collector_secrets(helm_copy: Path) -> None:
    """ADR-0026: org-sync creates `svc-ds-connector-<alias>` for every declared
    organisation and `svc-ds-collector-<alias>` for one that collects consent,
    and under production refuses a client it has no secret for. The helmfile
    renders both from its secrets and the job reads them. *Red:* drop the
    `organisations`/`organisationClients` lines from the helmfile, or the
    `envFrom` from the org-sync container."""
    objects = _render(helm_copy, *ORG_SYNC)
    secrets = [
        o
        for o in objects
        if o["kind"] == "Secret"
        and o["metadata"]["name"].endswith("-organisation-clients")
    ]
    assert len(secrets) == 1, [_key(o) for o in secrets]
    data = secrets[0].get("stringData") or {}
    assert set(data) == {
        "SVC_DS_CONNECTOR_EXAMPLE_ORG_SECRET",
        "SVC_DS_COLLECTOR_EXAMPLE_ORG_SECRET",
        "SVC_DS_CONNECTOR_OTHER_ORG_SECRET",
    }, sorted(data)
    assert all(data.values())
    name = secrets[0]["metadata"]["name"]
    readers = [
        c["name"]
        for o in objects
        if o["kind"] == "Deployment"
        for c in (o["spec"]["template"]["spec"].get("initContainers") or [])
        + (o["spec"]["template"]["spec"].get("containers") or [])
        if any(
            (ref.get("secretRef") or {}).get("name") == name
            for ref in c.get("envFrom") or []
        )
    ]
    assert readers == ["keycloak-org-sync"], readers


def test_a_collector_without_its_secret_does_not_render(helm_copy: Path) -> None:
    """A declared collector with no collector secret fails the render, naming the
    key. *Red:* drop the `required` in organisation-client-secret.yaml."""
    result = _run(
        [
            "helmfile",
            "-e",
            "example",
            "template",
            "--skip-deps",
            *ORG_SYNC,
            "--state-values-set",
            "secrets.organisationClients.example-org.collectorSecret=",
        ],
        helm_copy,
    )
    assert result.returncode != 0
    assert (
        "secrets.organisationClients.example-org.collectorSecret is required"
        in result.stderr
    )


# ==============================================================================
# The participant profile (WS-A of the deployment plan: ds1–ds4 and the database
# names). Rendered through a deployment's own helmfile (`render_pilot`), the shape
# a parent drives. Every test names the change that turns it red.
# ==============================================================================


REC, DSO = "example-rec", "example-dso"
AUTH_NS = "example-ds"
CODE_REC = "enrolment-code-of-example-rec-0123456789abcdef"
CODE_DSO = "enrolment-code-of-example-dso-0123456789abcdef"


def _p(values: dict, name: str) -> dict:
    return next(p for p in values["participants"] if p["name"] == name)


def _refused(render: PilotRender, *needles: str) -> None:
    assert render.returncode != 0, "the render succeeded"
    for needle in needles:
        assert needle in render.stderr, render.stderr[-2000:]


def _objects_of(objects: list[dict], release: str) -> list[dict]:
    return [o for o in objects if release_of(o) == release]


# ── ds1: participants as profiles; `enabled` honoured everywhere ──────────────


def _add_disabled(values: dict) -> None:
    # Only what a declared-but-off participant carries: no role, no blocks, and
    # no secrets entry at all.
    values["participants"].append({"name": "example-off", "enabled": False})


def test_a_disabled_participant_renders_nothing(render_pilot):
    """A declared participant with `enabled: false`, no role and no secrets leaves
    no trace: no namespace, release, connector URL, ConfigMap or Secret. *Red:*
    validate or range a participant before checking `enabled`."""
    objects = render_pilot(values=_add_disabled).ok()
    text = yaml.safe_dump_all(objects)
    assert "example-off" not in text


def test_a_participant_without_enabled_fails(render_pilot):
    """`enabled` is the explicit flag: absent is an error, not "off". *Red:* drop the
    presence check, and an entry missing the key silently renders nothing."""
    def values(v):
        del _p(v, DSO)["enabled"]
    _refused(render_pilot(values=values), f"participants[{DSO}].enabled")


def test_enabled_must_be_a_boolean(render_pilot):
    """`enabled: "false"` is a string, which a template reads as true. *Red:* drop the
    kind check."""
    def values(v):
        _p(v, DSO)["enabled"] = "false"
    _refused(render_pilot(values=values), f"participants[{DSO}].enabled", "boolean")


def test_a_role_outside_the_vocabulary_fails(render_pilot):
    """*Red:* drop the role enum check: `producer` reaches the charts."""
    def values(v):
        _p(v, DSO)["role"] = "producer"
    _refused(render_pilot(values=values), f"participants[{DSO}].role", "provider, consumer or both")


def test_a_feature_switch_must_be_a_boolean(render_pilot):
    """*Red:* drop the kind check on `portal.enabled`."""
    def values(v):
        _p(v, DSO)["portal"]["enabled"] = "yes"
    _refused(render_pilot(values=values), f"participants[{DSO}].portal.enabled", "boolean")


def test_participant_defaults_reach_every_participant(render_pilot):
    """`participantDefaults` is merged under each entry; the entry wins. *Red:* drop
    the merge, and DSO's connector admits nobody from the platform."""
    def values(v):
        v["participantDefaults"] = {
            "connector": {"networkPolicy": {"ingressFrom": [
                {"namespace": "example-shared", "podLabels": {"app.kubernetes.io/name": "writer"}}
            ]}}
        }
        del _p(v, DSO)["connector"]["networkPolicy"]
    objects = render_pilot(values=values).ok()
    dso = find(objects, "NetworkPolicy", f"ds-connector-{DSO}-from-callers")
    rec = find(objects, "NetworkPolicy", f"ds-connector-{REC}-from-callers")
    assert "example-shared" in yaml.safe_dump(dso)
    # REC's own list replaces the default.
    assert "example-shared" not in yaml.safe_dump(rec)
    assert "example-platform" in yaml.safe_dump(rec)


def test_participant_defaults_refuse_identity_and_switches(render_pilot):
    """A default `portal.enabled: true` could not be turned off by an entry (zero
    values do not override in a merge), so only chart blocks are allowed. *Red:*
    accept any key in `participantDefaults`."""
    def values(v):
        v["participantDefaults"] = {"portal": {"enabled": True}}
    _refused(render_pilot(values=values), "participantDefaults.portal")


# ── ds1: the collector switch ─────────────────────────────────────────────────


def _collector(values: dict) -> None:
    _p(values, REC)["collector"] = {"enabled": True, "holders": [DSO]}


def test_a_collector_gets_its_pair_from_the_anchor(render_pilot):
    """`collector.enabled` with holders renders the anchor's pairing Job, which adds
    `holder ← collector` once both are active. *Red:* drop the collectors Job."""
    objects = render_pilot(values=_collector).ok()
    jobs = [o for o in objects if o["kind"] == "Job" and o["metadata"]["name"].startswith("ds-identity-registry-collectors-")]
    assert len(jobs) == 1, [o["metadata"]["name"] for o in objects if o["kind"] == "Job"]
    script = " ".join(" ".join(c.get("args") or []) for c in containers(jobs[0]))
    assert f"did:web:{DSO}.ds.example.org" in script
    assert f"did:web:{REC}.ds.example.org" in script
    assert "ir-cli collector add" in script
    # Not a hook: it waits for the enrolment, which happens after this release.
    assert "helm.sh/hook" not in (jobs[0]["metadata"].get("annotations") or {})


def test_no_collector_renders_no_pairing_job(pilot):
    """*Red:* render the Job unconditionally."""
    assert not [o for o in pilot if o["kind"] == "Job" and "-collectors-" in o["metadata"]["name"]]


@pytest.mark.parametrize("holders", [[], ["example-nobody"], ["example-off"]])
def test_a_collector_without_a_live_holder_fails(render_pilot, holders):
    """No holder, an unknown one or a disabled one is a pair that can never form.
    *Red:* drop the holder checks."""
    def values(v):
        _add_disabled(v)
        _p(v, REC)["collector"] = {"enabled": True, "holders": holders}
    _refused(render_pilot(values=values), f"participants[{REC}].collector.holders")


# ── ds2: a portal host per participant ────────────────────────────────────────


def _two_portals(values: dict) -> None:
    _p(values, DSO)["portal"] = {"enabled": True, "replicaCount": 1}


def test_two_portals_on_one_host_fail(render_pilot):
    """Two portals defaulting to portal.<baseDomain> would collide on one Ingress
    host. *Red:* drop the uniqueness check: the render succeeds with two owners of
    the host."""
    _refused(render_pilot(values=_two_portals), "portal.ds.example.org", REC, DSO)


def test_each_portal_has_its_own_host(render_pilot):
    """`portal.host` moves a participant's portal, its oauth2-proxy, its ORIGIN and
    its connector's portal link together. *Red:* ignore `portal.host` in any of the
    four."""
    host = "portal-example-dso.ds.example.org"

    def values(v):
        _two_portals(v)
        _p(v, DSO)["portal"]["host"] = host
    objects = render_pilot(values=values).ok()

    def hosts(release: str) -> set[str]:
        return {
            rule["host"]
            for o in _objects_of(objects, release)
            if o["kind"] == "Ingress"
            for rule in o["spec"]["rules"]
        }
    assert hosts(f"ds-portal-{DSO}") == {host}
    assert hosts(f"ds-oauth2-proxy-{DSO}") == {host}
    assert hosts(f"ds-portal-{REC}") == {"portal.ds.example.org"}
    assert hosts(f"ds-oauth2-proxy-{REC}") == {"portal.ds.example.org"}
    portal_env = container_env(find(objects, "Deployment", f"ds-portal-{DSO}"))
    assert portal_env["ORIGIN"] == f"https://{host}"
    proxy = yaml.safe_dump([o for o in _objects_of(objects, f"ds-oauth2-proxy-{DSO}") if o["kind"] in ("ConfigMap", "Deployment")])
    assert f"https://{host}/oauth2/callback" in proxy
    conn_env = container_env(find(objects, "Deployment", f"ds-connector-{DSO}"))
    assert conn_env["CONNECTOR_NOTIFY_PORTAL_BASE_URL"] == f"https://{host}"


# ── ds3: seed and governance ConfigMaps from values ───────────────────────────


GOV = "# governance of example-dso\ndatasets: {}\n"


def _gov_files(values: dict) -> None:
    gov = _p(values, DSO)["connector"]["governance"]
    gov.pop("configMap")
    gov.pop("checksum")
    gov["files"] = {"governance.yaml": GOV, "governance.staging.yaml": "datasets: {}\n", "odrl-profile.yaml": "profile: {}\n"}


def test_governance_files_render_the_connectors_configmap(render_pilot):
    """The parent passes content; the chart renders the ConfigMap, mounts it and
    derives the checksum from it. *Red:* drop the ConfigMap template or the mount."""
    objects = render_pilot(values=_gov_files).ok()
    cm = find(objects, "ConfigMap", f"ds-connector-{DSO}-governance")
    assert cm["data"]["governance.yaml"] == GOV
    dep = find(objects, "Deployment", f"ds-connector-{DSO}")
    vols = {v["name"]: v for v in pod_spec(dep)["volumes"]}
    assert vols["governance"]["configMap"]["name"] == f"ds-connector-{DSO}-governance"
    checksum = dep["spec"]["template"]["metadata"]["annotations"]["checksum/governance"]
    assert len(checksum) == 64
    # The sync hook and the catalogue test read the same ConfigMap.
    sync = find(objects, "Job", f"ds-connector-{DSO}-sync")
    assert sync


def test_the_governance_checksum_follows_the_content(render_pilot):
    """*Red:* compute the checksum from anything but the files (or not at all)."""
    def sums(gov: str) -> str:
        def values(v):
            _gov_files(v)
            _p(v, DSO)["connector"]["governance"]["files"]["governance.yaml"] = gov
        dep = find(render_pilot(values=values).ok(), "Deployment", f"ds-connector-{DSO}")
        return dep["spec"]["template"]["metadata"]["annotations"]["checksum/governance"]
    assert sums(GOV) != sums(GOV + "# changed\n")


@pytest.mark.parametrize("extra", ["configMap", "checksum"])
def test_governance_files_with_a_configmap_or_checksum_fail(render_pilot, extra):
    """Two sources for one mount, or a hand digest of content the chart hashes
    itself. *Red:* let either through."""
    def values(v):
        _gov_files(v)
        _p(v, DSO)["connector"]["governance"][extra] = "x"
    _refused(render_pilot(values=values), "governance.files", f"governance.{extra}")


SEED = {"agreements.yaml": "agreements: []\n", "owners.yaml": "owners: []\n", "participation-en.md": "# terms\n", "bootstrap.sh": "true\n"}


def _seed_files(values: dict) -> None:
    b = values["authority"]["identityRegistry"]["bootstrap"]
    b.pop("seedConfigMap")
    b.pop("governanceConfigMap")
    b["seedFiles"] = dict(SEED)
    b["governanceFiles"] = {f"{REC}.governance.yaml": "datasets: {}\n", f"{DSO}.governance.yaml": GOV}


def test_seed_and_governance_files_render_the_anchors_configmaps(render_pilot):
    """*Red:* drop the anchor's ConfigMap templates, their mounts or checksums."""
    objects = render_pilot(values=_seed_files).ok()
    seed = find(objects, "ConfigMap", "ds-identity-registry-seed")
    gov = find(objects, "ConfigMap", "ds-identity-registry-governance")
    assert seed["data"] == SEED
    assert gov["data"][f"{DSO}.governance.yaml"] == GOV
    dep = find(objects, "Deployment", "ds-identity-registry")
    vols = {v["name"]: v for v in pod_spec(dep)["volumes"]}
    assert vols["seed"]["configMap"]["name"] == "ds-identity-registry-seed"
    # seedItems still map keys to nested paths.
    assert {"key": "participation-en.md", "path": "content/participation-en.md"} in vols["seed"]["configMap"]["items"]
    assert vols["governance"]["configMap"]["name"] == "ds-identity-registry-governance"
    ann = dep["spec"]["template"]["metadata"]["annotations"]
    assert len(ann["checksum/seed"]) == 64 and len(ann["checksum/governance"]) == 64


def test_the_seed_checksum_follows_the_content(render_pilot):
    """A changed owners.yaml rolls the anchor, so its bootstrap re-runs. *Red:* no
    checksum, or one over anything else."""
    def sums(owners: str) -> str:
        def values(v):
            _seed_files(v)
            v["authority"]["identityRegistry"]["bootstrap"]["seedFiles"]["owners.yaml"] = owners
        dep = find(render_pilot(values=values).ok(), "Deployment", "ds-identity-registry")
        return dep["spec"]["template"]["metadata"]["annotations"]["checksum/seed"]
    assert sums("owners: []\n") != sums("owners: [{id: x}]\n")


@pytest.mark.parametrize("pair", [("seedFiles", "seedConfigMap"), ("governanceFiles", "governanceConfigMap")])
def test_anchor_files_with_a_configmap_fail(render_pilot, pair):
    """*Red:* let both sources through."""
    def values(v):
        _seed_files(v)
        v["authority"]["identityRegistry"]["bootstrap"][pair[1]] = "x"
    _refused(render_pilot(values=values), f"bootstrap.{pair[0]}", f"bootstrap.{pair[1]}")


# ── ds4: enrolment of co-hosted participants ──────────────────────────────────


def _enrol(values: dict) -> None:
    for name in (REC, DSO):
        _p(values, name)["enrolment"] = {"enabled": True}


def _codes(s: dict) -> None:
    s["secrets"]["participants"][REC]["enrolmentCode"] = CODE_REC
    s["secrets"]["participants"][DSO]["enrolmentCode"] = CODE_DSO


def test_enrolment_is_off_by_default(pilot):
    """*Red:* render the enrolment objects unconditionally."""
    names = [o["metadata"]["name"] for o in pilot]
    assert not [n for n in names if "enrol" in n], [n for n in names if "enrol" in n]


def test_the_anchor_registers_each_code_in_a_hook(render_pilot):
    """The anchor's post-install/upgrade hook registers each co-hosted participant's
    code, read from a Secret, with the roles and scopes its role implies. *Red:* drop
    the hook, its `--code-env`, or derive the wrong roles."""
    objects = render_pilot(values=_enrol, secrets_=_codes).ok()
    hook = find(objects, "Job", "ds-identity-registry-enrolment")
    ann = hook["metadata"]["annotations"]
    assert ann["helm.sh/hook"] == "post-install,post-upgrade"
    script = " ".join(" ".join(c.get("args") or []) for c in containers(hook))
    assert "--alias example-rec --roles provider,consumer" in script
    assert "--scope owner:example-rec:member" in script
    assert "--alias example-dso --roles provider " in script
    assert "--scope owner:example-dso:member" not in script
    assert script.count("--code-env") == 2
    assert CODE_REC not in yaml.safe_dump(hook)
    codes = find(objects, "Secret", "ds-identity-registry-enrolment")
    assert set(codes["stringData"].values()) == {CODE_REC, CODE_DSO}


def test_the_participant_spends_its_code_once_in_a_job(render_pilot):
    """The participant registry release spends its code in a Job that retries until
    its DID document resolves (served by its running registry through ds-edc's
    Ingress, after this release), and skips when enrolled. *Red:* make it a hook
    (a deadlock with ds-edc), an init container, or drop the status check."""
    objects = render_pilot(values=_enrol, secrets_=_codes).ok()
    jobs = [o for o in _objects_of(objects, f"ds-identity-registry-{DSO}") if o["kind"] == "Job"]
    assert len(jobs) == 1, [o["metadata"]["name"] for o in jobs]
    job = jobs[0]
    assert job["metadata"]["name"].startswith(f"ds-identity-registry-{DSO}-enrol-")
    assert "helm.sh/hook" not in (job["metadata"].get("annotations") or {})
    script = " ".join(" ".join(c.get("args") or []) for c in containers(job))
    assert "ir-cli participant status --quiet" in script
    assert "ir-cli participant init --code" in script
    assert CODE_DSO not in yaml.safe_dump(job)
    secret = find(objects, "Secret", f"ds-identity-registry-{DSO}")
    assert secret["stringData"]["ENROLMENT_CODE"] == CODE_DSO
    dep = find(objects, "Deployment", f"ds-identity-registry-{DSO}")
    assert "ENROLMENT_CODE" not in yaml.safe_dump(pod_spec(dep).get("initContainers"))
    assert "participant init --code" not in yaml.safe_dump(pod_spec(dep).get("initContainers"))


def test_enrolment_without_a_code_fails(render_pilot):
    """*Red:* drop the presence check: the hook fails on the cluster instead."""
    _refused(render_pilot(values=_enrol), f"secrets.participants.{REC}.enrolmentCode")


def test_a_short_or_shared_enrolment_code_fails(render_pilot):
    """*Red:* drop the length or the uniqueness check."""
    def short(s):
        _codes(s)
        s["secrets"]["participants"][DSO]["enrolmentCode"] = "short-code"
    _refused(render_pilot(values=_enrol, secrets_=short), f"secrets.participants.{DSO}.enrolmentCode", "32")

    def shared(s):
        _codes(s)
        s["secrets"]["participants"][DSO]["enrolmentCode"] = CODE_REC
    _refused(render_pilot(values=_enrol, secrets_=shared), "enrolmentCode")


# ── Database names: the deployment's prefix ───────────────────────────────────


def _ds_prefix(values: dict) -> None:
    values["global"].setdefault("postgres", {})["databases"] = {"namePrefix": "ds_"}


def _ds_prefixed_passwords(s: dict) -> None:
    pg = s["secrets"]["postgres"]
    s["secrets"]["postgres"] = {f"ds_{k}": v for k, v in pg.items()}


def test_a_name_prefix_renames_every_database_and_role(render_pilot):
    """`namePrefix: ds_` gives the contract's role names, and each password is read
    from `secrets.postgres.<that name>`. *Red:* derive any name or password key
    without the prefix."""
    objects = render_pilot(values=_ds_prefix, secrets_=_ds_prefixed_passwords).ok()
    found = set()
    for o in objects:
        if o["kind"] != "Secret":
            continue
        user = (o.get("stringData") or {}).get("DB_USER") or (o.get("stringData") or {}).get("EDC_DB_USER")
        if user:
            found.add(user)
    expected = {"ds_identity_registry"} | {
        f"ds_{svc}_{p.replace('-', '_')}" for p in (REC, DSO)
        for svc in ("identity_registry", "connector", "provenance", "edc")
    }
    assert found == expected, sorted(found)
    for o in objects:
        if o["kind"] == "Deployment":
            for v in container_env(o).values():
                if isinstance(v, str) and "postgresql" in v:
                    assert "/ds_" in v, v


def test_a_missing_database_password_fails_naming_the_key(render_pilot):
    """*Red:* look the password up without a presence check: the chart's own
    `required` names `secrets.dbPassword`, not the deployment's key."""
    def secrets_(s):
        del s["secrets"]["postgres"]["connector_example_dso"]
    _refused(render_pilot(secrets_=secrets_), "secrets.postgres.connector_example_dso")


# ── The secrets generator follows the profile ─────────────────────────────────


def _generate(tmp_path: Path, values: dict, tool: Path | None = None) -> dict:
    import subprocess
    import sys

    vf, out = tmp_path / "values.yaml", tmp_path / "secrets.yaml"
    vf.write_text(yaml.safe_dump(values))
    result = subprocess.run(
        ["uv", "run", "-q", "--no-project", "--with", "pyyaml", "--with", "cryptography",
         "python", str(tool or HELM_DIR / "tools" / "generate_secrets.py"),
         "--values", str(vf), "--out", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return yaml.safe_load(out.read_text())


def test_the_generator_follows_names_enrolment_and_collectors(tmp_path):
    """The generated file is what the render policy asks for: passwords under the
    prefixed database names, a code per participant with enrolment on, a collector
    secret per collector, nothing for a disabled participant. *Red:* keep the
    hard-coded names, or skip a switch."""
    values = {
        "global": {"postgres": {"databases": {"namePrefix": "ds_"}}},
        "participants": [
            {"name": REC, "enabled": True, "role": "both", "enrolment": {"enabled": True},
             "collector": {"enabled": True, "holders": [DSO]}},
            {"name": DSO, "enabled": True, "role": "provider"},
            {"name": "example-off", "enabled": False},
        ],
    }
    doc = _generate(tmp_path, values)
    pg = doc["secrets"]["postgres"]
    assert set(pg) == {"ds_identity_registry"} | {
        f"ds_{svc}_{p.replace('-', '_')}" for p in (REC, DSO)
        for svc in ("identity_registry", "connector", "provenance", "edc")
    }
    parts = doc["secrets"]["participants"]
    assert set(parts) == {REC, DSO}
    assert len(parts[REC]["enrolmentCode"]) >= 32
    assert "enrolmentCode" not in parts[DSO]
    assert set(doc["realmOnly"]["collectorClients"]) == {REC}


# ── Everything on at once ─────────────────────────────────────────────────────


def _everything(values: dict) -> None:
    _enrol(values)
    _collector(values)
    _gov_files(values)
    _seed_files(values)
    _two_portals(values)
    _p(values, DSO)["portal"]["host"] = "portal-example-dso.ds.example.org"


def test_every_pod_with_every_switch_on_meets_the_restricted_profile(render_pilot):
    """The enrolment and collector Jobs are admitted by the namespaces' Pod Security
    level. *Red:* render one of their containers without `ds.containerSecurityContext`."""
    from test_pod_security import _violations

    objects = render_pilot(values=_everything, secrets_=_codes).ok()
    assert _violations(objects) == []


def test_no_job_pod_joins_a_service(render_pilot):
    """A Ready Job pod matching a Service's selector would receive its traffic: the
    anchor fetching a participant's DID document could land on the enrolment Job.
    *Red:* give the enrolment or collector Job's pods the release's selector labels."""
    objects = render_pilot(values=_everything, secrets_=_codes).ok()
    services = [o for o in objects if o["kind"] == "Service"]
    jobs = [o for o in objects if o["kind"] == "Job"]
    assert any("-enrol-" in j["metadata"]["name"] for j in jobs)
    for job in jobs:
        labels = job["spec"]["template"]["metadata"].get("labels") or {}
        ns = job["metadata"].get("namespace")
        for svc in services:
            selector = svc["spec"].get("selector") or {}
            if svc["metadata"].get("namespace") != ns or not selector:
                continue
            if "-sync" in job["metadata"]["name"]:
                continue  # the connector's publish hook: seconds long, pre-existing
            assert not all(labels.get(k) == v for k, v in selector.items()), (
                job["metadata"]["name"], svc["metadata"]["name"])


def test_the_enrolment_pods_are_under_their_own_network_policy(render_pilot):
    """Not selected by the release's policies, so they get their own: DNS and
    Postgres, and the participant's also 443 to its anchor. *Red:* drop the policy
    (the pods would run with no egress restriction at all)."""
    objects = render_pilot(values=_everything, secrets_=_codes).ok()
    for release, tls in (("ds-identity-registry", False), (f"ds-identity-registry-{DSO}", True)):
        pol = find(objects, "NetworkPolicy", f"{release}-enrolment")
        assert pol["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/instance"] == f"{release}-enrolment"
        ports = {p["port"] for rule in pol["spec"]["egress"] for p in rule.get("ports") or []}
        assert 5432 in ports and 53 in ports
        assert (443 in ports) is tls


# ── DNS through a node-local cache ────────────────────────────────────────────


def _dns_rules(objects):
    """Every egress rule on port 53, by policy name."""
    for pol in objects:
        if pol["kind"] != "NetworkPolicy":
            continue
        for rule in pol["spec"].get("egress") or []:
            if any(p.get("port") == 53 for p in rule.get("ports") or []):
                yield pol["metadata"]["name"], rule


def test_dns_egress_reaches_only_kube_dns_by_default(render_pilot):
    """Unset, the DNS rule admits the `k8s-app: kube-dns` pods and nothing else.
    *Red:* default `global.networkPolicy.dnsExtraTo` to anything."""
    objects = render_pilot(values=_everything, secrets_=_codes).ok()
    rules = list(_dns_rules(objects))
    assert rules
    for name, rule in rules:
        assert rule["to"] == [{"namespaceSelector": {}, "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}], name


def test_dns_egress_admits_the_extra_peers_it_is_given(render_pilot):
    """A cluster whose pods resolve through NodeLocal DNSCache (a host-network address,
    which no pod selector reaches) lists it in `global.networkPolicy.dnsExtraTo`, and
    every DNS rule carries it, the enrolment Jobs' included. *Red:* drop the helper
    from the default-deny or from the enrolment policy (a pod there cannot resolve,
    and an OIDC discovery or a Postgres host lookup hangs)."""
    peer = {"ipBlock": {"cidr": "169.254.20.10/32"}}

    def values(v):
        _everything(v)
        v.setdefault("global", {}).setdefault("networkPolicy", {})["dnsExtraTo"] = [peer]
    objects = render_pilot(values=values, secrets_=_codes).ok()
    rules = dict(_dns_rules(objects))
    assert f"ds-identity-registry-{DSO}-enrolment" in rules
    assert any(n.startswith("ds-oauth2-proxy") for n in rules)
    for name, rule in rules.items():
        assert rule["to"][0]["podSelector"] == {"matchLabels": {"k8s-app": "kube-dns"}}, name
        assert rule["to"][1:] == [peer], name


def test_an_empty_dns_peer_fails_the_render(render_pilot):
    """An empty peer admits every address on port 53: refused, never silently
    widened. *Red:* drop the check."""
    def values(v):
        v.setdefault("global", {}).setdefault("networkPolicy", {})["dnsExtraTo"] = [{}]
    result = render_pilot(values=values)
    assert result.returncode != 0
    assert "global.networkPolicy.dnsExtraTo[0] is empty" in result.stderr


# ── Egress to the trace collector ─────────────────────────────────────────────

_COLLECTOR = {
    "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "example-observability"}},
    "podSelector": {"matchLabels": {"app.kubernetes.io/name": "example-collector"}},
}


def _tracing(endpoint="http://collector.example-observability.svc:4318", egress_to=(_COLLECTOR,)):
    def values(v):
        _everything(v)
        tracing = v.setdefault("global", {}).setdefault("tracing", {})
        tracing["endpoint"] = endpoint
        if egress_to is not None:
            tracing["egressTo"] = list(egress_to)
    return values


def _collector_rules(objects, port):
    """Every egress rule on the collector's port, by policy name."""
    for pol in objects:
        if pol["kind"] != "NetworkPolicy":
            continue
        for rule in pol["spec"].get("egress") or []:
            if any(p.get("port") == port for p in rule.get("ports") or []):
                yield pol["metadata"]["name"], rule


def test_no_tracing_endpoint_opens_no_collector_egress(render_pilot):
    """Unset, no policy admits a collector. *Red:* render the rule unconditionally."""
    objects = render_pilot(values=_everything, secrets_=_codes).ok()
    assert not list(_collector_rules(objects, 4318))


def test_a_tracing_endpoint_admits_the_collector_from_every_default_deny(render_pilot):
    """Every pod is default-deny egress and the exporter drops rather than blocks, so a
    collector the policies do not admit reads as a quiet service. With an endpoint, every
    default-deny policy and the enrolment Jobs' carry one rule to `egressTo` on the
    endpoint's port. *Red:* drop the helper from either policy."""
    objects = render_pilot(values=_tracing(), secrets_=_codes).ok()
    rules = dict(_collector_rules(objects, 4318))
    deny = {o["metadata"]["name"] for o in objects
            if o["kind"] == "NetworkPolicy" and o["metadata"]["name"].endswith("-default-deny")}
    assert deny and deny <= set(rules), deny - set(rules)
    assert f"ds-identity-registry-{DSO}-enrolment" in rules
    for name, rule in rules.items():
        assert rule == {"to": [_COLLECTOR], "ports": [{"protocol": "TCP", "port": 4318}]}, name


def test_a_tracing_endpoint_without_peers_fails_the_render(render_pilot):
    """*Red:* drop the check (tracing on, every span dropped at the policy)."""
    _refused(render_pilot(values=_tracing(egress_to=None), secrets_=_codes), "global.tracing.egressTo is empty")


def test_a_tracing_endpoint_without_a_port_fails_the_render(render_pilot):
    """*Red:* default the port (a guess that is wrong for gRPC, or a proxy)."""
    _refused(render_pilot(values=_tracing(endpoint="http://collector.example-observability.svc"), secrets_=_codes),
             "has no explicit port")


def test_an_empty_collector_peer_fails_the_render(render_pilot):
    """An empty peer admits every address on the port. *Red:* drop the check."""
    _refused(render_pilot(values=_tracing(egress_to=({},)), secrets_=_codes), "global.tracing.egressTo[0] is empty")


def _exporters(objects):
    """(object name, container name, env list) for every container exporting spans."""
    for obj in objects:
        spec = ((obj.get("spec") or {}).get("template") or {}).get("spec") or {}
        for c in (spec.get("initContainers") or []) + (spec.get("containers") or []):
            env = c.get("env") or []
            if any(e["name"] == "OTEL_EXPORTER_OTLP_ENDPOINT" for e in env):
                yield obj["metadata"]["name"], c, env


def _edc_containers(objects):
    return [c for name, c, _ in _exporters(objects) if c["name"] == "edc"]


def test_every_exporter_says_which_namespace_sent_its_spans(render_pilot):
    """`service.name` is the same in every participant; the namespace is what tells
    them apart. The kubelet expands `$(POD_NAMESPACE)` only from a variable defined
    *earlier* in the list, so the order is asserted too. *Red:* drop the attribute
    from `ds.env.common`, or move it above `POD_NAMESPACE`."""
    exporters = list(_exporters(render_pilot(values=_tracing(), secrets_=_codes).ok()))
    assert exporters
    for name, c, env in exporters:
        names = [e["name"] for e in env]
        assert len(names) == len(set(names)), (name, c["name"])
        attrs = next(e for e in env if e["name"] == "OTEL_RESOURCE_ATTRIBUTES")
        assert attrs["value"] == "k8s.namespace.name=$(POD_NAMESPACE)", (name, c["name"])
        assert names.index("POD_NAMESPACE") < names.index("OTEL_RESOURCE_ATTRIBUTES"), (name, c["name"])


def test_resource_attributes_given_are_appended_not_rendered_twice(render_pilot):
    """A deployment's own `OTEL_RESOURCE_ATTRIBUTES` joins the namespace (later keys
    win in OpenTelemetry's parser). Two entries of one name would leave the
    kubelet's choice as the deployment's. *Red:* render `attributes` unfiltered."""
    def values(v):
        _tracing()(v)
        v["global"]["tracing"]["attributes"] = {"OTEL_RESOURCE_ATTRIBUTES": "deployment.environment=staging"}
    for name, c, env in _exporters(render_pilot(values=values, secrets_=_codes).ok()):
        attrs = [e["value"] for e in env if e["name"] == "OTEL_RESOURCE_ATTRIBUTES"]
        assert attrs == ["k8s.namespace.name=$(POD_NAMESPACE),deployment.environment=staging"], (name, c["name"])


def test_no_tracing_endpoint_sets_no_resource_attributes(render_pilot):
    """*Red:* render the attribute outside the endpoint's `with`."""
    for obj in render_pilot(values=_everything, secrets_=_codes).ok():
        assert "OTEL_RESOURCE_ATTRIBUTES" not in _container_env(obj), obj["metadata"]["name"]


def test_the_edc_runs_through_the_image_entrypoint(render_pilot):
    """`entrypoint.sh` attaches the OpenTelemetry agent; a `command` replaces it, and
    the EDC then runs with the endpoint set and no agent — measured on a cluster.
    *Red:* `command:` back on the edc container."""
    edcs = _edc_containers(render_pilot(values=_tracing(), secrets_=_codes).ok())
    assert edcs
    for c in edcs:
        assert "command" not in c
        assert c["args"][-1].startswith("java $JAVA_OPTS ")


def test_every_edc_is_named_by_its_release(render_pilot):
    """The image sets no service name; unnamed, every EDC reports as
    `unknown_service:java`. A name in `attributes` is the deployment's. *Red:* drop
    `OTEL_SERVICE_NAME` from the ds-edc chart."""
    objects = render_pilot(values=_tracing(), secrets_=_codes).ok()
    names = {n: next(e["value"] for e in env if e["name"] == "OTEL_SERVICE_NAME")
             for n, c, env in _exporters(objects) if c["name"] == "edc"}
    assert names and all(v == n for n, v in names.items()), names

    def named(v):
        _tracing()(v)
        v["global"]["tracing"]["attributes"] = {"OTEL_SERVICE_NAME": "edc"}
    for n, c, env in _exporters(render_pilot(values=named, secrets_=_codes).ok()):
        if c["name"] == "edc":
            assert [e["value"] for e in env if e["name"] == "OTEL_SERVICE_NAME"] == ["edc"], n


# ── The anchor's in-cluster callers (WS-C request: the host's onboarding) ─────


def test_the_anchor_admits_the_callers_it_is_given(render_pilot):
    """`authority.identityRegistry.networkPolicy.ingressFrom` admits exactly the named
    namespace (and pods) on the registry port, as the connector's does: the host
    platform's onboarding calls `/owners`, `/memberships`, `/admin`, which are on no
    Ingress. *Red:* drop the policy or the helmfile line."""
    def values(v):
        v["authority"]["identityRegistry"]["networkPolicy"] = {"ingressFrom": [
            {"namespace": "example-platform", "podLabels": {"app.kubernetes.io/name": "onboarding"}}
        ]}
    objects = render_pilot(values=values).ok()
    pol = find(objects, "NetworkPolicy", "ds-identity-registry-from-callers")
    peer = pol["spec"]["ingress"][0]["from"][0]
    assert peer["namespaceSelector"]["matchLabels"] == {"kubernetes.io/metadata.name": "example-platform"}
    assert peer["podSelector"]["matchLabels"] == {"app.kubernetes.io/name": "onboarding"}
    assert pol["spec"]["ingress"][0]["ports"] == [{"protocol": "TCP", "port": 30005}]
    assert not [o for o in objects if o["kind"] == "NetworkPolicy" and o["metadata"]["name"].startswith("ds-identity-registry-example") and o["metadata"]["name"].endswith("-from-callers")]


def test_no_anchor_caller_renders_no_policy(pilot):
    """*Red:* render the policy with an empty list."""
    assert not [o for o in pilot if o["metadata"]["name"] == "ds-identity-registry-from-callers"]


def test_an_anchor_caller_without_a_namespace_fails(render_pilot):
    """An empty namespaceSelector admits every namespace. *Red:* drop the check."""
    def values(v):
        v["authority"]["identityRegistry"]["networkPolicy"] = {"ingressFrom": [{"podLabels": {"a": "b"}}]}
    _refused(render_pilot(values=values), "networkPolicy.ingressFrom[0] has no namespace")
