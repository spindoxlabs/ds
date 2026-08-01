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
        CacheStatus(v.slug, cache_path(cache_dir, v).is_file(), cache_path(cache_dir, v))
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


def fetch_one(
    cache_dir: Path | str,
    vocab: Vocabulary,
    *,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Path:
    """Retrieve *vocab* into the cache and return the path written."""
    if not vocab.source:
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' has no source and no cached copy. Supply "
            f"{cache_path(cache_dir, vocab)} manually, or add a 'source:' URL."
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

    if len(body) > MAX_BYTES:
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' is {len(body)} bytes, over the "
            f"{MAX_BYTES}-byte limit — that is not a vocabulary document"
        )

    # Parsed before it is written, so a login page or an error document served
    # with a 200 is refused here rather than cached and served from `/ns/{slug}`
    # as though it were SAREF. A cache is only worth having if what it holds was
    # checked once.
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VocabularyFetchError(
            f"vocabulary '{vocab.slug}' from {vocab.source} is not JSON-LD: {exc}. "
            "Only 'format: jsonld' is supported — convert the source and register "
            "the result."
        ) from exc

    path = cache_path(cache_dir, vocab)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
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
    """
    written: list[Path] = []
    failures: list[str] = []

    for vocab in registry.vocabularies:
        path = cache_path(cache_dir, vocab)
        if path.is_file() and not refresh:
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
