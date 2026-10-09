"""The charts express what the local composition runs — asserted over a
pilot-shaped deployment rendered through its own helmfile.

Plans `the-charts-do-not-run-what-local-proved` (rows by number) and
`every-secret-has-one-source` (R*, the render-time policy). Every test names the
change that turns it red.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from conftest import (
    HELM_DIR,
    REPO_DIR,
    chart_of,
    container_env,
    containers,
    find,
    pod_spec,
    release_of,
)

REC, DSO = "example-rec", "example-dso"
AUTHORITY = "example-ds"
NS = {REC: f"example-ds-{REC}", DSO: f"example-ds-{DSO}"}
PLATFORM_NS = "example-platform"
ANCHOR_HOST = "trust-anchor.ds.example.org"


def _participant(values: dict, name: str) -> dict:
    return next(p for p in values["participants"] if p["name"] == name)


def _psec(s: dict, name: str) -> dict:
    return s["secrets"]["participants"][name]


# ── T0.2 — the pilot renders, through its own helmfile, in its own namespaces ─


def test_every_participant_has_its_releases_in_its_own_namespace(pilot):
    """T0.2. *Red:* disable a participant's registry release."""
    releases = {(o["metadata"].get("namespace"), release_of(o)) for o in pilot}
    for p in (REC, DSO):
        for svc in ("identity-registry", "edc", "provenance", "connector"):
            assert (NS[p], f"ds-{svc}-{p}") in releases, (svc, p)
    assert (AUTHORITY, "ds-identity-registry") in releases
    assert (NS[REC], f"ds-portal-{REC}") in releases
    assert (NS[REC], f"ds-oauth2-proxy-{REC}") in releases
    assert not any(r.startswith("ds-federated-catalog-") for _, r in releases)
    leaked = {
        r
        for _, r in releases
        for example in ("rec", "grid-operator", "third-party")
        if r.endswith(f"-{example}") and not r.endswith(f"example-{example}")
    }
    assert not leaked, f"ds's own example participants leaked into the render: {leaked}"


def test_nothing_names_a_default_namespace(pilot):
    """Staging puts ds in namespaces of its own choosing; a hard-coded
    `ds-authority` or `ds-<name>` anywhere is a pod that cannot reach its peer.
    *Red:* hard-code `ds-authority` in any `_env.tpl`."""
    text = yaml.safe_dump_all(pilot)
    assert "ds-authority" not in text
    for o in pilot:
        ns = o["metadata"].get("namespace")
        assert ns is None or ns.startswith("example-ds") or o["kind"] == "Namespace", (
            o["kind"],
            o["metadata"]["name"],
            ns,
        )


# ── M1 / R1 — the deployment's own files drive ds's helmfile ──────────────────


def test_the_render_needs_no_secrets_file_inside_helm(helm_copy: Path, pilot):
    """M1: ds's helmfile is a base. The copy has no `secrets.sops.yaml`, and the
    pilot's secrets live in the parent's directory. *Red:* make the `staging`
    environment require `secrets.sops.yaml` again."""
    assert not (helm_copy / "secrets.sops.yaml").exists()
    assert pilot


def test_no_secrets_at_all_fails_naming_where_they_come_from(render_pilot):
    """R1: with no secrets passed, the render fails and says what is missing,
    instead of a nil-pointer from deep inside a release. *Red:* drop the
    policy's presence check."""
    r = render_pilot(omit_secrets=True)
    assert r.returncode != 0
    assert "secrets.participants.example-rec" in r.stderr, r.stderr[-2000:]


# ── R2 — no placeholder outside `example` ──────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        ("svcDsPortalSecret",),
        ("postgres", "connector_example_dso"),
        ("participants", REC, "edcCallbackKey"),
        ("participants", DSO, "connectorAtRestKeys"),
        ("participants", DSO, "provenanceSubjectPseudonymKey"),
    ],
    ids=lambda p: ".".join(p),
)
def test_a_placeholder_fails_the_render_naming_the_key(render_pilot, path):
    """R2. *Red:* drop the placeholder check — a staging render with
    `CHANGE_ME` exits 0."""

    def put(s):
        node = s["secrets"]
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = "Change_Me"

    r = render_pilot(secrets_=put)
    assert r.returncode != 0
    assert "secrets." + ".".join(path) in r.stderr, r.stderr[-2000:]
    assert "Change_Me" not in r.stderr, "the value must never be printed"


