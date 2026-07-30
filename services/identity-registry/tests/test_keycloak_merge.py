"""The core/overlay split, and the ways it can go wrong.

`clients.yaml` declares what ds needs from a realm; `clients.<domain>.yaml`
declares what the domain backend deployed alongside it needs. They are merged
before the sync runs — not passed as two files — because `celine-policies keycloak
sync` takes exactly one file and **recomputes each client's grants from it**,
outside the `--prune` branch. Syncing the core alone would leave the overlay's
scopes in place and strip the grants that reference them off clients the core also
declares. These assertions pin the merge semantics that make that impossible.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from identity_registry.services import keycloak_merge as km

CORE = """\
realm: dataspaces
oauth2_proxy_client: oauth2_proxy
scopes:
  - name: connector.internal
    description: Internal API
  - name: dataset.read
    description: Read datasets
clients:
  - client_id: svc-ds-dataset-api
    name: Dataspace Dataset API
    secret: ${SVC_SECRET:-svc}
    scopes_prefix: dataset
    default_scopes:
      - connector.internal
    extra_audiences:
      - svc-ds-connector
"""

OVERLAY = """\
overlay: energy
scopes:
  - name: domain-registry.lookup
    description: Look a subject up in the domain registry
clients:
  - client_id: svc-domain-registry
    name: Domain Registry
    secret: ${DOMAIN_SECRET:-domain}
    scopes_prefix: domain-registry
    default_scopes:
      - domain-registry.lookup
  - client_id: svc-ds-dataset-api
    default_scopes:
      - domain-registry.lookup
    extra_audiences:
      - svc-domain-registry
"""

#: The core with a grant whose scope has moved to the overlay — R1's own footgun,
#: written out rather than assembled by string concatenation so it is obvious
#: *which* list the stray grant lands in.
CORE_WITH_A_STRAY_GRANT = CORE.replace(
    "      - connector.internal\n",
    "      - connector.internal\n      - domain-registry.lookup\n",
)


@pytest.fixture
def keycloak_dir(tmp_path: Path) -> Path:
    (tmp_path / "clients.yaml").write_text(CORE, encoding="utf-8")
    (tmp_path / "clients.energy.yaml").write_text(OVERLAY, encoding="utf-8")
    return tmp_path


def _merged(directory: Path, names: list[str]) -> dict:
    core = yaml.safe_load((directory / "clients.yaml").read_text(encoding="utf-8"))
    return km.merge(core, km.load_overlays(names, directory))


def _client(document: dict, client_id: str) -> dict:
    return next(c for c in document["clients"] if c["client_id"] == client_id)


# ── What the merge produces ──────────────────────────────────────────────────


def test_an_overlay_adds_its_own_scopes_and_clients(keycloak_dir: Path):
    merged = _merged(keycloak_dir, ["energy"])

    assert {s["name"] for s in merged["scopes"]} == {
        "connector.internal",
        "dataset.read",
        "domain-registry.lookup",
    }
    assert _client(merged, "svc-domain-registry")["scopes_prefix"] == "domain-registry"


def test_an_overlay_widens_a_core_client_rather_than_replacing_it(keycloak_dir: Path):
    """The case the whole mechanism exists for.

    `svc-ds-dataset-api` is ds's client; the grant it needs against the domain
    backend is the domain's to declare. The merged client must carry both, or the
    sync strips whichever file it was not shown.
    """
    dataset_api = _client(_merged(keycloak_dir, ["energy"]), "svc-ds-dataset-api")

    assert dataset_api["default_scopes"] == ["connector.internal", "domain-registry.lookup"]
    assert dataset_api["extra_audiences"] == ["svc-ds-connector", "svc-domain-registry"]
    # Identity untouched — the overlay named none of it.
    assert dataset_api["name"] == "Dataspace Dataset API"
    assert dataset_api["scopes_prefix"] == "dataset"


def test_merging_no_overlays_yields_the_core_unchanged(keycloak_dir: Path):
    core = yaml.safe_load((keycloak_dir / "clients.yaml").read_text(encoding="utf-8"))
    assert km.merge(core, []) == core


def test_the_merge_does_not_mutate_the_core(keycloak_dir: Path):
    """`build` renders from a fresh load, but a caller merging twice must not see
    the first overlay's grants accumulate onto the second result."""
    core = yaml.safe_load((keycloak_dir / "clients.yaml").read_text(encoding="utf-8"))
    overlays = km.load_overlays(["energy"], keycloak_dir)

    first = km.merge(core, overlays)
    second = km.merge(core, overlays)

    assert first == second
    assert _client(core, "svc-ds-dataset-api")["default_scopes"] == ["connector.internal"]


