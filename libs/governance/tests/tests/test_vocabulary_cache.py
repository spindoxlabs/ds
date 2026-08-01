"""Filling and reading the vocabulary cache.

The interesting cases are all failures, and one of them is the reason the module
parses before it writes: a source that answers 200 with a login page would
otherwise be cached and served from `/ns/saref4ener` as though it were SAREF.
"""
from __future__ import annotations

import json

import httpx
import pytest

from ds.governance.vocabularies import Vocabulary, VocabularyRegistry
from ds.governance.vocabulary_cache import (
    MAX_BYTES,
    VocabularyFetchError,
    cache_path,
    ensure_cached,
    fetch_one,
    read_cached,
    status,
)

SAREF = "https://saref.etsi.org/saref4ener/"
SOURCE = "https://saref.etsi.org/saref4ener/v1.2.1/saref4ener.jsonld"
DOCUMENT = {"@context": {"saref": "https://saref.etsi.org/core/"}, "@graph": []}


def vocab(**overrides) -> Vocabulary:
    base = {"slug": "saref4ener", "title": "SAREF4ENER", "iri": SAREF, "source": SOURCE}
    base.update(overrides)
    return Vocabulary(**base)


def client_returning(*responses: httpx.Response) -> httpx.Client:
    it = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return next(it)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ── Fetching ──────────────────────────────────────────────────────────────────

def test_a_fetch_writes_the_document(tmp_path):
    with client_returning(httpx.Response(200, json=DOCUMENT)) as client:
        path = fetch_one(tmp_path, vocab(), client=client)
    assert path == tmp_path / "saref4ener.jsonld"
    assert json.loads(path.read_text()) == DOCUMENT


def test_a_non_json_body_is_refused_rather_than_cached(tmp_path):
    """The case this ordering exists for.

    A captive portal, an SSO redirect landing page or an HTML error document all
    answer 200. Writing first and parsing never would leave `/ns/saref4ener`
    serving that page under `application/ld+json`.
    """
    html = "<html><body>Please sign in</body></html>"
    with client_returning(httpx.Response(200, text=html)) as client:
        with pytest.raises(VocabularyFetchError) as exc:
            fetch_one(tmp_path, vocab(), client=client)
    assert "not JSON-LD" in str(exc.value)
    assert not (tmp_path / "saref4ener.jsonld").exists()


def test_an_http_error_is_reported_with_the_source(tmp_path):
    with client_returning(httpx.Response(404)) as client:
        with pytest.raises(VocabularyFetchError) as exc:
            fetch_one(tmp_path, vocab(), client=client)
    assert SOURCE in str(exc.value)


def test_an_oversized_body_is_refused(tmp_path):
    big = json.dumps({"@graph": ["x" * MAX_BYTES]})
    with client_returning(httpx.Response(200, text=big)) as client:
        with pytest.raises(VocabularyFetchError) as exc:
            fetch_one(tmp_path, vocab(), client=client)
    assert "not a vocabulary document" in str(exc.value)


def test_no_source_and_no_cached_copy_names_the_path_to_supply(tmp_path):
    """A vocabulary behind a login is legitimate — the operator supplies the file.

    The error has to say *where*, or the operator is guessing at a filename.
    """
    with pytest.raises(VocabularyFetchError) as exc:
        fetch_one(tmp_path, vocab(source=None))
    assert str(tmp_path / "saref4ener.jsonld") in str(exc.value)


# ── ensure_cached ─────────────────────────────────────────────────────────────

def test_an_already_cached_vocabulary_is_not_refetched(tmp_path):
    (tmp_path / "saref4ener.jsonld").write_text(json.dumps(DOCUMENT))
    registry = VocabularyRegistry(vocabularies=[vocab()])
    # No client: a fetch attempt would raise on the real network or on `next()`.
    assert ensure_cached(tmp_path, registry) == []


def test_refresh_refetches_an_already_cached_vocabulary(tmp_path):
    (tmp_path / "saref4ener.jsonld").write_text(json.dumps({"stale": True}))
    registry = VocabularyRegistry(vocabularies=[vocab()])
    with client_returning(httpx.Response(200, json=DOCUMENT)) as client:
        written = ensure_cached(tmp_path, registry, refresh=True, client=client)
    assert len(written) == 1
    assert json.loads((tmp_path / "saref4ener.jsonld").read_text()) == DOCUMENT


def test_an_empty_registry_needs_no_network(tmp_path):
    """`V-5` — the shipped registry is empty, so `task start` never reaches out."""
    assert ensure_cached(tmp_path, VocabularyRegistry()) == []


def test_every_failure_is_reported_together(tmp_path):
    """One restart, one complete list — the sync's rule, for the same reason.

    An operator registering three vocabularies behind a proxy should not have to
    fix them one boot at a time.
    """
    registry = VocabularyRegistry(
        vocabularies=[
            vocab(),
            vocab(slug="cim", iri="https://cim.ucaiug.io/ns#", source="https://cim.example/x.jsonld"),
            vocab(slug="cosem", iri="https://example.test/cosem#", source=None),
        ]
    )
    with client_returning(httpx.Response(500), httpx.Response(503)) as client:
        with pytest.raises(VocabularyFetchError) as exc:
            ensure_cached(tmp_path, registry, client=client)
    message = str(exc.value)
    assert "3 vocabularies could not be cached" in message
    for slug in ("saref4ener", "cim", "cosem"):
        assert slug in message


# ── Reading ───────────────────────────────────────────────────────────────────

def test_read_cached_returns_none_when_absent(tmp_path):
    """A missing copy is a 404 with the canonical IRI — a useful answer."""
    assert read_cached(tmp_path, vocab()) is None


def test_read_cached_raises_on_a_corrupt_copy(tmp_path):
    """Not `None`. A corrupt copy means the cache is lying about what it holds."""
    (tmp_path / "saref4ener.jsonld").write_text("{ not json")
    with pytest.raises(VocabularyFetchError):
        read_cached(tmp_path, vocab())


def test_status_reports_what_is_cached(tmp_path):
    (tmp_path / "saref4ener.jsonld").write_text(json.dumps(DOCUMENT))
    registry = VocabularyRegistry(
        vocabularies=[vocab(), vocab(slug="cim", iri="https://cim.ucaiug.io/ns#")]
    )
    got = {s.slug: s.cached for s in status(tmp_path, registry)}
    assert got == {"saref4ener": True, "cim": False}


def test_the_cache_path_stays_inside_the_cache_directory(tmp_path):
    """Belt and braces over the slug validator, because a public route reads this."""
    assert cache_path(tmp_path, vocab()).parent == tmp_path
