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
and registers the result. See `.agents/plans/semantic-vocabulary.md` decision
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
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    #: A JSON-LD file **this participant ships**, as a path relative to
    #: `vocabularies.yaml`.
    #:
    #: Distinct from `source`, and not an overload of it. `source` mirrors a
    #: vocabulary somebody else publishes — SAREF, CIM — and is fetched over
    #: HTTP. This is for the case the registry could not express at all: a
    #: participant that **defines its own model** for its own response shape and
    #: serves it from its own `/ns/{slug}`. There is no URL to fetch, because
    #: this participant is the publisher.
    #:
    #: That case is the common one, not the exotic one. A dataset's payload model
    #: is a fact about what a producer's data plane returns, so most producers
    #: are describing their own shape rather than conforming to a standard —
    #: and a deployment that *does* align to SAREF4ENER simply sets `source`
    #: instead. It also keeps `V-5` true: a shipped definition means a registered
    #: vocabulary that needs no network at startup, so `task start` stays
    #: offline-capable with entries present.
    #:
    #: Resolved to an absolute path when the registry is loaded, so nothing
    #: downstream needs to know where the file was written.
    definition: str | None = None
    format: str = JSONLD

    @field_validator("definition")
    @classmethod
    def _check_definition(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value:
            raise ValueError("vocabulary definition must name a file")
        # Read from a committed config directory and served on a public route, so
        # the path is constrained rather than trusted — the same reason `slug` is.
        if ".." in Path(value).parts:
            raise ValueError(
                f"vocabulary definition {value!r} must stay within the registry's "
                "directory — it is committed configuration, not an arbitrary read"
            )
        return value

    @model_validator(mode="after")
    def _check_one_origin(self) -> Vocabulary:
        if self.source and self.definition:
            raise ValueError(
                f"vocabulary '{self.slug}' declares both a 'source' and a "
                "'definition'. One mirrors somebody else's vocabulary and the "
                "other publishes this participant's own — which of the two is "
                "being served is not something to resolve by precedence."
            )
        return self

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
    registry = VocabularyRegistry.model_validate(raw)
    for vocab in registry.vocabularies:
        if vocab.definition:
            vocab.definition = str(_resolve_definition(path, vocab))
    return registry


def _resolve_definition(registry_path: Path, vocab: Vocabulary) -> Path:
    """A shipped definition, resolved against the registry that names it.

    Two checks, and both are refusals rather than warnings.

    **It must stay inside the registry's directory.** The field validator already
    refuses `..` in the written path, but a symlink does not contain `..` and
    still leaves the directory — so containment is re-checked after resolution,
    against the real path. This file is read by a service and served on a public
    unauthenticated route; "committed configuration" is a claim about where it
    came from, and that claim is what is being enforced.

    **It must exist now, not at fetch time.** A registry naming a file that is
    not there is a deployment that will fail to boot (`V-4`), and the useful
    moment to say so is while reading the registry — with the registry's path in
    hand — not later from a cache filler that only knows a slug.
    """
    base = registry_path.parent.resolve()
    resolved = (base / vocab.definition).resolve()
    if not resolved.is_relative_to(base):
        raise VocabularyError(
            f"vocabulary '{vocab.slug}' definition {vocab.definition!r} resolves to "
            f"{resolved}, outside {base}"
        )
    if not resolved.is_file():
        raise VocabularyError(
            f"vocabulary '{vocab.slug}' names definition {vocab.definition!r}, which "
            f"does not exist at {resolved}. A shipped definition is committed "
            f"configuration — if the file is meant to be fetched, use 'source:'."
        )
    return resolved


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