def test_a_placeholder_inside_the_edr_key_fails(render_pilot):
    def put(s):
        _psec(s, REC)["edcVault"]["edrSigningPrivateJwk"] = (
            '{"kty":"EC","crv":"P-256","d":"CHANGE_ME","x":"CHANGE_ME","y":"CHANGE_ME"}'
        )
        _psec(s, REC)["edcVault"]["edrSigningPublicJwk"] = (
            '{"kty":"EC","crv":"P-256","x":"CHANGE_ME","y":"CHANGE_ME"}'
        )

    r = render_pilot(secrets_=put)
    assert r.returncode != 0
    assert "edrSigningPrivateJwk" in r.stderr, r.stderr[-2000:]


# ── R3 — no shared custody key ─────────────────────────────────────────────────


def test_the_anchor_and_a_participant_sharing_an_encryption_key_fail(render_pilot):
    """R3 (`D-47`). *Red:* drop the uniqueness assertion."""

    def share(s):
        _psec(s, DSO)["identityRegistryEncryptionKey"] = s["secrets"][
            "identityRegistryEncryptionKey"
        ]

    r = render_pilot(secrets_=share)
    assert r.returncode != 0
    assert "identityRegistryEncryptionKey" in r.stderr, r.stderr[-2000:]


@pytest.mark.parametrize("key", ["identityRegistryEncryptionKey", "edcControlApiKey"])
def test_two_participants_sharing_a_custody_key_fail(render_pilot, key):
    def share(s):
        _psec(s, DSO)[key] = _psec(s, REC)[key]

    r = render_pilot(secrets_=share)
    assert r.returncode != 0
    assert key in r.stderr, r.stderr[-2000:]


def test_every_edc_shares_the_one_svc_edc_secret(render_pilot):
    """Every EDC logs in as the one realm client `svc-edc`, so
    `connectorClientSecret` is the opposite of a custody key: two different
    values mean one EDC cannot log in. *Red:* treat it as a custody key (the
    pilot then fails), or drop the equality check (this passes)."""

    def differ(s):
        _psec(s, DSO)["connectorClientSecret"] = "a-different-svc-edc-secret-9f3c"

    r = render_pilot(secrets_=differ)
    assert r.returncode != 0
    assert "connectorClientSecret" in r.stderr, r.stderr[-2000:]


# ── R4 — no committed dev EDR key ──────────────────────────────────────────────


def _fixture_jwks() -> list[dict]:
    keys = []
    for f in sorted(
        (REPO_DIR / "services/connector/config").glob("*-vault.properties")
    ):
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                value = line.split("=", 1)[1].strip()
                if value.startswith("{"):
                    keys.append(json.loads(value))
    assert keys, "no fixture keys found — R4 checks nothing"
    return keys


def test_a_committed_fixture_edr_key_fails(render_pilot):
    """R4. *Red:* empty the fingerprint list."""
    fixture = _fixture_jwks()[0]

    def paste(s):
        _psec(s, DSO)["edcVault"]["edrSigningPrivateJwk"] = json.dumps(fixture)
        _psec(s, DSO)["edcVault"]["edrSigningPublicJwk"] = json.dumps(
            {k: v for k, v in fixture.items() if k != "d"}
        )

    r = render_pilot(secrets_=paste)
    assert r.returncode != 0
    assert "example-dso" in r.stderr and "fixture" in r.stderr, r.stderr[-2000:]
    assert fixture["d"] not in r.stderr


def test_the_fingerprint_list_is_the_fixtures_public_coordinates():
    """The helmfile's list is read off the fixtures, so a rotated fixture cannot
    leave the check guarding a key nobody uses. *Red:* add or drop an entry."""
    helmfile = (HELM_DIR / "helmfile.yaml.gotmpl").read_text()
    match = re.search(r"\$devEdrKeyX := list ([^\n}]+)", helmfile)
    assert match, "no $devEdrKeyX list in the helmfile"
    listed = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert listed == {k["x"] for k in _fixture_jwks()}


