"""ODRL documents in the compact form EDC's v5 management API validates.

v5 validates the **raw** request body against JSON schemas before any JSON-LD
processing (``management-api-schema-validator``). A policy is checked against
the DSP 2025 contract schema, which fixes the compact form the DSP ODRL profile
context (``https://w3id.org/dspace/2025/1/odrl-profile.jsonld``) produces:
``"@type": "Set"``, ``permission`` / ``action`` / ``constraint`` /
``leftOperand`` / ``operator`` / ``rightOperand`` without a prefix, ``action``
and ``leftOperand`` as strings, and ``operator`` as one of the profile's
terms (``eq``, ``isAnyOf``, …). Anything else is a 400 before EDC reads it.

ds's mapper writes ODRL with an embedded ``@context`` and ``odrl:``-prefixed
keys, which v3 accepted because it expanded first. :func:`to_dsp_compact`
rewrites such a document into the profile's form **without changing what it
means**: every compact IRI is expanded against the document's own context,
values the profile types as ``@vocab`` (``action``, ``leftOperand``) become
absolute IRIs, and ``operator`` becomes the profile term for the same IRI. The
embedded context is dropped, so nothing in the result depends on a prefix the
profile does not declare.
"""

from __future__ import annotations

from typing import Any

ODRL = "http://www.w3.org/ns/odrl/2/"

#: The operators the DSP 2025 profile defines as terms — the schema's enum.
DSP_OPERATORS = frozenset(
    {
        "eq",
        "gt",
        "gteq",
        "lteq",
        "hasPart",
        "isA",
        "isAllOf",
        "isAnyOf",
        "isNoneOf",
        "isPartOf",
        "lt",
        "term-lteq",
        "neq",
    }
)

#: Profile terms a key may be written as, keyed by their ODRL local name.
_RULE_KEYS = frozenset(
    {
        "permission",
        "prohibition",
        "obligation",
        "duty",
        "action",
        "constraint",
        "leftOperand",
        "operator",
        "rightOperand",
        "assigner",
        "assignee",
        "target",
        "profile",
        "and",
        "or",
        "xone",
        "andSequence",
    }
)

_POLICY_TYPES = {"Set", "Offer", "Agreement", "Policy"}

#: Prefixes every ds document may use without declaring them.
_WELL_KNOWN = {
    "odrl": ODRL,
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dct": "http://purl.org/dc/terms/",
}


class OdrlConversionError(ValueError):
    """The document cannot be expressed in the DSP profile's compact form."""


def _prefixes(context: Any) -> dict[str, str]:
    """The prefix map a document's ``@context`` declares (strings only)."""
    prefixes = dict(_WELL_KNOWN)
    contexts = context if isinstance(context, list) else [context]
    for ctx in contexts:
        if isinstance(ctx, dict):
            for key, value in ctx.items():
                if isinstance(value, str) and not key.startswith("@"):
                    prefixes[key] = value
    return prefixes


def _expand(value: str, prefixes: dict[str, str]) -> str:
    """``dsp-policy:Membership`` → the absolute IRI; anything else unchanged."""
    if ":" not in value:
        return value
    prefix, _, rest = value.partition(":")
    if rest.startswith("//"):
        return value  # already absolute (http://, https://)
    base = prefixes.get(prefix)
    return base + rest if base else value


def _local_key(key: str, prefixes: dict[str, str]) -> str:
    """The profile term for a key, when it is an ODRL rule/policy key."""
    expanded = _expand(key, prefixes)
    if expanded.startswith(ODRL):
        local = expanded[len(ODRL) :]
        if local in _RULE_KEYS:
            return local
    return key


def _iri(value: Any, prefixes: dict[str, str]) -> str:
    """An ``@vocab``-typed value as an absolute IRI string."""
    if isinstance(value, dict):
        value = value.get("@id") or value.get("@value") or ""
    if not isinstance(value, str) or not value:
        raise OdrlConversionError(f"expected an IRI, got {value!r}")
    expanded = _expand(value, prefixes)
    if ":" not in expanded:
        # A bare term. The profile resolves only its own terms, and an ODRL
        # action such as `use` is one of them; anything else would be resolved
        # against the document base, so it is written out in full.
        return ODRL + expanded
    return expanded


def _operator(value: Any, prefixes: dict[str, str]) -> str:
    iri = _iri(value, prefixes)
    local = iri[len(ODRL) :] if iri.startswith(ODRL) else ""
    if local not in DSP_OPERATORS:
        raise OdrlConversionError(
            f"operator {iri!r} is not one the DSP 2025 profile defines"
        )
    return local


def _node_id(value: Any, prefixes: dict[str, str]) -> Any:
    """``assigner`` / ``target``: ``@id``-typed, so a plain string."""
    if isinstance(value, dict) and "@id" in value:
        return _expand(str(value["@id"]), prefixes)
    if isinstance(value, str):
        return _expand(value, prefixes)
    return value


def _right_operand(value: Any, prefixes: dict[str, str]) -> Any:
    """A literal stays a literal; a typed ``xsd:string`` literal becomes plain."""
    if isinstance(value, list):
        return [_right_operand(item, prefixes) for item in value]
    if isinstance(value, dict):
        if set(value) <= {"@value", "@type"}:
            dtype = _expand(str(value.get("@type", "")), prefixes)
            if not dtype or dtype == _WELL_KNOWN["xsd"] + "string":
                return value.get("@value")
            return {"@value": value.get("@value"), "@type": dtype}
        if set(value) == {"@id"}:
            return {"@id": _expand(str(value["@id"]), prefixes)}
    return value


def _convert(node: Any, prefixes: dict[str, str]) -> Any:
    if isinstance(node, list):
        return [_convert(item, prefixes) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for raw_key, value in node.items():
        if raw_key == "@context":
            continue
        key = _local_key(raw_key, prefixes)
        if key == "@type" and isinstance(value, str):
            local = _expand(value, prefixes).removeprefix(ODRL)
            out[key] = local if local in _POLICY_TYPES else value
        elif key == "action":
            out[key] = _iri(value, prefixes)
        elif key == "leftOperand":
            out[key] = _iri(value, prefixes)
        elif key == "operator":
            out[key] = _operator(value, prefixes)
        elif key == "rightOperand":
            out[key] = _right_operand(value, prefixes)
        elif key in {"assigner", "assignee", "target"}:
            out[key] = _node_id(value, prefixes)
        elif key in {"permission", "prohibition", "obligation", "duty", "constraint"}:
            items = value if isinstance(value, list) else [value]
            out[key] = [_convert(item, prefixes) for item in items]
        elif key in {"and", "or", "xone", "andSequence"}:
            items = value if isinstance(value, list) else [value]
            out[key] = [_convert(item, prefixes) for item in items]
        else:
            out[key] = _convert(value, prefixes)
    return out


def to_dsp_compact(policy: dict[str, Any]) -> dict[str, Any]:
    """Rewrite an ODRL policy into the DSP 2025 profile's compact form."""
    prefixes = _prefixes(policy.get("@context"))
    converted = _convert(policy, prefixes)
    if not isinstance(converted, dict):  # pragma: no cover — input is a dict
        raise OdrlConversionError("policy must be a JSON object")
    return converted
