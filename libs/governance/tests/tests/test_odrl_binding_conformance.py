"""Every operand this mapper emits is bound by the EDC extension that evaluates it.

This is the **binding-vs-emission** half of the policy conformance check
(`EDC-10`). The other half — every bound operand has a registered function — is
`PolicyRegistrationTest` on the Java side; neither can see what the other does,
which is why the defect this file was written for survived so long.

Why it matters, and why nothing else catches it
-----------------------------------------------

EDC's ``ScopeFilter`` **removes** a rule or constraint whose action or left
operand is not bound to the scope being evaluated, rather than failing it. So an
operand this mapper emits and ``services/edc-extensions`` does not bind is not an
error anywhere:

* the offer is published to counterparties carrying the term,
* the term is deleted from the policy before evaluation,
* every negotiation succeeds and no log line mentions any of it.

A permission stripped of its only constraint becomes unconditional. DSSC-AUP-06
requires that *all* policies be enforced during contract negotiation, so a term
that is offered and silently dropped is a conformance failure, not an
inefficiency.

It found ``odrl:industry eq "contract-agreed"`` the first time it ran — emitted
for ``access_requirements: contract``, bound by nothing, duplicating
``ds:contractRequired`` under an operand that means the industry *sector*.

Reading the Java
----------------

The bindings are string literals passed to ``ruleBindingRegistry.bind(...)`` in
one method of one file. Parsing them is cruder than importing them would be, and
it is the only way across the language boundary that does not add a generated
artifact plus a staleness guard for it — two more things to drift. The parse is
deliberately strict: an unreadable ``DataspacesExtension.java`` fails the test
rather than yielding an empty set that would make every assertion below pass.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ds.governance.mapper import GovernanceMapper
from ds.governance.models import (
    DataspacePolicy,
    GovernanceOwner,
    GovernanceRuleV2,
    OdrlProfile,
    PolicyConsent,
    PolicyObligations,
    PurposeConcept,
)

# `libs/governance/tests/tests/` → repository root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXTENSION = (
    _REPO_ROOT
    / "services/edc-extensions/src/main/java/dataspaces/edc/DataspacesExtension.java"
)

_PROFILE = OdrlProfile(
    purposes=[
        PurposeConcept(slug="EnergyCommunityOperation", label="Energy community operation"),
        PurposeConcept(slug="GridMonitoring", label="Grid monitoring"),
    ],
)

# Operands and actions the extension binds that this mapper does not emit.
# A dead binding is the milder failure — it costs nothing until something starts
# emitting the term — but it is how `ds:accessScope` sat in the enforcement
# surface for as long as it did, so each one is listed with its reason.
_ALLOWED_UNEMITTED = {
    # ODRL's default action. Selectable through `policy.permitted_actions`, and
    # EDC's own ContractCoreExtension binds it in these scopes regardless.
    "odrl:use",
    "http://www.w3.org/ns/odrl/2/use",
    # The compact form of the consent operand. The mapper emits the expanded
    # `{namespace}ConsentStatus`; the compact one appears on a policy that
    # reached the store without the ODRL context applied, and on agreements
    # signed before the profile moved. Unbinding it would silently drop the
    # consent constraint from those.
    "ds:consentStatus",
}


_ODRL_NAMESPACE = "http://www.w3.org/ns/odrl/2/"


def _expand(term: str) -> str:
    """`odrl:purpose` and its full IRI are the same term, and both are bound.

    Only the `odrl` prefix expands: it is the one this mapper declares in the
    offer's `@context`. `ds:` is not declared there, so JSON-LD treats it as an
    absolute IRI and it survives verbatim — which is why the extension binds the
    literal string `ds:contractRequired`.
    """
    return (
        _ODRL_NAMESPACE + term[len("odrl:"):] if term.startswith("odrl:") else term
    )


def _bound_terms() -> set[str]:
    """Every term passed as the first argument of `ruleBindingRegistry.bind(...)`.

    Namespace-derived operands (`namespace + "Membership"`) are resolved against
    the default profile namespace, which is what the extension defaults to and
    what `profiles/energy.yaml` ships.
    """
    source = _EXTENSION.read_text(encoding="utf-8")
    terms: set[str] = set()
    for expression in re.findall(r"ruleBindingRegistry\.bind\(\s*([^,]+?)\s*,", source):
        terms |= _resolve(source, expression)

    assert terms, f"parsed no bindings out of {_EXTENSION} — the parse, not the bindings, is broken"
    return terms


def _resolve(source: str, expression: str) -> set[str]:
    """Every string value a Java expression appearing in a `bind(...)` call can take.

    Handles the four shapes the extension uses: a literal, a constant on another
    class (`Purposes.COMPACT`), a local (`String x = namespace + "Suffix"`, or a
    `String[]`), and a loop variable (`for (String action : ACTIONS)`).
    """
    expression = expression.strip()

    if expression.startswith('"'):
        return {expression.strip('"')}

    if "." in expression:
        owner, _, field = expression.partition(".")
        return {_java_constant(_EXTENSION.with_name(f"{owner}.java"), field)}

    concatenated = re.search(rf'String {expression} = namespace \+ "([^"]+)"', source)
    if concatenated:
        return {_PROFILE.namespace + concatenated.group(1)}

    array = re.search(rf"String\[\] {expression} = \{{(.*?)\}};", source, re.DOTALL)
    if array:
        return {
            value
            for element in array.group(1).split(",")
            if element.strip()
            for value in _resolve(source, element)
        }

    # A loop variable: bound once per element of whatever it iterates.
    loop = re.search(rf"for \(String {expression} : (\w+)\)", source)
    if loop:
        return _resolve_iterable(source, loop.group(1))

    pytest.fail(f"cannot resolve the Java expression `{expression}` bound in {_EXTENSION}")


def _resolve_iterable(source: str, name: str) -> set[str]:
    """The elements of a `List.of(...)` constant or a `String[]` local."""
    constant = re.search(rf"List<String> {name} = List\.of\((.*?)\);", source, re.DOTALL)
    if constant:
        return set(re.findall(r'"([^"]+)"', constant.group(1)))
    return _resolve(source, name)


def _java_constant(path: Path, field: str) -> str:
    """The value of `static final String FIELD = "…";` in another class."""
    match = re.search(
        rf'String {field} = "([^"]+)"', path.read_text(encoding="utf-8")
    )
    assert match, f"cannot resolve {path.stem}.{field} in {path}"
    return match.group(1)


def _emitted_terms() -> set[str]:
    """Permission actions and left operands, across every rule shape this mapper builds.

    Driven through the real mapper rather than read off the source: the point is
    what a deployment can actually publish, and the branches that produce the
    rarest constraints are exactly the ones nobody exercises by hand.
    """
    mapper = GovernanceMapper(
        participant_id="rec", base_url="https://rec.dataspaces.localhost", profile=_PROFILE
    )
    terms: set[str] = set()

    for access_level in ("open", "internal", "restricted"):
        for access_requirements in (None, "all", "partner", "contract"):
            for consent_required in (False, True):
                for contract_required in (False, True):
                    rule = GovernanceRuleV2(
                        access_level=access_level,
                        access_requirements=access_requirements,
                        classification="pii" if consent_required else "green",
                        ownership=[GovernanceOwner(name="rec")],
                        policy=DataspacePolicy(
                            purpose=["EnergyCommunityOperation", "GridMonitoring"],
                            consent=PolicyConsent(required=consent_required),
                            obligations=PolicyObligations(contract_required=contract_required),
                        ),
                    )
                    offer = mapper.to_odrl_offer("datasets.silver.meters_15m", rule)
                    for permission in offer["odrl:permission"]:
                        terms.add(permission["odrl:action"]["@id"])
                        for constraint in permission.get("odrl:constraint", []):
                            left = constraint["odrl:leftOperand"]
                            terms.add(left["@id"] if isinstance(left, dict) else left)

    # One purpose rather than several takes the `odrl:isA` branch, which carries
    # the same operand — asserted here so a change to that branch is covered.
    single = GovernanceRuleV2(
        access_level="open",
        policy=DataspacePolicy(purpose=["GridMonitoring"]),
    )
    for permission in mapper.to_odrl_offer("d", single)["odrl:permission"]:
        for constraint in permission.get("odrl:constraint", []):
            left = constraint["odrl:leftOperand"]
            terms.add(left["@id"] if isinstance(left, dict) else left)

    return terms


def test_every_emitted_term_is_bound_by_the_edc_extension():
    """The direction that fails silently, and the one with no exceptions.

    An emitted term the extension does not bind is deleted from the policy
    before evaluation. Nothing raises, nothing logs, and the check the term
    stood for is gone.
    """
    unbound = {_expand(t) for t in _emitted_terms()} - {_expand(t) for t in _bound_terms()}
    assert not unbound, (
        "the governance mapper emits ODRL terms that services/edc-extensions does not bind: "
        f"{sorted(unbound)}. EDC's ScopeFilter *removes* an unbound operand rather than "
        "failing it, so each of these is published to counterparties and then silently "
        "dropped before evaluation — DSSC-AUP-06 requires the opposite. Bind and register "
        "it in DataspacesExtension.registerPolicy, or stop emitting it."
    )


def test_every_emitted_odrl_term_is_bound_in_both_forms():
    """Compact and expanded, because which one arrives is not decidable here.

    Whether a policy carries `odrl:purpose` or the full IRI depends on how it
    reached the store — a freshly mapped offer keeps the compact form, one that
    went through EDC's JSON-LD expansion does not, and an agreement holds
    whichever shape it was signed with, for its whole life. Binding one form is
    binding half the policies.
    """
    bound = _bound_terms()
    for term in sorted(t for t in _emitted_terms() if t.startswith("odrl:")):
        assert term in bound, f"{term} is not bound in its compact form"
        assert _expand(term) in bound, f"{term} is not bound in its expanded form"


def test_no_binding_is_dead():
    """The milder direction: a bound term nothing produces.

    Harmless until something emits it — at which point a bound operand with no
    registered function fails evaluation outright and denies everything. That is
    what `ds:accessScope` was.
    """
    emitted = {_expand(t) for t in _emitted_terms()} | {_expand(t) for t in _ALLOWED_UNEMITTED}
    dead = {_expand(t) for t in _bound_terms()} - emitted
    assert not dead, (
        f"services/edc-extensions binds ODRL terms nothing emits: {sorted(dead)}. "
        "Unbind them, or add each to _ALLOWED_UNEMITTED with the reason it is kept."
    )


def test_the_extension_namespace_matches_the_profile():
    """One namespace, configured twice, and a mismatch unbinds everything.

    `dataspaces.odrl.namespace` on the EDC and `OdrlProfile.namespace` on the
    connector are independent settings that must agree: the extension binds
    `{namespace}Membership` and `{namespace}ConsentStatus`, so a profile whose
    namespace has moved emits operands the extension never bound — the failure
    the test above describes, arriving through configuration rather than code.
    """
    source = _EXTENSION.read_text(encoding="utf-8")
    default = re.search(
        r'"dataspaces\.odrl\.namespace",\s*"([^"]+)"', source
    )
    assert default, f"cannot find the namespace default in {_EXTENSION}"
    assert default.group(1) == OdrlProfile().namespace, (
        "the EDC extension's default ODRL namespace and the default OdrlProfile namespace "
        "have diverged. Every operand is derived from one of them, so they must agree or "
        "a deployment that sets neither enforces nothing."
    )