# ── The EDR key's two halves (chart parity OQ1 (b)) ────────────────────────────


def test_a_public_edr_key_that_is_not_the_private_ones_half_fails(render_pilot):
    """OQ1 (b): the operator supplies both halves; a mismatch would serve a key
    no EDR was signed with. *Red:* compare only the `kid`."""

    def mismatch(s):
        other = json.loads(_psec(s, DSO)["edcVault"]["edrSigningPublicJwk"])
        mine = json.loads(_psec(s, REC)["edcVault"]["edrSigningPublicJwk"])
        other["kid"] = mine["kid"]
        _psec(s, REC)["edcVault"]["edrSigningPublicJwk"] = json.dumps(other)

    r = render_pilot(secrets_=mismatch)
    assert r.returncode != 0
    assert "example-rec" in r.stderr and "edrSigningPublicJwk" in r.stderr, r.stderr[
        -2000:
    ]


def test_a_private_key_in_the_public_slot_fails(render_pilot):
    """The connector must hold no private material. *Red:* drop the `d` check."""

    def leak(s):
        v = _psec(s, REC)["edcVault"]
        v["edrSigningPublicJwk"] = v["edrSigningPrivateJwk"]

    r = render_pilot(secrets_=leak)
    assert r.returncode != 0
    assert "edrSigningPublicJwk" in r.stderr, r.stderr[-2000:]


# ── R5 — agreement pairs are single-source ─────────────────────────────────────


def _secret_data(objects, name, ns) -> dict:
    return find(objects, "Secret", name, ns).get("stringData") or {}


def _vault(objects, p) -> dict[str, str]:
    raw = _secret_data(objects, f"ds-edc-{p}", NS[p])["vault.properties"]
    out = {}
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


@pytest.mark.parametrize("p", [REC, DSO])
def test_the_agreement_pairs_hold(pilot, p):
    """R5: the EDC vault's callback key is the connector's, its STS secret is the
    participant registry's. *Red:* feed either side from another key."""
    vault = _vault(pilot, p)
    conn = _secret_data(pilot, f"ds-connector-{p}", NS[p])
    reg = _secret_data(pilot, f"ds-identity-registry-{p}", NS[p])
    assert vault["ds-connector-callback-key"] == conn["EDC_CALLBACK_KEY"]
    assert vault["sts-client-secret"] == reg["IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET"]


def test_an_organisation_client_secret_that_disagrees_fails(render_pilot):
    """Posture A: org-sync creates `svc-ds-connector-<alias>` with
    `organisationClients.<alias>.connectorSecret`, and the connector logs in with
    `participants.<p>.organisationClientSecret`. Two copies; a difference is a
    connector that cannot log in. *Red:* drop the equality check."""

    def posture_a(v):
        v["global"]["keycloak"]["sync"] = {
            "enabled": True,
            "organizationsConfigMap": "orgs",
            "organisations": {REC: {"collectsConsent": True}},
        }

    def differ(s):
        s["secrets"]["keycloakAdminUsername"] = "realm-admin"
        s["secrets"]["keycloakAdminPassword"] = "9d8c7b6a5f4e3d2c"
        s["secrets"]["organisationClients"] = {
            REC: {
                "connectorSecret": "not-the-same-9a8b7c",
                "collectorSecret": "c0ll3ct0r-5ecr3t-77",
            }
        }

    r = render_pilot(values=posture_a, secrets_=differ)
    assert r.returncode != 0
    assert f"organisationClients.{REC}.connectorSecret" in r.stderr, r.stderr[-2000:]


def test_no_template_generates_a_secret():
    """R6: a value generated at install differs between installs and from every
    other stack. *Red:* add `randAlphaNum` to any template."""
    pattern = re.compile(
        r"\b(lookup|randAlphaNum|randAlpha|randNumeric|randAscii|genPrivateKey|genCA|genSelfSignedCert)\b"
    )
    offenders = [
        str(f.relative_to(HELM_DIR))
        for f in list((HELM_DIR / "charts").rglob("*.tpl"))
        + list((HELM_DIR / "charts").rglob("*.yaml"))
        + [HELM_DIR / "helmfile.yaml.gotmpl"]
        if "/charts/ds-" in str(f)
        and pattern.search(f.read_text())
        and "/charts/charts/" not in str(f)
    ]
    assert not offenders, offenders


