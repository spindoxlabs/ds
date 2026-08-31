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
            vocab(
                slug="cim",
                iri="https://cim.ucaiug.io/ns#",
                source="https://cim.example/x.jsonld",
            ),
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


# ── A definition this participant ships ───────────────────────────
#
# The registry could previously only *mirror* somebody else's vocabulary:
# `source` must be an absolute http(s) URI, so a participant that defines its own
# model for its own response shape had no way to register it. That is the common
# case, not the exotic one — a dataset's payload model is a fact about what a
# producer's data plane returns.


def _registry_with_definition(tmp_path, body: str = None):
    registry_dir = tmp_path / "governance"
    registry_dir.mkdir()
    (registry_dir / "own.jsonld").write_text(
        body if body is not None else json.dumps(DOCUMENT), encoding="utf-8"
    )
    (registry_dir / "vocabularies.yaml").write_text(
        "vocabularies:\n"
        "  - slug: own\n"
        "    title: Our own model\n"
        "    iri: https://rec.dataspaces.localhost/ns/own\n"
        "    definition: own.jsonld\n",
        encoding="utf-8",
    )
    return registry_dir


def test_a_shipped_definition_is_published_without_a_network(tmp_path):
    """No client is passed, so reaching the network would be a real request.

    Returning without one is the assertion — this is what keeps `V-5` true for a
    deployment that has entries registered: `task start` stays offline-capable.
    """
    from ds.governance.vocabularies import load_vocabularies

    registry_dir = _registry_with_definition(tmp_path)
    registry = load_vocabularies(registry_dir / "vocabularies.yaml")

    ensure_cached(tmp_path / "cache", registry)

    assert read_cached(tmp_path / "cache", registry.vocabularies[0]) == DOCUMENT


def test_a_shipped_definition_tracks_its_file_across_restarts(tmp_path):
    """The asymmetry with `source`, and it is deliberate.

    A fetched copy is a snapshot of a document somebody else controls, so a
    restart must not silently replace it. A definition is *this deployment's own
    committed file* — it changes only by a reviewed commit, and a cache that
    ignored the change would serve a version of the participant's vocabulary that
    no longer exists in the repository.
    """
    from ds.governance.vocabularies import load_vocabularies

    registry_dir = _registry_with_definition(tmp_path)
    path = registry_dir / "vocabularies.yaml"
    ensure_cached(tmp_path / "cache", load_vocabularies(path))

    edited = {"@context": {"own": "https://rec.dataspaces.localhost/ns/own#"}}
    (registry_dir / "own.jsonld").write_text(json.dumps(edited), encoding="utf-8")
    ensure_cached(tmp_path / "cache", load_vocabularies(path))

    registry = load_vocabularies(path)
    assert read_cached(tmp_path / "cache", registry.vocabularies[0]) == edited


def test_a_definition_that_is_not_jsonld_is_refused(tmp_path):
    """Same rule as a fetched body. A half-edited local file reaching
    `/ns/{slug}` as though it were a vocabulary is the failure this prevents."""
    from ds.governance.vocabularies import load_vocabularies

    registry_dir = _registry_with_definition(tmp_path, body="not json at all")
    registry = load_vocabularies(registry_dir / "vocabularies.yaml")

    with pytest.raises(VocabularyFetchError, match="not JSON-LD"):
        ensure_cached(tmp_path / "cache", registry)


# ── A cache that is already right does not need to be writable (TASK-10) ──────
#
# `ensure_cached` republishes a `definition:` on every start, which used to mean
# an unconditional write — so every start required a writable cache directory.
# Both documented ways of supplying a cache make it un-writable: the chart's
# preferred `vocabularies.cache.configMap` is a **read-only** ConfigMap volume,
# and the compose mount is shared with the host so `task vocab:fetch` can fill it,
# which leaves the files owned by whoever wrote them and not by uid 10001. The
# connector exited 3 on `PermissionError` in both cases, over bytes that were
# already correct.


def test_republishing_an_unchanged_definition_writes_nothing(tmp_path, monkeypatch):
    """The write is skipped, not merely tolerated.

    Asserted by making any write fail: if `_write_document` still opened the file
    for writing, this raises. Checking the mtime instead would pass on a
    write-identical-bytes implementation, which is the thing that broke.
    """
    from ds.governance import vocabulary_cache
    from ds.governance.vocabularies import load_vocabularies

    registry_dir = _registry_with_definition(tmp_path)
    path = registry_dir / "vocabularies.yaml"
    cache = tmp_path / "cache"
    ensure_cached(cache, load_vocabularies(path))

    def refuse(*args, **kwargs):
        raise AssertionError("wrote to a cache that already held the right bytes")

    monkeypatch.setattr(vocabulary_cache.Path, "write_text", refuse)

    ensure_cached(cache, load_vocabularies(path))

    assert read_cached(cache, load_vocabularies(path).vocabularies[0]) == DOCUMENT


def test_a_read_only_cache_still_starts_when_it_is_already_correct(tmp_path):
    """The ConfigMap case, reproduced with the filesystem rather than mocks.

    A ConfigMap volume mounts its files read-only inside a read-only directory,
    so **both** are locked down here — locking only the directory would still let
    an unconditional `write_text` reopen the existing file and pass.
    """
    import os
    import stat

    from ds.governance.vocabularies import load_vocabularies

    registry_dir = _registry_with_definition(tmp_path)
    path = registry_dir / "vocabularies.yaml"
    cache = tmp_path / "cache"
    ensure_cached(cache, load_vocabularies(path))

    cached = cache_path(cache, load_vocabularies(path).vocabularies[0])
    os.chmod(cached, stat.S_IRUSR)
    os.chmod(cache, stat.S_IRUSR | stat.S_IXUSR)
    try:
        ensure_cached(cache, load_vocabularies(path))  # must not raise
    finally:
        os.chmod(cache, stat.S_IRWXU)
        os.chmod(cached, stat.S_IRUSR | stat.S_IWUSR)


def test_a_changed_definition_is_still_republished_over_a_file_it_does_not_own(
    tmp_path,
):
    """The property the skip must not cost: the committed file still wins.

    Replacement goes through a temporary file and `os.replace`, so it needs write
    permission on the **directory** rather than on the existing file — which is
    what lets the container replace a copy `task vocab:fetch` wrote from the host.
    """
    import os
    import stat

    from ds.governance.vocabularies import load_vocabularies

    registry_dir = _registry_with_definition(tmp_path)
    path = registry_dir / "vocabularies.yaml"
    cache = tmp_path / "cache"
    ensure_cached(cache, load_vocabularies(path))

    cached = cache_path(cache, load_vocabularies(path).vocabularies[0])
    os.chmod(cached, stat.S_IRUSR)  # read-only file, writable directory

    edited = {"@context": {"own": "https://rec.dataspaces.localhost/ns/own#"}}
    (registry_dir / "own.jsonld").write_text(json.dumps(edited), encoding="utf-8")
    ensure_cached(cache, load_vocabularies(path))

    assert read_cached(cache, load_vocabularies(path).vocabularies[0]) == edited


def test_no_temporary_file_is_left_behind(tmp_path):
    """A `.own.jsonld.<pid>.tmp` surviving in the cache would be served by
    nothing but would make `status` and any directory listing lie."""
    from ds.governance.vocabularies import load_vocabularies

    registry_dir = _registry_with_definition(tmp_path)
    cache = tmp_path / "cache"
    ensure_cached(cache, load_vocabularies(registry_dir / "vocabularies.yaml"))

    assert [p.name for p in sorted(cache.iterdir())] == ["own.jsonld"]
