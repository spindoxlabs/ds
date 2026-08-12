"""`/ns/*` — the semantic vocabulary surface, and the sibling routes it must not break.

Rulebook `M-11` (a vocabulary hub that browses), `M-8` (published unauthenticated).

The test carrying the most weight is
`test_the_catch_all_does_not_shadow_the_siblings`.
`/ns/{slug}` is a catch-all on a prefix that already had two public routes, and
FastAPI resolves in registration order — so declaring it too early makes
`/ns/policy` resolve into the vocabulary handler, find no vocabulary slugged
"policy", and 404. Every test of the *new* route would still pass.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from connector.config import get_settings
from connector.main import create_app
from connector.services import consent_vocabulary as vocab

SAREF = "https://saref.etsi.org/saref4ener/"
DOCUMENT = {"@context": {"saref": "https://saref.etsi.org/core/"}, "@graph": []}

REGISTRY = """
vocabularies:
  - slug: saref4ener
    title: SAREF extension for energy
    version: "1.2.1"
    iri: https://saref.etsi.org/saref4ener/
    source: https://saref.etsi.org/saref4ener/v1.2.1/saref4ener.jsonld
  - slug: cim
    title: IEC CIM
    iri: https://cim.ucaiug.io/ns#
"""


@pytest_asyncio.fixture
async def ns_client(tmp_path, monkeypatch):
    """A client whose registry has two entries and whose cache holds one.

    One cached and one not, because "registered but no local copy" is a real
    deployment state with its own answer, and a fixture that cached everything
    would never reach it.
    """
    registry_file = tmp_path / "vocabularies.yaml"
    registry_file.write_text(REGISTRY, encoding="utf-8")

    cache_dir = tmp_path / "vocabularies"
    cache_dir.mkdir()
    (cache_dir / "saref4ener.jsonld").write_text(json.dumps(DOCUMENT), encoding="utf-8")

    settings = get_settings()
    monkeypatch.setattr(settings, "vocabularies_path", str(registry_file))
    monkeypatch.setattr(settings, "vocabulary_cache_dir", str(cache_dir))
    vocab.reset_caches()

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, cache_dir

    vocab.reset_caches()


# ── The trap ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_catch_all_does_not_shadow_the_siblings(ns_client):
    """`/ns/policy` and `/ns/sharing-offers` must still be themselves.

    Registration order is the only thing keeping this true, and nothing about
    reading `namespace.py` top to bottom makes that obvious. If this fails, the
    `@router.get("/ns/{slug}")` declaration moved above them.
    """
    client, _ = ns_client

    policy = await client.get("/ns/policy")
    assert policy.status_code == 200
    assert "@graph" in policy.json(), "resolved into the vocabulary handler"

    offers = await client.get("/ns/sharing-offers")
    assert offers.status_code == 200
    assert isinstance(offers.json(), list)

    vocabularies = await client.get("/ns/vocabularies")
    assert vocabularies.status_code == 200
    assert {v["slug"] for v in vocabularies.json()} == {"saref4ener", "cim"}


# ── Browse ────────────────────────────────────────────────────────────────────

@pytest.mark.rule("M-11")
@pytest.mark.asyncio
async def test_the_index_lists_every_surface(ns_client):
    client, _ = ns_client
    body = (await client.get("/ns")).json()
    assert body["policy"]["href"] == "/ns/policy"
    assert body["sharingOffers"]["href"] == "/ns/sharing-offers"
    assert {v["slug"] for v in body["vocabularies"]} == {"saref4ener", "cim"}


@pytest.mark.rule("M-11")
@pytest.mark.asyncio
async def test_the_index_reports_which_copies_are_missing(ns_client):
    """An uncached entry is shown, not hidden.

    A registered vocabulary with no local copy is a deployment problem, and an
    operator should be able to see it from outside the container.
    """
    client, _ = ns_client
    body = (await client.get("/ns")).json()
    cached = {v["slug"]: v["cached"] for v in body["vocabularies"]}
    assert cached == {"saref4ener": True, "cim": False}


@pytest.mark.rule("M-8", "M-11")
@pytest.mark.asyncio
async def test_the_registry_projection_carries_the_iri(ns_client):
    """The IRI is the identity — it is what a `dcat.conforms_to` names."""
    client, _ = ns_client
    entries = {v["slug"]: v for v in (await client.get("/ns/vocabularies")).json()}
    assert entries["saref4ener"]["iri"] == SAREF
    assert entries["saref4ener"]["version"] == "1.2.1"


# ── Retrieval ─────────────────────────────────────────────────────────────────

@pytest.mark.rule("M-8", "M-11")
@pytest.mark.asyncio
async def test_a_cached_vocabulary_is_served_as_jsonld(ns_client):
    client, _ = ns_client
    response = await client.get("/ns/saref4ener")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/ld+json")
    assert response.json() == DOCUMENT


@pytest.mark.rule("M-8")
@pytest.mark.asyncio
async def test_an_uncached_vocabulary_404s_with_its_canonical_iri(ns_client):
    """Not a 500, and not silence.

    The registry is a local convenience; the IRI is the identity. "Not here, and
    here is where it lives" is an answer a caller can act on.
    """
    client, _ = ns_client
    response = await client.get("/ns/cim")
    assert response.status_code == 404
    assert response.json()["detail"]["iri"] == "https://cim.ucaiug.io/ns#"


@pytest.mark.rule("M-8")
@pytest.mark.asyncio
async def test_an_unregistered_slug_404s(ns_client):
    client, _ = ns_client
    assert (await client.get("/ns/nonesuch")).status_code == 404


@pytest.mark.asyncio
async def test_a_corrupt_cached_copy_is_a_500_not_a_404(ns_client):
    """A 404 would say "we do not have it", which is false and misleading.

    The file is there; this deployment wrote something unreadable into its own
    cache. That is a server fault and must read as one.
    """
    client, cache_dir = ns_client
    (cache_dir / "saref4ener.jsonld").write_text("{ not json", encoding="utf-8")
    assert (await client.get("/ns/saref4ener")).status_code == 500


# ── Perimeter ─────────────────────────────────────────────────────────────────

@pytest.mark.rule("M-8", "M-11")
@pytest.mark.asyncio
async def test_every_surface_is_public(ns_client):
    """`M-8`: vocabularies are published unauthenticated.

    Asserted rather than assumed, because the reflex on this codebase is to add
    `Depends(require_permission(...))` to a new route — and here that would be
    wrong. An onboarding wizard renders these before anyone has an identity, and
    a vocabulary is a public standard in the first place.
    """
    client, _ = ns_client
    for path in (
        "/ns",
        "/ns/vocabularies",
        "/ns/policy",
        "/ns/sharing-offers",
        "/ns/saref4ener",
    ):
        assert (await client.get(path)).status_code == 200, path


@pytest.mark.asyncio
async def test_no_registry_is_an_empty_surface_not_an_error(tmp_path, monkeypatch):
    """`V-5` — the platform ships nothing registered, and must still serve `/ns`."""
    settings = get_settings()
    monkeypatch.setattr(settings, "vocabularies_path", str(tmp_path / "absent.yaml"))
    monkeypatch.setattr(settings, "vocabulary_cache_dir", str(tmp_path / "cache"))
    vocab.reset_caches()

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        body = (await client.get("/ns")).json()
        assert body["vocabularies"] == []
        assert body["policy"]["href"] == "/ns/policy"
    vocab.reset_caches()