# ── Row 4 — the connector serves the EDR verification key ──────────────────────


@pytest.mark.parametrize("p", [REC, DSO])
def test_the_connector_holds_the_public_edr_key_and_nothing_private(
    pilot, pilot_base_secrets, p
):
    """T1.1 under OQ1 (b). *Red:* drop the mount, or mount the ds-edc Secret."""
    dep = find(pilot, "Deployment", f"ds-connector-{p}", NS[p])
    env = container_env(dep, "connector")
    path = env.get("CONNECTOR_EDC_VAULT_FILE")
    assert path, "CONNECTOR_EDC_VAULT_FILE not set"
    assert env.get("CONNECTOR_EDR_SIGNER_ALIAS") == "participant-private-key"
    mount_dir, filename = path.rsplit("/", 1)
    conn = next(c for c in containers(dep) if c["name"] == "connector")
    mount = next(
        m for m in conn.get("volumeMounts") or [] if m["mountPath"] == mount_dir
    )
    volume = next(v for v in pod_spec(dep)["volumes"] if v["name"] == mount["name"])
    assert volume["secret"]["secretName"] == f"ds-connector-{p}", (
        "must be the connector's own Secret"
    )
    item = next(i for i in volume["secret"]["items"] if i["path"] == filename)
    content = _secret_data(pilot, f"ds-connector-{p}", NS[p])[item["key"]]
    alias, _, raw = content.strip().partition("=")
    assert alias == "participant-private-key"
    served = json.loads(raw)
    assert "d" not in served
    expected = json.loads(
        _psec(pilot_base_secrets, p)["edcVault"]["edrSigningPublicJwk"]
    )
    assert {k: served[k] for k in ("kty", "crv", "x", "y")} == {
        k: expected[k] for k in ("kty", "crv", "x", "y")
    }
    for v in pod_spec(dep)["volumes"]:
        assert (v.get("secret") or {}).get("secretName") != f"ds-edc-{p}"


# ── Rows 9, 10 — governance: the deployment's ODRL profile; a change rolls ──────


def test_the_odrl_profile_path_names_the_mounted_file(pilot):
    """T1.2. *Red:* hard-code the path, or drop it."""
    env = container_env(
        find(pilot, "Deployment", f"ds-connector-{REC}", NS[REC]), "connector"
    )
    assert env.get("CONNECTOR_ODRL_PROFILE_PATH") == "/governance/odrl-profile.yaml"


def test_the_profile_path_follows_the_mount_and_the_file(render_pilot):
    """T1.2, the half the pilot's own values cannot show: a mount and a file
    other than the defaults. *Red:* hard-code the path."""

    def move(v):
        gov = _participant(v, DSO)["connector"]["governance"]
        gov["mountPath"] = "/etc/example-governance"
        gov["odrlProfileFile"] = "profile-staging.yaml"

    objects = render_pilot(values=move).ok()
    env = container_env(
        find(objects, "Deployment", f"ds-connector-{DSO}", NS[DSO]), "connector"
    )
    assert (
        env["CONNECTOR_ODRL_PROFILE_PATH"]
        == "/etc/example-governance/profile-staging.yaml"
    )


def test_without_a_profile_file_no_path_is_rendered(render_pilot):
    def drop(v):
        del _participant(v, DSO)["connector"]["governance"]["odrlProfileFile"]

    objects = render_pilot(values=drop).ok()
    env = container_env(
        find(objects, "Deployment", f"ds-connector-{DSO}", NS[DSO]), "connector"
    )
    assert "CONNECTOR_ODRL_PROFILE_PATH" not in env


