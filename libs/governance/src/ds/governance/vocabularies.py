"""The semantic vocabulary registry — slug, canonical IRI, local copy.

A dataset declares its payload semantic model as `dcat.conforms_to`, a **URI**
(the canonical schema's word). This registry is what turns that URI into
something a person or a machine can actually read: a title, a version, and a
locally cached JSON-LD definition served from ``/ns/{slug}``.

Three things this deliberately is not.

**It is not a fetcher.** Nothing here opens a socket. The registry describes
where a vocabulary comes from; filling the cache is a separate, explicit step
(``task vocab:fetch``, or the connector's startup load). A public unauthenticated
``/ns/*`` route that fetched on demand would proxy an operator-configured URL and
tie its availability to a third party's uptime.

**It is not a converter.** ``format: jsonld`` is the only accepted value. ds
ships no RDF toolchain, so a Turtle source is refused by name rather than
half-parsed. A deployment needing SAREF's Turtle converts it once, out of band,
and registers the result. See `.agents/semantic-vocabulary.plan.md` decision
`V-3`.

**It is not authority over the vocabulary.** The IRI is. A registry entry is a
local convenience — a cached copy and an address to serve it from — and deleting
one changes nothing about what a dataset conforms to.

Editing is a code change, like every other vocabulary in this platform
(rulebook `data-models.md` §5.1). That is what lets this close the browse half of
`M-11` without touching §5.1 or `M-12`.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

#: The only serialisation this platform stores or serves (`V-3`).
JSONLD = "jsonld"

#: A slug is a URL path segment on a public route, so it is constrained rather
#: than trusted: lowercase alphanumerics and hyphens. This is what keeps a
#: registry entry from reaching outside the cache directory when it becomes a
#: filename — see `Vocabulary.cache_filename`.
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class VocabularyError(ValueError):
    """A vocabulary registry that cannot be served as written."""


def _is_absolute_http_uri(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class Vocabulary(BaseModel):
    """One semantic vocabulary this deployment publishes a local copy of."""

    model_config = ConfigDict(extra="forbid")

    #: The ``/ns/{slug}`` path segment, and the cache filename stem.
    slug: str
    title: str
    #: Free text on purpose. Vocabularies version as ``1.2.1``, ``v3``,
    #: ``2024-11`` and ``3.0.0-rc1``; imposing a scheme here would refuse real
    #: published versions to gain nothing — nothing compares these.
    version: str = ""
    #: **The identity.** Matched against a dataset's ``dcat.conforms_to``. Two
    #: fields rather than one because the IRI is what the standard is called and
    #: the slug is where this deployment happens to serve it — a deployment gets
    #: to choose the second and never the first.
    iri: str
    #: Where a fetch would retrieve it. Absent means "cached copy supplied by the
    #: operator" — legitimate for a vocabulary behind a login or published only
    #: as a download.
    source: str | None = None
    format: str = JSONLD

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, value: str) -> str:
        if not _SLUG.match(value):
            raise ValueError(
                f"vocabulary slug {value!r} must be lowercase alphanumerics and "
                "hyphens — it is a public URL segment and a filename"
            )
        return value

    @field_validator("iri")
    @classmethod
    def _check_iri(cls, value: str) -> str:
        if not _is_absolute_http_uri(value):
            raise ValueError(
                f"vocabulary iri {value!r} must be an absolute http(s) URI — a "
                "bare name is not a model reference (rulebook M-7)"
            )
        return value

    @field_validator("source")
    @classmethod
    def _check_source(cls, value: str | None) -> str | None:
        if value is not None and not _is_absolute_http_uri(value):
            raise ValueError(
                f"vocabulary source {value!r} must be an absolute http(s) URI"
            )
        return value

    @field_validator("format")
    @classmethod
    def _check_format(cls, value: str) -> str:
        if value != JSONLD:
            raise ValueError(
                f"vocabulary format {value!r} is not supported — {JSONLD!r} is "
                "the only accepted value. ds ships no RDF toolchain; convert the "
                "source once and register the JSON-LD"
            )
        return value

    @property
    def cache_filename(self) -> str:
        return f"{self.slug}.jsonld"


class VocabularyRegistry(BaseModel):
    """Every vocabulary this deployment publishes, indexed two ways."""

    model_config = ConfigDict(extra="forbid")

    vocabularies: list[Vocabulary] = Field(default_factory=list)

    @property
    def by_slug(self) -> dict[str, Vocabulary]:
        return {v.slug: v for v in self.vocabularies}

    @property
    def by_iri(self) -> dict[str, Vocabulary]:
        return {v.iri: v for v in self.vocabularies}

    def resolve(self, conforms_to: str | None) -> Vocabulary | None:
        """The registered vocabulary for a dataset's ``dcat.conforms_to``.

        ``None`` means *not registered here*, which is **not** an error: an
        external standard IRI is a legitimate reference without a local copy, and
        refusing it would make every deployment mirror SAREF before it could
        declare it (`V-6`).
        """
        if not conforms_to:
            return None
        return self.by_iri.get(conforms_to.strip())


def _read(path: Path) -> VocabularyRegistry:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise VocabularyError(f"{path.name} must be a mapping with a 'vocabularies' key")
    return VocabularyRegistry.model_validate(raw)


def load_vocabularies(
    path: Path | str | None,
    overlay_name: str | None = None,
) -> VocabularyRegistry:
    """Load ``vocabularies.yaml`` plus its optional deployment overlay.

    Replace-by-slug, not union. Unlike sharing offers — which are *contributed*
    by whoever declares the datasets, so a duplicate is a real conflict between
    two producers — a vocabulary registry is one deployment's answer to "which
    copies do I serve". An overlay naming an existing slug is rebinding its own
    entry, not overwriting somebody else's.

    A missing file is an **empty registry, not an error**: the platform ships no
    vocabularies (`V-5`), so `task start` must work with nothing registered and
    without reaching the network.
    """
    if path is None:
        return VocabularyRegistry()
    base_path = Path(path)

    registry = _read(base_path) if base_path.exists() else VocabularyRegistry()
    entries = {v.slug: v for v in registry.vocabularies}

    name = overlay_name or os.getenv("VOCABULARIES_OVERLAY_NAME")
    if name:
        overlay_path = base_path.parent / f"vocabularies.{name}.yaml"
        if overlay_path.exists():
            for vocab in _read(overlay_path).vocabularies:
                entries[vocab.slug] = vocab

    _check_unique_iris(entries.values())
    return VocabularyRegistry(vocabularies=list(entries.values()))


def _check_unique_iris(vocabularies) -> None:
    """Two slugs for one IRI is ambiguous, and silently so.

    `resolve()` indexes by IRI, so the loser would simply never be reachable from
    a dataset — its `/ns/{slug}` would serve, and nothing would ever point at it.
    A duplicate slug cannot happen (dict keys); a duplicate IRI can, and must be
    named rather than resolved by insertion order.
    """
    seen: dict[str, str] = {}
    for vocab in vocabularies:
        previous = seen.get(vocab.iri)
        if previous is not None:
            raise VocabularyError(
                f"vocabularies '{previous}' and '{vocab.slug}' both claim IRI "
                f"'{vocab.iri}'. The IRI is the identity — a dataset declaring it "
                "could not say which copy it meant."
            )
        seen[vocab.iri] = vocab.slug