def test_two_overlays_asking_for_the_same_grant_add_it_once(keycloak_dir: Path):
    """A real case once a deployment runs two backends: both may need the same
    core client to hold something. A duplicate scope assignment is not an error to
    Keycloak, but it makes the effective file lie about what was declared."""
    (keycloak_dir / "clients.second.yaml").write_text(
        textwrap.dedent(
            """\
            overlay: second
            clients:
              - client_id: svc-ds-dataset-api
                default_scopes:
                  - domain-registry.lookup
                extra_audiences:
                  - svc-domain-registry
            """
        ),
        encoding="utf-8",
    )

    dataset_api = _client(
        _merged(keycloak_dir, ["energy", "second"]), "svc-ds-dataset-api"
    )

    assert dataset_api["default_scopes"] == ["connector.internal", "domain-registry.lookup"]
    assert dataset_api["extra_audiences"] == ["svc-ds-connector", "svc-domain-registry"]


# ── What an overlay may not do ───────────────────────────────────────────────


def test_a_missing_overlay_is_an_error_not_a_thinner_realm(keycloak_dir: Path):
    """A silently-thinner realm is the failure mode this mechanism exists to
    prevent, so a deployment naming an overlay it does not have must not fall back
    to a core-only sync."""
    with pytest.raises(km.MergeError) as exc:
        km.load_overlays(["nonexistent"], keycloak_dir)

    assert "nonexistent" in str(exc.value)
    assert "energy" in str(exc.value), "the error should name what is available"