def test_a_governance_change_rolls_the_connector_and_nothing_else(pilot, render_pilot):
    """T1.3. Two renders differing only in `governance.checksum` differ in that
    connector's pod annotation and nowhere else. *Red:* remove the annotation."""

    def bump(v):
        _participant(v, DSO)["connector"]["governance"]["checksum"] = "sha256-changed"

    changed = render_pilot(values=bump).ok()
    before = {
        (o["kind"], o["metadata"].get("namespace"), o["metadata"]["name"]): o
        for o in pilot
    }
    after = {
        (o["kind"], o["metadata"].get("namespace"), o["metadata"]["name"]): o
        for o in changed
    }
    assert before.keys() == after.keys()
    differing = [k for k in before if before[k] != after[k]]
    # Secrets are regenerated per render only if the secrets change; they do not.
    assert differing == [("Deployment", NS[DSO], f"ds-connector-{DSO}")], differing
    ann_b = before[differing[0]]["spec"]["template"]["metadata"]["annotations"]
    ann_a = after[differing[0]]["spec"]["template"]["metadata"]["annotations"]
    assert ann_b["checksum/governance"] == "sha256-of-the-assembled-governance-dso"
    assert ann_a["checksum/governance"] == "sha256-changed"


# ── Row 8 — who may call a connector ───────────────────────────────────────────


def _ingress_rules(objects, p):
    return [
        rule
        for o in objects
        if o["kind"] == "NetworkPolicy"
        and o["metadata"].get("namespace") == NS[p]
        and release_of(o) == f"ds-connector-{p}"
        for rule in (o["spec"].get("ingress") or [])
    ]


@pytest.mark.parametrize("p", [REC, DSO])
def test_the_host_platforms_callers_are_admitted_exactly(pilot, p):
    """T1.4: the consent writer and the data plane, in the host platform's own
    namespace, reach the connector's service port — and nothing else from that
    namespace. *Red:* admit the whole namespace, or every namespace."""
    peers = [
        (peer, rule["ports"])
        for rule in _ingress_rules(pilot, p)
        for peer in rule["from"]
        if ((peer.get("namespaceSelector") or {}).get("matchLabels") or {}).get(
            "kubernetes.io/metadata.name"
        )
        == PLATFORM_NS
    ]
    labels = sorted(
        (peer.get("podSelector") or {})
        .get("matchLabels", {})
        .get("app.kubernetes.io/name", "")
        for peer, _ in peers
    )
    assert labels == ["dataset-api", "onboarding"], peers
    for peer, ports in peers:
        assert ports == [{"protocol": "TCP", "port": 30001}]
        assert peer.get("podSelector", {}).get("matchLabels"), (
            "a whole namespace was admitted"
        )
    for rule in _ingress_rules(pilot, p):
        for peer in rule["from"]:
            assert peer.get("namespaceSelector", {}).get("matchLabels"), (
                "an empty namespaceSelector admits every namespace",
                peer,
            )


def test_no_ingress_from_renders_no_extra_rule(render_pilot):
    def drop(v):
        del _participant(v, DSO)["connector"]["networkPolicy"]

    objects = render_pilot(values=drop).ok()
    names = {
        o["metadata"]["name"]
        for o in objects
        if o["kind"] == "NetworkPolicy" and o["metadata"].get("namespace") == NS[DSO]
    }
    assert f"ds-connector-{DSO}-from-callers" not in names
    assert (
        f"ds-connector-{REC}-from-callers" not in names
    )  # other namespace, not listed


def test_an_ingress_from_entry_without_a_namespace_fails(render_pilot):
    def bad(v):
        _participant(v, DSO)["connector"]["networkPolicy"]["ingressFrom"] = [
            {"podLabels": {"app.kubernetes.io/name": "onboarding"}}
        ]

    r = render_pilot(values=bad)
    assert r.returncode != 0
    assert "ingressFrom" in r.stderr, r.stderr[-2000:]


# ── Rows 11, 17, 38 — the participant's blocks reach their charts ──────────────


def _sync_job(objects, p):
    return find(objects, "Job", f"ds-connector-{p}-sync", NS[p])


def test_a_sync_block_set_in_values_reaches_the_job(render_pilot):
    """T1.5. *Red:* revert the forwarding."""

    def publisher(v):
        _participant(v, DSO)["connector"]["sync"] = {"clientId": "svc-ds-publisher"}

    def secret(s):
        _psec(s, DSO)["publisherSecret"] = "p0bl1sh3r-s3cr3t-4e5f"

    objects = render_pilot(values=publisher, secrets_=secret).ok()
    job = _sync_job(objects, DSO)
    assert container_env(job)["SYNC_CLIENT_ID"] == "svc-ds-publisher"
    assert (
        _secret_data(objects, f"ds-connector-{DSO}", NS[DSO])["PUBLISHER_CLIENT_SECRET"]
        == "p0bl1sh3r-s3cr3t-4e5f"
    )


