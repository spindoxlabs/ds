"""The semantic vocabulary registry — slug, canonical IRI, local copy.

What these guard is mostly the *refusals*. The registry's happy path is a dict
lookup; its value is in what it declines to accept, because a slug is a public
URL segment and a filename, and an IRI is the identity a dataset's
`dcat.conforms_to` is matched against.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ds.governance.vocabularies import (
    Vocabulary,
    VocabularyError,
    VocabularyRegistry,
    load_vocabularies,
)

SAREF = "https://saref.etsi.org/saref4ener/"
CIM = "https://cim.ucaiug.io/ns#"


def write(tmp_path: Path, doc: dict, name: str = "vocabularies.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def entry(**overrides) -> dict:
    base = {
        "slug": "saref4ener",
        "title": "SAREF extension for energy",
        "version": "1.2.1",
        "iri": SAREF,
        "source": "https://saref.etsi.org/saref4ener/v1.2.1/saref4ener.jsonld",
        "format": "jsonld",
    }
    base.update(overrides)
    return base


# ── Loading ───────────────────────────────────────────────────────────────────


def test_a_missing_file_is_an_empty_registry_not_an_error():
    """`V-5`: the platform ships no vocabularies, so `task start` must work.

    If this raised, zero-config dev would need a registry file before the
    connector could boot — and the startup loader would then need the network.
    """
    registry = load_vocabularies(Path("/nonexistent/vocabularies.yaml"))
    assert registry.vocabularies == []


def test_none_path_is_an_empty_registry():
    assert load_vocabularies(None).vocabularies == []


def test_a_registered_vocabulary_loads(tmp_path):
    path = write(tmp_path, {"vocabularies": [entry()]})
    registry = load_vocabularies(path)
    assert [v.slug for v in registry.vocabularies] == ["saref4ener"]
    assert registry.by_slug["saref4ener"].iri == SAREF


def test_the_overlay_replaces_by_slug(tmp_path):
    """A deployment rebinds its own entry — unlike sharing offers, which union.

    Offers are *contributed* by whoever declares the datasets, so a duplicate id
    is a conflict between two producers. A registry is one deployment's answer to
    "which copies do I serve", so an overlay naming an existing slug is editing
    its own entry.
    """
    write(tmp_path, {"vocabularies": [entry()]})
    write(
        tmp_path,
        {"vocabularies": [entry(version="1.2.1-local", source=None)]},
        name="vocabularies.site.yaml",
    )
    registry = load_vocabularies(tmp_path / "vocabularies.yaml", overlay_name="site")
    assert len(registry.vocabularies) == 1
    assert registry.vocabularies[0].version == "1.2.1-local"
    assert registry.vocabularies[0].source is None


def test_an_absent_overlay_is_not_an_error(tmp_path):
    path = write(tmp_path, {"vocabularies": [entry()]})
    assert len(load_vocabularies(path, overlay_name="nope").vocabularies) == 1


# ── Resolution ────────────────────────────────────────────────────────────────


def test_resolve_matches_a_dataset_conforms_to(tmp_path):
    registry = load_vocabularies(write(tmp_path, {"vocabularies": [entry()]}))
    assert registry.resolve(SAREF).slug == "saref4ener"


def test_resolve_tolerates_surrounding_whitespace(tmp_path):
    """The value comes out of hand-authored YAML."""
    registry = load_vocabularies(write(tmp_path, {"vocabularies": [entry()]}))
    assert registry.resolve(f"  {SAREF} ").slug == "saref4ener"


def test_an_unregistered_iri_resolves_to_none_rather_than_raising(tmp_path):
    """`V-6` — not registered is not an error.

    An external standard IRI is a legitimate reference without a local copy.
    Raising here would force every deployment to mirror SAREF before it could
    declare conformance to it, which is the opposite of what a registry is for.
    """
    registry = load_vocabularies(write(tmp_path, {"vocabularies": [entry()]}))
    assert registry.resolve(CIM) is None


def test_no_conforms_to_resolves_to_none(tmp_path):
    registry = load_vocabularies(write(tmp_path, {"vocabularies": [entry()]}))
    assert registry.resolve(None) is None
    assert registry.resolve("") is None


# ── Refusals ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "slug",
    [
        "../etc/passwd",  # the one that matters: slug becomes a filename
        "SAREF4ENER",  # a public URL segment, so case is not free
        "saref ener",
        "saref_ener",
        "",
        "-leading",
        "trailing-",
    ],
)
def test_a_slug_that_is_not_a_url_segment_is_refused(slug):
    with pytest.raises(ValidationError):
        Vocabulary(slug=slug, title="t", iri=SAREF)


def test_the_slug_constraint_is_what_bounds_the_cache_filename():
    """Stated as its own assertion because it is the security-relevant one.

    `cache_filename` is joined to the cache directory. The validator is the only
    thing standing between a registry entry and a path outside it.
    """
    assert Vocabulary(slug="saref4ener", title="t", iri=SAREF).cache_filename == (
        "saref4ener.jsonld"
    )
    with pytest.raises(ValidationError):
        Vocabulary(slug="../../etc/passwd", title="t", iri=SAREF)


@pytest.mark.parametrize("iri", ["saref4ener", "urn:x:y", "/saref", "ftp://x/y", ""])
def test_a_bare_name_is_not_a_model_reference(iri):
    """Rulebook `M-7`, and this validator is what makes it enforceable."""
    with pytest.raises(ValidationError):
        Vocabulary(slug="s", title="t", iri=iri)


@pytest.mark.parametrize("fmt", ["turtle", "rdfxml", "ntriples", "json", ""])
def test_a_non_jsonld_format_is_refused_by_name(fmt):
    """`V-3` — ds ships no RDF toolchain, so a Turtle source is refused, not half-read."""
    with pytest.raises(ValidationError) as exc:
        Vocabulary(slug="s", title="t", iri=SAREF, format=fmt)
    assert "jsonld" in str(exc.value)


def test_an_unknown_key_is_refused(tmp_path):
    """`extra="forbid"`: a misspelled key must not be silently ignored.

    This is the same defect the `dcat:` block had for real — a valid-looking file
    with a field nothing reads. A registry is small enough that there is no
    excuse for tolerating it.
    """
    with pytest.raises(ValidationError):
        Vocabulary(slug="s", title="t", iri=SAREF, sourse="typo")


def test_two_slugs_claiming_one_iri_are_refused(tmp_path):
    """Indexed by IRI, so the loser would be unreachable rather than wrong."""
    path = write(
        tmp_path,
        {
            "vocabularies": [
                entry(),
                entry(slug="saref-energy", source=None),
            ]
        },
    )
    with pytest.raises(VocabularyError) as exc:
        load_vocabularies(path)
    assert "saref4ener" in str(exc.value) and "saref-energy" in str(exc.value)


def test_a_source_that_is_not_a_url_is_refused():
    with pytest.raises(ValidationError):
        Vocabulary(slug="s", title="t", iri=SAREF, source="./local.jsonld")


def test_no_source_is_allowed(tmp_path):
    """A vocabulary behind a login, or published only as a download.

    The operator supplies the cached file; ds has nowhere to fetch it from and
    says so by omission rather than by inventing a URL.
    """
    vocab = Vocabulary(slug="s", title="t", iri=SAREF, source=None)
    assert vocab.source is None


def test_a_file_that_is_not_a_mapping_is_refused(tmp_path):
    path = tmp_path / "vocabularies.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(VocabularyError):
        load_vocabularies(path)


def test_an_empty_registry_object_is_valid():
    assert VocabularyRegistry().vocabularies == []


# ── A definition this participant ships ───────────────────────────


def _write(tmp_path, registry_yaml: str, *, definition: str | None = None):
    (tmp_path / "vocabularies.yaml").write_text(registry_yaml, encoding="utf-8")
    if definition is not None:
        (tmp_path / "own.jsonld").write_text(definition, encoding="utf-8")
    return tmp_path / "vocabularies.yaml"


_ENTRY = (
    "vocabularies:\n"
    "  - slug: own\n"
    "    title: Our own model\n"
    "    iri: https://rec.dataspaces.localhost/ns/own\n"
    "    definition: {definition}\n"
)


def test_a_definition_is_resolved_against_the_registry_that_names_it(tmp_path):
    from ds.governance.vocabularies import load_vocabularies

    path = _write(tmp_path, _ENTRY.format(definition="own.jsonld"), definition="{}")
    registry = load_vocabularies(path)

    resolved = Path(registry.vocabularies[0].definition)
    assert resolved.is_absolute() and resolved == (tmp_path / "own.jsonld").resolve()


def test_a_missing_definition_is_refused_when_the_registry_is_read(tmp_path):
    """With the registry's path in hand, so the message can name where it looked.

    A registry naming a file that is not there is a deployment that will fail to
    boot (`V-4`); saying so from a cache filler that only knows a slug would say
    it later and less usefully.
    """
    from ds.governance.vocabularies import VocabularyError, load_vocabularies

    path = _write(tmp_path, _ENTRY.format(definition="absent.jsonld"))

    with pytest.raises(VocabularyError, match="does not exist"):
        load_vocabularies(path)


def test_a_definition_may_not_escape_the_registry_directory(tmp_path):
    from ds.governance.vocabularies import VocabularyError, load_vocabularies

    outside = tmp_path.parent / "outside.jsonld"
    outside.write_text("{}", encoding="utf-8")
    registry_dir = tmp_path / "governance"
    registry_dir.mkdir()
    (registry_dir / "link.jsonld").symlink_to(outside)
    path = _write(registry_dir, _ENTRY.format(definition="link.jsonld"))

    with pytest.raises(VocabularyError, match="outside"):
        load_vocabularies(path)


def test_a_written_definition_may_not_traverse_upwards(tmp_path):
    """Refused by the field validator, before any path is resolved."""
    from pydantic import ValidationError

    from ds.governance.vocabularies import VocabularyRegistry

    with pytest.raises(ValidationError, match="within the registry"):
        VocabularyRegistry.model_validate(
            {
                "vocabularies": [
                    {
                        "slug": "own",
                        "title": "t",
                        "iri": "https://x.test/ns/own",
                        "definition": "../elsewhere.jsonld",
                    }
                ]
            }
        )


def test_source_and_definition_are_mutually_exclusive():
    from pydantic import ValidationError

    from ds.governance.vocabularies import VocabularyRegistry

    with pytest.raises(ValidationError, match="both a 'source' and a 'definition'"):
        VocabularyRegistry.model_validate(
            {
                "vocabularies": [
                    {
                        "slug": "own",
                        "title": "t",
                        "iri": "https://x.test/ns/own",
                        "source": "https://x.test/own.jsonld",
                        "definition": "own.jsonld",
                    }
                ]
            }
        )