def test_an_overlay_may_not_redefine_a_core_clients_identity(keycloak_dir: Path):
    """Letting an overlay restate `secret` or `scopes_prefix` would make it a
    second, unreviewable copy of the authority file."""
    (keycloak_dir / "clients.rogue.yaml").write_text(
        textwrap.dedent(
            """\
            overlay: rogue
            clients:
              - client_id: svc-ds-dataset-api
                secret: ${ROGUE:-rogue}
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(km.MergeError) as exc:
        _merged(keycloak_dir, ["rogue"])

    assert "secret" in str(exc.value)


def test_an_overlay_may_not_set_a_realm_level_key(keycloak_dir: Path):
    """Which realm ds talks to, and which client humans log in through, are ds's
    statements about the deployment — not a backend's."""
    (keycloak_dir / "clients.rogue.yaml").write_text(
        "overlay: rogue\nrealm: somewhere-else\n", encoding="utf-8"
    )

    with pytest.raises(km.MergeError) as exc:
        _merged(keycloak_dir, ["rogue"])

    assert "realm" in str(exc.value)


def test_an_overlay_may_not_redeclare_a_core_scope(keycloak_dir: Path):
    """A scope has exactly one definition. Two descriptions for one name means the
    realm's copy depends on merge order."""
    (keycloak_dir / "clients.rogue.yaml").write_text(
        textwrap.dedent(
            """\
            overlay: rogue
            scopes:
              - name: connector.internal
                description: Something else entirely
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(km.MergeError) as exc:
        _merged(keycloak_dir, ["rogue"])

    assert "connector.internal" in str(exc.value)


# ── Validation: the mistake the split makes possible ─────────────────────────


def test_a_grant_whose_scope_moved_to_an_overlay_is_caught(keycloak_dir: Path):
    """Move a scope out of the core and forget the grant that references it, and
    the merged file declares a grant nobody declares a scope for. `celine-policies`
    assigns by name, in a container whose log nobody reads — so catch it here."""
    (keycloak_dir / "clients.yaml").write_text(
        CORE_WITH_A_STRAY_GRANT, encoding="utf-8"
    )

    problems = km.validate(_merged(keycloak_dir, []))

    assert problems == [
        "svc-ds-dataset-api: default_scopes names undeclared scope domain-registry.lookup"
    ]


def test_that_same_grant_validates_once_the_overlay_is_applied(keycloak_dir: Path):
    (keycloak_dir / "clients.yaml").write_text(
        CORE_WITH_A_STRAY_GRANT, encoding="utf-8"
    )
    assert km.validate(_merged(keycloak_dir, ["energy"])) == []


def test_build_refuses_to_render_an_inconsistent_declaration(keycloak_dir: Path):
    (keycloak_dir / "clients.yaml").write_text(
        CORE_WITH_A_STRAY_GRANT, encoding="utf-8"
    )

    with pytest.raises(km.MergeError) as exc:
        km.build([], keycloak_dir)

    assert "undeclared scope" in str(exc.value)


def test_the_rendered_header_records_which_overlays_were_applied(keycloak_dir: Path):
    """The effective file is committed and gated by a no-diff test, so an operator
    who regenerates without `--overlay energy` produces a visible diff rather than
    a quietly thinner realm."""
    assert "# Overlays:   energy" in km.build(["energy"], keycloak_dir)
    assert "# Overlays:   (none)" in km.build([], keycloak_dir)


# ── Overlay discovery ────────────────────────────────────────────────────────


def test_generated_artefacts_are_not_mistaken_for_overlays(keycloak_dir: Path):
    """Both generated files sit beside the overlays and match `clients.*.yaml`.
    Treating one as an overlay would merge a realm into itself."""
    (keycloak_dir / "clients.effective.yaml").write_text("scopes: []\n", encoding="utf-8")
    (keycloak_dir / "clients.host.generated.yaml").write_text("scopes: []\n", encoding="utf-8")

    assert km.discover_overlays(keycloak_dir) == ["energy"]


# ── The real files ───────────────────────────────────────────────────────────


def test_the_core_file_names_no_domain_system():
    """R1's actual claim: ds's declaration of what it needs from a realm should
    not name somebody's domain backend."""
    core = yaml.safe_load(km.SOURCE.read_text(encoding="utf-8"))

    names = [s["name"] for s in core["scopes"]] + [
        c["client_id"] for c in core["clients"]
    ]
    leaked = [n for n in names if "rec-registry" in n or "rec_registry" in n]

    assert not leaked, f"core clients.yaml still names a domain system: {leaked}"

    for client in core["clients"]:
        strays = [s for s in client.get("default_scopes") or [] if "rec-registry" in s]
        assert not strays, f"{client['client_id']} still grants {strays}"


def test_the_committed_effective_file_is_not_stale():
    """If this fails, the core or an overlay changed and the effective file did
    not — run `task keycloak:merge` and commit the result. It is what
    `keycloak-sync` applies, so a stale copy is a realm that does not match the
    repository."""
    assert km.TARGET.exists(), "effective file missing — run `task keycloak:merge`"
    assert km.TARGET.read_text(encoding="utf-8") == km.build(
        km.discover_overlays()
    ), "effective clients file is stale — run `task keycloak:merge`"


def test_the_effective_file_restores_every_domain_grant():
    """The end-to-end property. `svc-ds-dataset-api` and `svc-ds-e2e` stay in the
    core file, so the sync recomputes their grants — and without the merge it
    would recompute them *without* the domain registry, which reads as a row
    filter resolving nobody rather than as an authorization error."""
    effective = yaml.safe_load(km.TARGET.read_text(encoding="utf-8"))

    assert "rec-registry.lookup" in _client(effective, "svc-ds-dataset-api")["default_scopes"]
    assert "svc-rec-registry" in _client(effective, "svc-ds-dataset-api")["extra_audiences"]
    assert "rec-registry.admin" in _client(effective, "svc-ds-e2e")["default_scopes"]
    assert "svc-rec-registry" in _client(effective, "svc-ds-e2e")["extra_audiences"]
    assert _client(effective, "svc-rec-registry")["scopes_prefix"] == "rec-registry"


def test_the_effective_file_keeps_the_realm_level_keys():
    """`oauth2_proxy_client` is what makes user tokens carry a per-service `aud`.
    Losing it in the merge would 401 every human at every service."""
    effective = yaml.safe_load(km.TARGET.read_text(encoding="utf-8"))
    core = yaml.safe_load(km.SOURCE.read_text(encoding="utf-8"))

    assert effective["realm"] == core["realm"]
    assert effective["oauth2_proxy_client"] == core["oauth2_proxy_client"]


def test_the_host_mirror_carries_no_domain_system():
    """The overlay is precisely what must not cross into a host realm: there
    `rec-registry.*` is the host's own service, not ds's to declare."""
    from identity_registry.services import keycloak_mirror

    core = yaml.safe_load(keycloak_mirror.SOURCE.read_text(encoding="utf-8"))
    built = keycloak_mirror.build_mirror(core)

    assert not [s for s in built["scopes"] if "rec-registry" in s["name"]]
    assert not [c for c in built["clients"] if "rec-registry" in c["client_id"]]
    for client in built["clients"]:
        assert not [s for s in client["default_scopes"] if "rec-registry" in s]
