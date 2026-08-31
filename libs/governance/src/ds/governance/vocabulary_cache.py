"""Filling and reading the local vocabulary cache.

Separate from :mod:`vocabularies`, which describes the registry and opens no
sockets. This is the one module that fetches, and keeping it apart is what lets
the request path import the registry without importing a fetcher.

**Nothing on a request path calls into here except** :func:`read_cached`, which
only ever opens a file. A public unauthenticated ``/ns/*`` route that fetched on
demand would proxy an operator-configured URL and tie its availability to a third
party's uptime; the fetch is an explicit step (``task vocab:fetch``) or a startup
one, and both fail loudly rather than degrading a route.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from .vocabularies import Vocabulary, VocabularyRegistry

logger = logging.getLogger(__name__)

#: A vocabulary document is a definition, not a dataset. Ten megabytes is far
#: past any real one and still small enough that a redirect to something else
#: cannot fill a disk before it is refused.
MAX_BYTES = 10 * 1024 * 1024

DEFAULT_TIMEOUT = 30.0


class VocabularyFetchError(RuntimeError):
    """A registered vocabulary could not be obtained.

    Raised rather than logged because both callers must fail: ``vocab:fetch``
    reports it, and the connector's startup refuses to boot on it. A connector
    that starts while serving ``/ns/{slug}`` as a 404 has published a vocabulary
    reference it cannot honour — and the catalogue it syncs names that IRI.
    """


@dataclass(frozen=True)
class CacheStatus:
    slug: str
    cached: bool
    path: Path


def cache_path(cache_dir: Path | str, vocab: Vocabulary) -> Path:
    """Where *vocab*'s local copy lives.

    ``Vocabulary.slug`` is validated to lowercase alphanumerics and hyphens, so
    the join cannot escape *cache_dir*. That validator is load-bearing here, and
    the assertion below says so rather than trusting it silently — this path is
    built from a config file and read by a public route.
    """
    directory = Path(cache_dir)
    path = directory / vocab.cache_filename
    resolved_parent = path.resolve().parent
    if resolved_parent != directory.resolve():
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' resolves outside the cache directory"
        )
    return path


def status(cache_dir: Path | str, registry: VocabularyRegistry) -> list[CacheStatus]:
    return [
        CacheStatus(
            v.slug, cache_path(cache_dir, v).is_file(), cache_path(cache_dir, v)
        )
        for v in registry.vocabularies
    ]


def read_cached(cache_dir: Path | str, vocab: Vocabulary) -> dict | None:
    """The cached JSON-LD document, or ``None`` if there is no local copy.

    ``None`` rather than an exception: a missing copy is a 404 with the canonical
    IRI in the body, which is a useful answer. A *corrupt* copy is not — it means
    the cache is lying about having the vocabulary — so that raises.
    """
    path = cache_path(cache_dir, vocab)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VocabularyFetchError(
            f"cached vocabulary '{vocab.slug}' at {path} is not readable JSON: {exc}"
        ) from exc


def _write_document(
    cache_dir: Path | str, vocab: Vocabulary, body: bytes, origin: str
) -> Path:
    """Validate and write one vocabulary document into the cache.

    Parsed **before** it is written, wherever it came from, so a login page
    served with a 200 or a half-edited local file is refused here rather than
    cached and served from ``/ns/{slug}`` as though it were a vocabulary. A cache
    is only worth having if what it holds was checked once.
    """
    if len(body) > MAX_BYTES:
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' is {len(body)} bytes, over the "
            f"{MAX_BYTES}-byte limit — that is not a vocabulary document"
        )
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' from {origin} is not JSON-LD: {exc}. "
            "Only 'format: jsonld' is supported — convert the source and register "
            "the result."
        ) from exc

    path = cache_path(cache_dir, vocab)
    serialised = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )

    # **A write that would change nothing is not performed**, and this is a
    # correctness fix rather than an optimisation. A `definition:` is republished
    # on *every* start by design (see `ensure_cached`), so the old unconditional
    # write demanded a writable cache on every start — and the two places the
    # cache is legitimately not writable are both documented as preferred:
    #
    #   * `helm/charts/ds-connector/values.yaml` calls `vocabularies.cache.configMap`
    #     "the one to prefer", and a ConfigMap volume is **read-only**;
    #   * the compose mount is shared with the host so `task vocab:fetch` can fill
    #     it from outside, and whoever wrote a file there owns it — not uid 10001.
    #
    # Both produced `PermissionError` and a container that would not start, on a
    # cache already holding exactly the right bytes. Comparing first is what makes
    # "always republish" mean *the committed file wins* rather than *the directory
    # must be writable*.
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == serialised:
                return path
        except OSError:
            pass  # unreadable — fall through and try to replace it

    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace through a temporary file in the same directory: `os.replace` is
    # atomic, so a concurrent `/ns/{slug}` read never sees a half-written
    # document, and it needs write permission on the **directory** rather than on
    # the existing file — which is what lets the host and the container take turns
    # filling a shared cache neither of them owns outright.
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(serialised, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return path


def _copy_definition(cache_dir: Path | str, vocab: Vocabulary) -> Path:
    """Publish a definition this participant ships, from committed configuration.

    No socket: the participant *is* the publisher, so there is nothing to fetch.
    `load_vocabularies` has already resolved the path and refused one that does
    not exist or escapes the registry's directory, so by here it is a readable
    file inside a config directory.
    """
    source = Path(vocab.definition)
    written = _write_document(cache_dir, vocab, source.read_bytes(), str(source))
    logger.info("Published vocabulary '%s' from %s", vocab.slug, source)
    return written


def fetch_one(
    cache_dir: Path | str,
    vocab: Vocabulary,
    *,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Path:
    """Retrieve *vocab* into the cache and return the path written."""
    if vocab.definition:
        return _copy_definition(cache_dir, vocab)

    if not vocab.source:
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' has no source, no definition and no cached "
            f"copy. Supply {cache_path(cache_dir, vocab)} manually, add a 'source:' "
            f"URL to mirror somebody else's vocabulary, or a 'definition:' file to "
            f"publish this participant's own."
        )

    owned = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        response = http.get(vocab.source, headers={"Accept": "application/ld+json"})
        response.raise_for_status()
        body = response.content
    except httpx.HTTPError as exc:
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' could not be fetched from {vocab.source}: {exc}"
        ) from exc
    finally:
        if owned:
            http.close()

    path = _write_document(cache_dir, vocab, body, vocab.source)
    logger.info("Cached vocabulary '%s' from %s", vocab.slug, vocab.source)
    return path


def ensure_cached(
    cache_dir: Path | str,
    registry: VocabularyRegistry,
    *,
    refresh: bool = False,
    client: httpx.Client | None = None,
) -> list[Path]:
    """Fetch every registered vocabulary that has no local copy.

    **Every failure is collected and reported together**, the same rule the
    governance sync follows: an operator registering four vocabularies behind a
    proxy should be told about all four, not made to fix them one restart at a
    time.

    With *refresh*, re-fetches entries that are already cached — the
    ``vocab:fetch --refresh`` path. Startup never refreshes: a cached copy is
    what the deployment is serving, and silently replacing it on a restart would
    change what a running catalogue's IRIs resolve to.

    **A shipped definition is always re-published, refresh or not**, and the
    asymmetry is deliberate. A fetched copy is a snapshot of a document somebody
    else controls, so replacing it on a restart changes what a running catalogue
    resolves to behind the operator's back — that is what `refresh` exists to
    make deliberate. A `definition:` is *this deployment's own committed file*:
    it changes only by a reviewed commit, the commit is the deliberate act, and a
    cache that ignored it would serve a version of the participant's vocabulary
    that no longer exists in the repository.
    """
    written: list[Path] = []
    failures: list[str] = []

    for vocab in registry.vocabularies:
        path = cache_path(cache_dir, vocab)
        if path.is_file() and not refresh and not vocab.definition:
            continue
        try:
            written.append(fetch_one(cache_dir, vocab, client=client))
        except VocabularyFetchError as exc:
            failures.append(str(exc))

    if failures:
        raise VocabularyFetchError(
            f"{len(failures)} vocabular{'y' if len(failures) == 1 else 'ies'} "
            "could not be cached:\n  - " + "\n  - ".join(failures)
        )
    return written
