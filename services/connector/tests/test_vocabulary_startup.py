"""The vocabulary cache at startup, and the deployment wiring that feeds it.

`task e2e:all` cannot reach any of this. The e2e suite exercises an *exchange* —
catalogue, negotiate, transfer — and this is a publication mechanism: nothing in
a flow reads `/ns/{slug}`, and a broken startup loader shows up as a container
that never becomes healthy, which the suite reports as a dependency timeout with
no mention of vocabularies. So it is asserted here or nowhere.

Two layers, matching the two ways this can break:

1. `_load_vocabulary_cache` — the **fail-closed** decision. A connector that
   boots while `/ns/{slug}` 404s has published a reference its own catalogue
   names in `dct:conformsTo` and cannot serve.
2. The compose wiring — the cache directory has to be writable and the registry
   has to be *findable*, neither of which any Python test would notice.

**Helm is not covered here, and nothing else covers it either**: no test in this
repository renders a chart, so `helm lint` and `helm template` remain manual.
That matters more for this feature than for most, because the chart's default
path is an `emptyDir` cache — so a misrendered mount turns every pod start into a
dependency on an external host. Verified by hand across three render paths
(nothing registered / registry only / registry plus supplied cache); a
`helm unittest` harness would be a repo-wide addition, not a connector one.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from connector.config import get_settings
from connector.main import _load_vocabulary_cache
from connector.services import consent_vocabulary as vocab

UNIT = Path(__file__).resolve().parents[1]
ROOT = UNIT.parents[1]

SAREF = "https://saref.etsi.org/saref4ener/"
DOCUMENT = {"@context": {"saref": "https://saref.etsi.org/core/"}, "@graph": []}

REGISTRY = """
vocabularies:
  - slug: saref4ener
    title: SAREF extension for energy
    iri: https://saref.etsi.org/saref4ener/
    source: https://saref.etsi.org/saref4ener/v1.2.1/saref4ener.jsonld
"""

UNFETCHABLE = """
vocabularies:
  - slug: saref4ener
    title: SAREF extension for energy
    iri: https://saref.etsi.org/saref4ener/