def test_a_client_id_reaches_the_connector_and_its_sync_job(render_pilot):
    """Row 38: a participant whose chart name differs from its organisation's
    alias. *Red:* forward `clientId` to one of the two only."""

    def alias(v):
        _participant(v, REC)["connector"]["clientId"] = (
            "svc-ds-connector-example-community"
        )

    objects = render_pilot(values=alias).ok()
    dep = find(objects, "Deployment", f"ds-connector-{REC}", NS[REC])
    assert (
        container_env(dep, "connector")["CONNECTOR_CLIENT_ID"]
        == "svc-ds-connector-example-community"
    )
    assert (
        container_env(_sync_job(objects, REC))["SYNC_CLIENT_ID"]
        == "svc-ds-connector-example-community"
    )


def test_the_row_17_values_reach_their_charts(render_pilot):
    """Row 17 (D1's additions): `personTokenRequired`, `trustAnchor.*`,
    `podAnnotations`, the EDC's `managementAudience`, the portal's `datasetApi`
    and `consumer`. *Red:* revert any one forward."""

    def set_all(v):
        rec = _participant(v, REC)
        rec["connector"]["personTokenRequired"] = False
        rec["connector"]["trustAnchor"] = {"credentialStatusCacheSeconds": 600}
        rec["connector"]["podAnnotations"] = {"example.org/owner": "data-team"}
        rec["provenance"]["personTokenRequired"] = False
        rec["edc"]["managementAudience"] = "svc-ds-edc-example"

    objects = render_pilot(values=set_all).ok()
    dep = find(objects, "Deployment", f"ds-connector-{REC}", NS[REC])
    env = container_env(dep, "connector")
    assert env["CONNECTOR_PERSON_TOKEN_REQUIRED"] == "false"
    assert env["CONNECTOR_CREDENTIAL_STATUS_CACHE_SECONDS"] == "600"
    assert (
        dep["spec"]["template"]["metadata"]["annotations"]["example.org/owner"]
        == "data-team"
    )
    prov = container_env(find(objects, "Deployment", f"ds-provenance-{REC}", NS[REC]))
    assert prov["PROVENANCE_PERSON_TOKEN_REQUIRED"] == "false"
    cm = find(objects, "ConfigMap", f"ds-edc-{REC}", NS[REC])
    assert "ds.management.audience=svc-ds-edc-example" in cm["data"]["edc.properties"]


@pytest.mark.parametrize("key", ["secrets", "participant", "global"])
def test_a_forwarded_block_cannot_carry_what_the_helmfile_owns(render_pilot, key):
    """The forwarded block is configuration; secrets come from the secrets file
    and identity from the participant entry — single-source. *Red:* drop the
    refusal and let the block override them."""

    def smuggle(v):
        _participant(v, REC)["connector"][key] = {"anything": "x"}

    r = render_pilot(values=smuggle)
    assert r.returncode != 0
    assert key in r.stderr, r.stderr[-2000:]


# ── Row 28 — a participant registry holds no other client's secret ─────────────


def test_a_participant_registry_holds_no_service_client_secret(
    pilot, pilot_base_secrets
):
    """T1.6: it was fed the `svc-edc` secret under `svc-ds-identity-registry`'s
    name. The service no longer requires it on a participant. *Red:* feed it
    again."""
    for p in (REC, DSO):
        data = _secret_data(pilot, f"ds-identity-registry-{p}", NS[p])
        assert "IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET" not in data
        env = container_env(
            find(pilot, "Deployment", f"ds-identity-registry-{p}", NS[p])
        )
        assert "IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET" not in env
    anchor = _secret_data(pilot, "ds-identity-registry", AUTHORITY)
    assert (
        anchor["IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET"]
        == pilot_base_secrets["secrets"]["svcDsIdentityRegistrySecret"]
    )


# ── OQ5, row 35 — one trust anchor host everywhere ─────────────────────────────