"""


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """Point the settings at a scratch registry and cache, and reset the caches."""

    def _configure(registry_yaml: str | None):
        cache_dir = tmp_path / "vocabularies"
        cache_dir.mkdir(exist_ok=True)
        path = tmp_path / "vocabularies.yaml"
        if registry_yaml is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(registry_yaml, encoding="utf-8")

        settings = get_settings()
        monkeypatch.setattr(settings, "vocabularies_path", str(path))
        monkeypatch.setattr(settings, "vocabulary_cache_dir", str(cache_dir))
        vocab.reset_caches()
        return settings, cache_dir

    yield _configure
    vocab.reset_caches()


# ── The fail-closed decision ──────────────────────────────────────────────────

def test_an_empty_registry_never_touches_the_network(configured):
    """`V-5` — this is what keeps `task start` offline-capable.

    No mock and no client: if the loader tried to fetch, it would attempt a real
    connection to saref.etsi.org and this test would be slow or flaky rather than
    wrong. Returning before that is the assertion.
    """
    settings, _ = configured(None)
    _load_vocabulary_cache(settings)


def test_an_already_cached_vocabulary_is_not_refetched(configured):
    """Same reasoning: reaching the network here would be a real request.

    Also the behaviour that matters operationally — a restart must not silently
    replace a cached copy, because that changes what a running catalogue's
    `dct:conformsTo` IRIs resolve to.
    """
    settings, cache_dir = configured(REGISTRY)
    (cache_dir / "saref4ener.jsonld").write_text(json.dumps(DOCUMENT), encoding="utf-8")
    _load_vocabulary_cache(settings)
    assert json.loads((cache_dir / "saref4ener.jsonld").read_text()) == DOCUMENT


@pytest.mark.rule("M-8")
def test_an_unobtainable_vocabulary_stops_startup(configured):
    """**The decision this feature turns on.**

    The entry has no `source:` and no cached copy, so it cannot be obtained by
    any means — the deterministic stand-in for an unreachable host. The loader
    must raise, not warn: booting anyway publishes `/ns/saref4ener` as a 404
    while the catalogue advertises that IRI.
    """
    settings, _ = configured(UNFETCHABLE)
    with pytest.raises(RuntimeError) as exc:
        _load_vocabulary_cache(settings)
    assert "saref4ener" in str(exc.value)


def test_the_failure_says_what_to_do_about_it(configured):
    """An operator reads this in a crash-looping container's logs.

    "Could not fetch" alone leaves them guessing between a network problem, a
    typo and a missing file. The message names the command and the directory.
    """
    settings, cache_dir = configured(UNFETCHABLE)
    with pytest.raises(RuntimeError) as exc:
        _load_vocabulary_cache(settings)
    message = str(exc.value)
    assert "task vocab:fetch" in message
    assert str(cache_dir) in message


# ── Registry resolution ───────────────────────────────────────────────────────

def test_an_explicit_path_wins_over_the_sibling_convention(configured):
    settings, _ = configured(REGISTRY)
    assert [v.slug for v in vocab.get_vocabularies().vocabularies] == ["saref4ener"]


def test_the_sibling_convention_finds_vocabularies_beside_governance(
    tmp_path, monkeypatch
):
    """`vocabularies.yaml` next to `governance.yaml`, like `sharing-offers.yaml`."""
    (tmp_path / "governance.yaml").write_text("sources: {}\n", encoding="utf-8")
    (tmp_path / "vocabularies.yaml").write_text(REGISTRY, encoding="utf-8")

    settings = get_settings()
    monkeypatch.setattr(settings, "vocabularies_path", None)
    monkeypatch.setattr(
        settings, "governance_yaml_path", str(tmp_path / "governance.yaml")
    )
    vocab.reset_caches()
    try:
        assert [v.slug for v in vocab.get_vocabularies().vocabularies] == ["saref4ener"]
    finally:
        vocab.reset_caches()


def test_no_registry_anywhere_is_an_empty_one(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "vocabularies_path", None)
    monkeypatch.setattr(
        settings, "governance_yaml_path", str(tmp_path / "governance.yaml")
    )
    vocab.reset_caches()
    try:
        assert vocab.get_vocabularies().vocabularies == []
    finally:
        vocab.reset_caches()


def test_reset_caches_drops_the_registry(configured):
    """`POST /provider/sync` calls `reset_caches`, and must pick up a registry edit.

    The profile had exactly this bug (`CON-10`): a cache the sync could not reach
    kept serving the taxonomy the process booted with. Adding a second cache
    beside it without adding it to `reset_caches` would reintroduce that.
    """
    settings, _ = configured(REGISTRY)
    assert len(vocab.get_vocabularies().vocabularies) == 1

    Path(settings.vocabularies_path).write_text("vocabularies: []\n", encoding="utf-8")
    assert len(vocab.get_vocabularies().vocabularies) == 1, "expected the cache to hold"

    vocab.reset_caches()
    assert vocab.get_vocabularies().vocabularies == []


# ── Deployment wiring ─────────────────────────────────────────────────────────
#
# Asserted against the files, like `test_container_image.py`: a mount that is
# read-only or a registry path that points at nothing are container-level
# defects no Python test would reach, and both make the startup loader fail in a
# way that reads as a vocabulary problem rather than a wiring one.

COMPOSE = [
    ("docker-compose.rec.yml", "ds-connector-rec"),
    ("docker-compose.third-party.yml", "ds-connector-third-party"),
]


def _service(compose_file: str, service: str) -> dict:
    doc = yaml.safe_load((ROOT / compose_file).read_text(encoding="utf-8"))
    return doc["services"][service]


def _host_path_for(service_def: dict, container_dir: str) -> Path:
    """The repo path mounted at ``container_dir``, read out of the mount itself.

    Derived rather than hardcoded, and that is the point of the test: this
    asserted ``services/connector/governance/`` until the participant rename
    replaced that directory with one per participant (``governance-rec``,
    ``governance-grid-operator``). Hardcoding the host side made the check a
    restatement of a layout instead of a check of the wiring, so it went stale
    the moment the layout moved.
    """
    for mount in service_def.get("volumes", []):
        host, _, rest = str(mount).partition(":")
        target = rest.split(":")[0]
        if target == container_dir:
            return ROOT / host.lstrip("./")
    raise AssertionError(f"no volume mounted at {container_dir}: {service_def.get('volumes')}")


@pytest.mark.parametrize("compose_file,service", COMPOSE)
def test_compose_points_at_a_registry_that_exists(compose_file, service):
    definition = _service(compose_file, service)
    declared = definition["environment"]["CONNECTOR_VOCABULARIES_PATH"]
    assert declared.startswith("/governance/"), declared
    # The container path maps to a real file in the repo — mounted, not baked.
    host_dir = _host_path_for(definition, "/governance")
    assert (host_dir / Path(declared).name).is_file(), (
        f"{declared} is mounted from {host_dir}, which has no {Path(declared).name}"
    )


@pytest.mark.parametrize("compose_file,service", COMPOSE)
def test_the_cache_mount_is_writable(compose_file, service):
    """The startup loader writes here. `/governance` is `:ro` and must stay so.

    A cache under the read-only governance mount would crash the container on a
    permission error while reporting a fetch failure — the wrong diagnosis, in
    the log line an operator acts on.
    """
    svc = _service(compose_file, service)
    cache_dir = svc["environment"]["CONNECTOR_VOCABULARY_CACHE_DIR"]

    mounts = {m.split(":")[1]: m for m in svc["volumes"]}
    assert cache_dir in mounts, f"{cache_dir} is not mounted"
    assert not mounts[cache_dir].endswith(":ro"), (
        "the vocabulary cache must be writable"
    )
    assert mounts["/governance"].endswith(":ro"), "governance must stay read-only"


@pytest.mark.parametrize("compose_file,service", COMPOSE)
def test_the_cache_is_not_inside_the_read_only_mount(compose_file, service):
    env = _service(compose_file, service)["environment"]
    assert not env["CONNECTOR_VOCABULARY_CACHE_DIR"].startswith("/governance/")


@pytest.mark.parametrize("compose_file,service", COMPOSE)
def test_the_cache_lives_under_data(compose_file, service):
    """ADR-0008: fetched and generated material lives under `./data/`.

    This shipped as `services/connector/governance-rec/vocab-cache`, which was wrong
    twice over: it put fetched state inside a directory of committed
    configuration, and it added one more place to look for scratch data. The rule
    exists so that second list stays short — scattered cache directories arrive
    one reasonable-looking exception at a time.

    A test rather than a comment, because the instinct when adding a cache is to
    put it next to whatever it caches.
    """
    svc = _service(compose_file, service)
    host_paths = [m.split(":")[0] for m in svc["volumes"]]
    assert "./data/vocabularies" in host_paths, host_paths
    assert svc["environment"]["CONNECTOR_VOCABULARY_CACHE_DIR"].startswith("/data/")


def test_the_default_cache_dir_is_under_data():
    """The default matters more than the compose value — it is what a bare run uses."""
    from connector.config import Settings

    assert Settings.model_fields["vocabulary_cache_dir"].default.startswith("data/")


def test_the_registry_is_not_under_data():
    """Committed configuration is not cache, and must not be swept into `data/`.

    `data/` is gitignored in full, so a registry that lived there would vanish
    from a fresh clone and the connector would silently publish nothing.
    """
    from connector.config import Settings

    default = Settings.model_fields["vocabularies_path"].default
    assert default is None, "the registry resolves beside governance.yaml, not in data/"


@pytest.mark.rule("M-6", "M-8")
def test_no_shipped_vocabulary_needs_the_network_at_boot():
    """`V-5`, asserted rather than trusted.

    **This used to require the shipped registries to be empty**, and that was the
    right assertion while `source:` was the only way to register anything: the
    loader fetches what it finds, so one committed entry made every `task start`,
    every CI run and every fresh clone depend on an external host at boot.

    `definition:` removed the reason without removing the risk. An entry the
    participant ships needs no fetch, so the seam can be exercised offline — but
    a `source:` added beside it still reintroduces the boot dependency, and now
    it would arrive next to entries that look fine. So the assertion moved to the
    property that was always the point: **nothing shipped here is fetched.**
    """
    registries = sorted(UNIT.glob("governance-*/vocabularies.yaml"))
    assert registries, f"no governance-*/vocabularies.yaml under {UNIT}"
    for path in registries:
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in registry["vocabularies"] or []:
            assert not entry.get("source"), (
                f"{path.relative_to(UNIT)} registers {entry['slug']!r} with a "
                "`source:`, so a default install fetches it at startup and fails "
                "if it cannot. Ship the document with `definition:` instead."
            )
            assert entry.get("definition"), (
                f"{path.relative_to(UNIT)} registers {entry['slug']!r} with "
                "neither `source:` nor `definition:` — startup cannot obtain it "
                "and will refuse to boot (V-4)."
            )


@pytest.mark.rule("M-6")
def test_no_shipped_vocabulary_imposes_a_real_world_model():
    """`M-6` — the platform mandates no payload model.

    A fixture exercising the seam is not the platform imposing a model, and the
    difference is visible in the IRI: these are `*.dataspaces.localhost`, the dev
    fixture namespace, the same rule the rest of this repository follows. An
    entry naming a real published ontology would be a deployment's choice
    committed as everyone's default.
    """
    for path in sorted(UNIT.glob("governance-*/vocabularies.yaml")):
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in registry["vocabularies"] or []:
            assert ".dataspaces.localhost" in entry["iri"], (
                f"{path.relative_to(UNIT)} ships {entry['iri']!r}. A real model is "
                "a deployment overlay, not a committed fixture (M-6)."
            )