def test_every_service_trusts_the_anchor_the_anchor_is(pilot):
    """The anchor names itself from `trustAnchorDomain`; every participant
    derives it. *Red:* set the literal in values.yaml to another domain."""
    anchor_env = container_env(
        find(pilot, "Deployment", "ds-identity-registry", AUTHORITY)
    )
    assert anchor_env["IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN"] == ANCHOR_HOST
    seen = 0
    for o in pilot:
        if o["kind"] != "Deployment":
            continue
        env = container_env(o)
        for name, value in env.items():
            if not isinstance(value, str):
                continue
            if name.endswith("_TRUST_ANCHOR_DID"):
                assert value == f"did:web:{ANCHOR_HOST}", (o["metadata"]["name"], name)
                seen += 1
            if name.endswith(("_CREDENTIAL_STATUS_URL", "_TRUST_LIST_URL")):
                assert value.startswith(f"https://{ANCHOR_HOST}/"), (
                    o["metadata"]["name"],
                    name,
                )
                seen += 1
    for p in (REC, DSO):
        props = find(pilot, "ConfigMap", f"ds-edc-{p}", NS[p])["data"]["edc.properties"]
        assert f"did:web:{ANCHOR_HOST}" in props
    assert seen >= 12


def test_an_anchor_domain_that_disagrees_with_the_derived_one_fails(render_pilot):
    def literal(v):
        v["authority"]["identityRegistry"]["trustAnchorDomain"] = (
            "trust-anchor.elsewhere.example.org"
        )

    r = render_pilot(values=literal)
    assert r.returncode != 0
    assert "trustAnchorDomain" in r.stderr, r.stderr[-2000:]


# ── Rows 2, 21, 22 — the anchor's bootstrap carries a deployment ───────────────


def _bootstrap(objects):
    dep = find(objects, "Deployment", "ds-identity-registry", AUTHORITY)
    init = next(c for c in pod_spec(dep)["initContainers"] if c["name"] == "bootstrap")
    return dep, init


def test_seed_items_map_nested_paths(pilot):
    """T2.1 (row 21). *Red:* ignore `seedItems`."""
    dep, _ = _bootstrap(pilot)
    seed = next(v for v in pod_spec(dep)["volumes"] if v["name"] == "seed")
    assert seed["configMap"]["name"] == "example-ds-seed"
    assert {
        "key": "participation-en.md",
        "path": "content/participation-en.md",
    } in seed["configMap"]["items"]


def test_org_apply_runs_with_the_deployments_flags(pilot):
    """T2.2 (row 2): pinned through the helmfile. *Red:* stop forwarding
    `orgApply`."""
    _, init = _bootstrap(pilot)
    script = init["args"][0]
    line = next(l for l in script.splitlines() if "ir-cli org apply" in l)
    assert '--governance "/governance/example-rec.governance.yaml"' in line
    assert '--governance "/governance/example-dso.governance.yaml"' in line
    assert '--verified-by "example-deployment-staging"' in line
    assert '--evidence-ref "env/staging/owners.yaml"' in line
    assert 'sh "$SEED/bootstrap.sh"' in script  # row 22: collectors


def test_org_apply_without_verified_by_fails(render_pilot):
    def drop(v):
        v["authority"]["identityRegistry"]["bootstrap"]["orgApply"]["verifiedBy"] = ""

    r = render_pilot(values=drop)
    assert r.returncode != 0
    assert "verifiedBy" in r.stderr


# ── Rows 14, 16 — portal and edge ──────────────────────────────────────────────


def test_the_portal_names_no_federated_catalogue_it_does_not_have(pilot):
    """T3.1. *Red:* render it unconditionally."""
    env = container_env(find(pilot, "Deployment", f"ds-portal-{REC}", NS[REC]))
    assert "FEDERATED_CATALOG_URL" not in env


def test_the_portal_names_its_federated_catalogue_when_it_has_one(render_pilot):
    def enable(v):
        _participant(v, REC)["federatedCatalog"] = {
            "enabled": True,
            "connectorServiceName": f"ds-connector-{REC}.{NS[REC]}.svc.cluster.local",
        }

    objects = render_pilot(values=enable).ok()
    env = container_env(find(objects, "Deployment", f"ds-portal-{REC}", NS[REC]))
    assert env["FEDERATED_CATALOG_URL"] == f"http://ds-federated-catalog-{REC}:30003"


def test_the_portal_gets_its_catalogue_and_consumer_defaults(pilot):
    """T3.2. *Red:* revert the forwarding."""
    env = container_env(find(pilot, "Deployment", f"ds-portal-{REC}", NS[REC]))
    assert env["CATALOGUE_URL"] == "https://datasets.example.org"
    assert env["CONSUMER_DEFAULT_ASSIGNER"] == f"did:web:{DSO}.ds.example.org"


@pytest.mark.parametrize("p", [REC, DSO])
def test_the_participant_host_answers_dspace_version_at_its_root(pilot, p):
    """T3.3 (DSP 2025-1 SHOULD, RFC 8615): `/.well-known/dspace-version` on the
    host goes to EDC's protocol port as `/protocol/.well-known/dspace-version`;
    management and control stay unrouted. *Red:* route management."""
    host = f"{p}.ds.example.org"
    ingresses = [
        o
        for o in pilot
        if o["kind"] == "Ingress"
        and o["metadata"].get("namespace") == NS[p]
        and release_of(o) == f"ds-edc-{p}"
    ]
    found = []
    for ing in ingresses:
        for rule in ing["spec"]["rules"]:
            assert rule["host"] == host
            for path in rule["http"]["paths"]:
                port = path["backend"]["service"]["port"]["number"]
                assert port not in (19192, 19193), "management or control routed"
                if path["path"] == "/.well-known/dspace-version":
                    found.append((ing, port))
    assert len(found) == 1, found
    ing, port = found[0]
    assert port == 19194
    assert (
        ing["metadata"]["annotations"]["nginx.ingress.kubernetes.io/rewrite-target"]
        == "/protocol/.well-known/dspace-version"
    )


# ── Phase 4 — the doctor's chart-owned rows as `helm test` hooks ───────────────


def _tests(objects):
    return [
        o
        for o in objects
        if o["kind"] == "Pod"
        and (o["metadata"].get("annotations") or {}).get("helm.sh/hook") == "test"
    ]


def test_each_surface_ds_owns_has_a_helm_test(pilot):
    """T4 at render level: one test Pod per surface, each asserting content.
    Whether each one passes healthy and fails broken is T4.1, on a cluster (D3).
    *Red:* drop a chart's `templates/tests/`."""
    names = {o["metadata"]["name"] for o in _tests(pilot)}
    for p in (REC, DSO):
        assert f"ds-edc-{p}-test-did-document" in names
        assert f"ds-identity-registry-{p}-test-registry" in names
        assert f"ds-connector-{p}-test-catalogue" in names
    assert f"ds-portal-{REC}-test-public-paths" in names
    assert not any(n.startswith("ds-identity-registry-test") for n in names), (
        "the anchor is not a participant registry"
    )


@pytest.mark.parametrize("p", [REC, DSO])
def test_the_did_test_asserts_the_document_id(pilot, p):
    pod = next(
        o
        for o in _tests(pilot)
        if o["metadata"]["name"] == f"ds-edc-{p}-test-did-document"
    )
    env = container_env(pod)
    assert env["EXPECT_DID"] == f"did:web:{p}.ds.example.org"
    assert env["DID_URL"].endswith("/.well-known/did.json")


def test_test_pods_are_reachable_under_default_deny(pilot):
    """A test Pod that the release's own NetworkPolicy selects fails for the
    wrong reason: the release's default-deny selects name **and** instance, so a
    test Pod carries the chart's name (which `fromWorkloads` admits) and an
    instance of its own. *Red:* give it the release's selector labels."""
    selectors = [
        (
            o["metadata"].get("namespace"),
            o["spec"]["podSelector"].get("matchLabels") or {},
        )
        for o in pilot
        if o["kind"] == "NetworkPolicy"
    ]
    for pod in _tests(pilot):
        labels = pod["metadata"]["labels"]
        assert labels.get("app.kubernetes.io/component") == "test", pod["metadata"][
            "name"
        ]
        assert chart_of(pod)
        for ns, match in selectors:
            if ns == pod["metadata"].get("namespace") and match:
                assert not all(labels.get(k) == v for k, v in match.items()), (
                    pod["metadata"]["name"],
                    match,
                )
