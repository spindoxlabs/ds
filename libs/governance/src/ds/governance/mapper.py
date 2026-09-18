"""GovernanceMapper — converts GovernanceRuleV2 to ODRL and EDC payloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .consent import requires_consent as requires_consent
from .models import GovernanceRuleV2, OdrlProfile, subject_column
from .sharing import SharingOfferCatalogue

# No module-level tag→purpose mapping — deployers configure this via
# OdrlProfile.tag_to_purpose so the platform stays domain-neutral.

RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

#: ODRL 2.2 Common Vocabulary: *"The party receiving the result/outcome of
#: exercising the action of the Rule."* Its right operand must identify parties,
#: so the operand carries participant DIDs — the same identity EDC puts in
#: `ParticipantAgent.getIdentity()` and in `counterPartyId`.
#:
#: Emitted in the **access** policy only, which is why a counterparty never sees
#: it: EDC evaluates the access policy in the `catalog` scope, both when it
#: builds a catalogue (`ContractDefinitionResolverImpl`) and again when it
#: validates an initial offer (`ContractValidationServiceImpl.validateInitialOffer`
#: — `new CatalogPolicyContext(agent)`), so one binding covers discovery and
#: negotiation. The restriction hides the offer rather than refusing it late,
#: which is the consequence recorded in `docs/services/federated-catalog.md`.
RECIPIENT_OPERAND = "odrl:recipient"

#: The dev dataspace identity, matching `IDENTITY_REGISTRY_DATASPACE_URI`'s
#: default. A deployment passes its own; the fallback exists for the same reason
#: `participant_did`'s does.
DEFAULT_DATASPACE_URI = "https://dataspaces.localhost/dataspace"

# ── `ds:contractRequired` is deliberately left undeclared (`GOV-10`, half open)
#
# The emitted offer uses one prefix its `@context` does not define: `ds:`, in
# `ds:contractRequired`. Declaring it is **not** a context tweak, and the reason
# is worth stating before someone does it as a tidy-up.
#
# `services/edc-extensions` binds the **literal string**:
#
#     ruleBindingRegistry.bind("ds:contractRequired", NEGOTIATION_SCOPE);
#
# Declare `ds:` here and EDC's JSON-LD expansion resolves the term to a full
# IRI, the binding stops matching, and the contract constraint is silently no
# longer evaluated. That is precisely the failure `GOV-04` and `EDC-06` were —
# a policy term shown to counterparties that nothing enforces — arrived at from
# the opposite direction, and it would pass every unit test in this repository.
#
# Closing it properly is one change across three places, verified live:
#   1. give the profile a `contract_operand`, so this stops being a second
#      hardcoded vocabulary beside `p.term(p.membership_operand)`;
#   2. bind that operand in `DataspacesExtension` the way `membershipOperand`
#      already is, from configuration rather than a literal;
#   3. rebuild the EDC image and prove it on a running exchange — the
#      binding-vs-emission conformance test checks the two lists agree, not that
#      the engine matched.
#
# `rdf:` has none of that risk: it appears only inside `odrl:obligation`, which
# carries no bound operand, so it is declared below.

# ── Permitted actions by access_level ─────────────────────────────────────────
# "{profile}" is replaced with the profile query-action IRI at runtime.

_LEVEL_ACTION_KEYS: dict[str, list[str]] = {
    "open": ["{query}", "odrl:aggregate", "odrl:transfer"],
    "internal": ["{query}", "odrl:aggregate"],
    "restricted": ["{query}"],
    "secret": [],
}

# ── Auto prohibitions by classification ───────────────────────────────────────

_CLASS_PROHIBITIONS: dict[str, list[str]] = {
    "pii": ["odrl:transfer", "odrl:derive", "odrl:distribute", "odrl:sublicense"],
    "red": ["odrl:transfer", "odrl:sublicense"],
    "yellow": ["odrl:sublicense"],
    "green": [],
}


# `requires_consent` was defined here, in full, and the connector then grew a
# byte-identical second copy of it (`connector.services.consent_vocabulary`). It
# now lives in `consent.py` and both spellings delegate to it —
# [#21](https://github.com/spindoxlabs/ds/issues/21). Re-exported here because
# `from ds.governance.mapper import requires_consent` is what the tests and
# `__init__` already say, and because this module is still one of its readers.
#
# Reach for `consent_gate` instead wherever the *reason* matters: it names which
# of the four declarations asserted the gate, which is the half that was
# unrecoverable at the point of use.


class GovernanceMapper:
    """Converts a GovernanceRuleV2 into ODRL and EDC Management API payloads.

    Usage::

        mapper = GovernanceMapper(participant_id="provider",
                                  base_url="https://rec.dataspaces.localhost")
        odrl = mapper.to_odrl_offer("datasets.gold.meters_15m", rule)
        asset = mapper.to_asset_create("datasets.gold.meters_15m", rule)
    """

    def __init__(
        self,
        participant_id: str,
        base_url: str,
        profile: OdrlProfile | None = None,
        owner_did_resolver: Callable[[str], str | None] | None = None,
        participant_did: str | None = None,
        dataspace_uri: str | None = None,
        sharing_offers: SharingOfferCatalogue | None = None,
    ):
        self.participant_id = participant_id
        self.base_url = base_url.rstrip("/")
        self.profile = profile or OdrlProfile()
        self._resolve_owner_did = owner_did_resolver
        # Deployments outside the dev domain must pass participant_did explicitly;
        # the fallback keeps the historical dev default.
        self.participant_did = (
            participant_did or f"did:web:{participant_id}.dataspaces.localhost"
        )
        # What the membership constraint compares against: the value of the
        # `memberOf` claim on the `MembershipCredential` the trust anchor signs.
        # One per dataspace, never per dataset — see the note where
        # `PolicyAudience` used to be, in `models.py`.
        self.dataspace_uri = dataspace_uri or DEFAULT_DATASPACE_URI
        # The offers bound to this deployment's datasets. The recipient access
        # policy is **derived** from them rather than declared beside them: D-14's
        # wildcard admission and the `odrl:recipient` constraint are one
        # restriction, and one restriction gets one source (plan
        # `every-personal-dataset-asks-for-a-local-consent`, "One rule, one
        # implementation"). Absent, no dataset carries a recipient restriction.
        self.sharing_offers = sharing_offers

    @property
    def owner_did_resolver(self) -> Callable[[str], str | None] | None:
        return self._resolve_owner_did

    def bind_offers(self, catalogue: SharingOfferCatalogue | None) -> None:
        """Point the recipient derivation at *catalogue*.

        A sync reads the offers from beside the governance file it was handed,
        which is not always the connector's configured one. Rebinding here keeps
        one authority per sync instead of two loads that can disagree.
        """
        self.sharing_offers = catalogue

    # ── A note on operand vocabularies, kept after the code that needed it ────
    #
    # `matrix.py` used to sort this mapper's constraints into "enforced by EDC"
    # and "enforced by our services" against a hand-written list:
    # `{"ds:accessScope", "ds:contractRequired"}` and
    # `{"odrl:purpose", "ds:consentStatus"}`. **Two of those four were terms this
    # mapper has never emitted** — the membership operand is
    # `{namespace}Membership` and the consent operand `{namespace}ConsentStatus`,
    # both built through `profile.term()`, while `ds:accessScope` was retired
    # when membership moved into the profile.
    #
    # The tell was exact: every operand built through `profile.term()` was
    # missing and every hardcoded one was present. The module is now deleted —
    # nothing consumed it, which is why nothing caught it — but the shape is
    # worth keeping in mind: **a second copy of a vocabulary, in a module that
    # does not own it, drifts the moment the owner adds an indirection.** Ask the
    # profile, or ask this class; do not re-list its terms.
    #
    # The live equivalent of that check is `test_odrl_binding_conformance.py`,
    # which compares what this mapper emits against what `services/edc-extensions`
    # binds — emission against enforcement, rather than against a copy.

    def _resolve_actions(self, keys: list[str]) -> list[str]:
        """Replace ``{query}`` placeholder with profile query-action IRI."""
        query_iri = self.profile.term(self.profile.query_action)
        return [query_iri if k == "{query}" else k for k in keys]

    def _resolve_assigner(self, rule: GovernanceRuleV2) -> str:
        """Resolve the ODRL assigner DID from rule ownership or fall back to participant DID."""
        if self._resolve_owner_did and rule.ownership:
            for owner in rule.ownership:
                did = self._resolve_owner_did(owner.name)
                if did:
                    return did
        return self.participant_did

    # ── ODRL ──────────────────────────────────────────────────────────────────

    def to_odrl_offer(self, dataset_key: str, rule: GovernanceRuleV2) -> dict[str, Any]:
        """Return a full ODRL Offer dict for the given dataset."""
        p = self.profile
        space = rule.dataspace
        access_level = rule.access_level or "internal"

        action_keys = space.permitted_actions or _LEVEL_ACTION_KEYS.get(
            access_level, ["{query}"]
        )
        permitted = self._resolve_actions(action_keys)
        prohibited = space.prohibited_actions or _CLASS_PROHIBITIONS.get(
            rule.classification or "green", []
        )
        purposes = self._purpose_iris(space.purpose)

        offer_id = f"urn:offer:{self.participant_id}:{dataset_key.replace('.', ':')}"

        permissions = [
            self._build_permission(
                action, access_level, rule.access_requirements, purposes, rule
            )
            for action in permitted
        ]

        prohibitions = [{"odrl:action": {"@id": action}} for action in prohibited]

        obligations = self._build_obligations(rule)

        context: dict[str, Any] = {
            "odrl": "http://www.w3.org/ns/odrl/2/",
            p.prefix: p.namespace,
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        }
        # `rdf:` is declared when an obligation uses it, on the same rule as
        # `dct` on the asset: a context prefix a document never references is a
        # claim about vocabularies it does not speak (`GOV-10`).
        if any("rdf:value" in str(o) for o in obligations):
            context["rdf"] = RDF_NAMESPACE
        if p.profile_iri:
            context["odrl:profile"] = p.profile_iri

        offer: dict[str, Any] = {
            "@context": context,
            "@type": "odrl:Offer",
            "@id": offer_id,
            "odrl:assigner": {"@id": self._resolve_assigner(rule)},
            "odrl:permission": permissions,
            "odrl:prohibition": prohibitions,
            "odrl:obligation": obligations,
        }
        # `GOV-08`. Metadata, not a constraint: a counterparty can ask what the
        # vocabulary meant when they negotiated, and no policy engine evaluates
        # it. Omitted entirely when the profile declares no version — naming one
        # it does not have would be worse than silence.
        if p.version:
            offer[f"{p.prefix}:profileVersion"] = p.version
        return offer

    # ── The access policy ─────────────────────────────────────────────────────
    #
    # EDC's `ContractDefinition` holds two policies and asks two questions of
    # them (`ContractDefinition`'s own javadoc): the **access** policy decides
    # whether a counterparty may see and ask for the asset at all, the
    # **contract** policy states the terms that bind once an agreement exists.
    # ds emitted one policy into both slots, so *every* term was published to
    # every counterparty and none of them could hide anything. Membership and
    # recipient are conditions on being admitted, not terms of use, so they are
    # the access policy's and nothing else is.

    def needs_membership(
        self, rule: GovernanceRuleV2, access_level: str | None = None
    ) -> bool:
        """Does this dataset require the counterparty to be a dataspace member?

        Unchanged from when the answer produced an `owner:` string: an `internal`
        or `restricted` dataset, or one whose `access_requirements` asks for a
        partner or a contract. Only the *right operand* changed.
        """
        level = access_level or rule.access_level or "internal"
        reqs = rule.access_requirements or "all"
        return reqs in ("partner", "contract") or level in ("internal", "restricted")

    @staticmethod
    def restricted_to_recipients(rule: GovernanceRuleV2) -> bool:
        """Is this dataset offered **only** to the recipients its offers name?

        `access_requirements: partner`, and nothing else. That value used to emit
        `Membership eq owner:<alias>:partner` — a string no enrolment granted, so
        the datasets asking for it could not be negotiated at all. What it was
        trying to say is *named organisations*, and that is now an
        `odrl:recipient` set in the access policy
        (`the-owner-scope-is-a-string-nobody-grants`, step 2).

        **Opt-in, per dataset, and it has to be.** Deriving the restriction for
        every dataset that declares an offer would close the `D-15` per-party
        path: a person may grant a party the offer does not name, and a negotiation
        refused by the access policy never reaches the consent layer that would
        have admitted them. A provider saying "this goes to these organisations
        and no others" is a different statement from a subject saying "this party
        may have mine", and only the first belongs in the contract definition.

        Where a dataset does opt in, the provider's restriction is the outer one:
        a per-party grant cannot widen it, by design.
        """
        return (rule.access_requirements or "all") == "partner"

    def recipient_dids(self, rule: GovernanceRuleV2) -> list[str]:
        """The DIDs an `odrl:recipient` restriction admits, in declaration order.

        Derived from the offers the dataset declares, through
        `SharingOfferCatalogue.recipients_of` and the owner registry — the same
        declaration `circle.admits_wildcard` reads for `D-14`. One restriction,
        one source, two enforcement points.

        **An alias that does not resolve to a DID contributes nothing**, which
        narrows the set rather than widening it (`CR-4`). It cannot silently pass
        either: an unresolvable recipient is an error from the `offer-recipient`
        compliance check, so the publish is refused before this matters.
        """
        if not self.restricted_to_recipients(rule):
            return []
        if self.sharing_offers is None or self._resolve_owner_did is None:
            return []
        dids: list[str] = []
        for alias in self.sharing_offers.recipients_of(rule.dataspace.sharing_offers):
            did = self._resolve_owner_did(alias)
            if did and did not in dids:
                dids.append(did)
        return dids

    def access_constraints(self, rule: GovernanceRuleV2) -> list[dict[str, Any]]:
        """Membership, then recipient — the two conditions on being admitted."""
        p = self.profile
        constraints: list[dict[str, Any]] = []

        if self.needs_membership(rule):
            constraints.append(
                {
                    "odrl:leftOperand": {"@id": p.term(p.membership_operand)},
                    "odrl:operator": {"@id": "odrl:eq"},
                    # The `memberOf` claim's value, not a scope: the trust anchor
                    # signs it into every `MembershipCredential`, and every
                    # connector already asks for that credential as a DCP DEFAULT
                    # scope (`edc.iam.dcp.scopes.membership.*`).
                    "odrl:rightOperand": {
                        "@value": self.dataspace_uri,
                        "@type": "xsd:string",
                    },
                }
            )

        recipients = self.recipient_dids(rule)
        if recipients:
            constraints.append(
                {
                    "odrl:leftOperand": {"@id": RECIPIENT_OPERAND},
                    # `isAnyOf` even for a single recipient, deliberately. A
                    # recipient restriction is a *set* — the maintainer's
                    # 2026-09-17 decision is that readings go to several
                    # organisations and later to a group — and one shape means one
                    # branch on the Java side. The multi-valued right operand
                    # survives serialisation because of the patched
                    # `JsonObjectFromPolicyTransformer` in
                    # `services/edc-extensions`; see the purpose constraint below
                    # for what breaks without it.
                    "odrl:operator": {"@id": "odrl:isAnyOf"},
                    "odrl:rightOperand": [{"@id": did} for did in recipients],
                }
            )
        return constraints

    def to_access_odrl_set(
        self, dataset_key: str, rule: GovernanceRuleV2
    ) -> dict[str, Any]:
        """The access policy as an ODRL Set: the admitted actions, so constrained.

        The permission's actions are the same ones the contract policy permits.
        That is not decoration — EDC's `ScopeFilter` **deletes** a rule whose
        action is not bound in the scope being evaluated, and a policy whose only
        permission was deleted evaluates to *success*. An access policy carrying
        an action unbound in `catalog` would therefore admit everybody, silently,
        which is the failure mode `test_odrl_binding_conformance` exists for.
        """
        p = self.profile
        space = rule.dataspace
        access_level = rule.access_level or "internal"
        action_keys = space.permitted_actions or _LEVEL_ACTION_KEYS.get(
            access_level, ["{query}"]
        )
        constraints = self.access_constraints(rule)

        permissions: list[dict[str, Any]] = []
        for action in self._resolve_actions(action_keys):
            permission: dict[str, Any] = {"odrl:action": {"@id": action}}
            if constraints:
                permission["odrl:constraint"] = constraints
            permissions.append(permission)

        context: dict[str, Any] = {
            "odrl": "http://www.w3.org/ns/odrl/2/",
            p.prefix: p.namespace,
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        }
        return {
            "@context": context,
            "@type": "odrl:Set",
            "@id": self.access_policy_id(dataset_key, rule),
            "odrl:permission": permissions,
        }

    @staticmethod
    def access_policy_id(dataset_key: str, rule: GovernanceRuleV2) -> str:
        """`<key>-access-policy`, or the deployment's explicit `access_policy_id`.

        `access_policy_id` named the *one* policy before the split, so a
        deployment that set it now names the access half — which is what the
        field always said it did.
        """
        return (
            rule.dataspace.contract.access_policy_id
            or f"{dataset_key.replace('.', '-')}-access-policy"
        )

    @staticmethod
    def contract_policy_id(dataset_key: str, rule: GovernanceRuleV2) -> str:
        """`<key>-policy`, or the deployment's explicit `contract_policy_id`.

        The derived default keeps the id the single policy already had, because
        it is the one an agreement references and an operator greps for.
        """
        return (
            rule.dataspace.contract.contract_policy_id
            or f"{dataset_key.replace('.', '-')}-policy"
        )

    def to_access_policy_create(
        self, dataset_key: str, rule: GovernanceRuleV2
    ) -> dict[str, Any]:
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "PolicyDefinition",
            "@id": self.access_policy_id(dataset_key, rule),
            "policy": self.to_access_odrl_set(dataset_key, rule),
        }

    def _build_permission(
        self,
        action: str,
        access_level: str,
        access_requirements: str | None,
        purposes: list[str],
        rule: GovernanceRuleV2,
    ) -> dict[str, Any]:
        p = self.profile
        space = rule.dataspace
        constraints: list[dict[str, Any]] = []
        reqs = access_requirements or "all"

        # ── The membership constraint is **not** here any more ────────────────
        #
        # It moved to the access policy (`access_constraints`), with the
        # recipient restriction beside it, because that is the policy EDC
        # evaluates in the `catalog` scope — so the offer is *hidden* from a
        # non-member rather than shown and then refused. It also stopped being a
        # string nobody grants: `owner:<alias>:member|partner` and
        # `dataspaces.query` were checked over HTTP against a hand-kept list on
        # the trust anchor, beside a signed `MembershipCredential` that already
        # carries the answer (`the-owner-scope-is-a-string-nobody-grants`).
        #
        # Contract gate — `access_requirements: contract`, `access_level:
        # restricted`, or an explicit `dataspace.contract_required`. The EDC
        # extension evaluates this as the explicit policy acknowledgement
        # performed by negotiation.
        #
        # `access_requirements: contract` used to emit a *second*, separate
        # constraint: `odrl:industry eq "contract-agreed"`. It said the same
        # thing under an operand that means the industry *sector* in ODRL 2.2,
        # and `services/edc-extensions` bound no such operand — so EDC's
        # ScopeFilter deleted it before evaluation and every counterparty was
        # shown a policy term this dataspace never enforced, which is what
        # DSSC-AUP-06 forbids. The binding-vs-emission conformance test
        # (`test_odrl_binding_conformance.py`) is what found it and what stops
        # the next one.
        if (
            reqs == "contract"
            or access_level == "restricted"
            or space.contract_required
        ):
            constraints.append(
                {
                    "odrl:leftOperand": {"@id": "ds:contractRequired"},
                    "odrl:operator": {"@id": "odrl:eq"},
                    # Typed, like every sibling constraint (`GOV-11`). It was a bare
                    # `"true"` — the only untyped right operand this mapper emitted,
                    # so a JSON-LD processor was free to read it as a plain literal
                    # while the membership and purpose operands beside it carried
                    # their type. `xsd:boolean` rather than the siblings'
                    # `xsd:string`, because the value is one.
                    #
                    # Safe against the enforcement side: `ContractRequiredFunction`
                    # parses through `Purposes.unwrapScalar`, which reaches `@value`
                    # inside a `JsonObject` before comparing — the same unwrapping
                    # that exists because EDC's expansion produces this shape anyway.
                    "odrl:rightOperand": {"@value": "true", "@type": "xsd:boolean"},
                }
            )

        # Purpose constraint — ONE constraint listing every permitted purpose.
        #
        # Constraints within a permission are ANDed, so emitting one constraint
        # per purpose would demand that a consumer's use serve all of them at
        # once. `odrl:isAnyOf` expresses what a multi-purpose dataset actually
        # offers: any one of these reasons is admissible.
        #
        # This shape depends on a patched EDC class — do not change it casually.
        #
        # Stock EDC cannot serialise a multi-valued right operand: it ingests,
        # stores and evaluates one correctly, but
        # `JsonObjectFromPolicyTransformer.visitLiteralExpression` renders it with
        # `toString()` on the way out, so the operand reaches every other
        # participant as `"[{@value={valueType=STRING, chars=https://…}}, …]"`.
        # `services/edc-extensions` carries a patched copy of that class so the
        # published operand is a plain array of purpose IRIs.
        #
        # `odrl:or` of scalar `isA` was tried instead and is **worse**: EDC accepts
        # the `OrConstraint` on ingest and then fails JSON-LD compaction
        # (`IRI_CONFUSED_WITH_PREFIX`), 500ing the entire Management API list
        # response and emptying the DSP catalogue.
        #
        # The rulebook's account of the profile and its required elements is
        # `docs/rulebook/policies.md`; the packaging guard that keeps the
        # forked transformer in the shadow JAR is in `services/edc-extensions`.
        # (This used to cite `docs/governance-and-odrl.md`, which has never
        # existed in this tree — `GOV-16`.)
        if len(purposes) == 1:
            constraints.append(
                {
                    "odrl:leftOperand": {"@id": "odrl:purpose"},
                    "odrl:operator": {"@id": "odrl:isA"},
                    "odrl:rightOperand": {"@id": purposes[0]},
                }
            )
        elif purposes:
            constraints.append(
                {
                    "odrl:leftOperand": {"@id": "odrl:purpose"},
                    "odrl:operator": {"@id": "odrl:isAnyOf"},
                    "odrl:rightOperand": [{"@id": purpose} for purpose in purposes],
                }
            )

        # Consent constraint
        needs_consent = requires_consent(rule)
        if needs_consent:
            constraints.append(
                {
                    "odrl:leftOperand": {"@id": p.term(p.consent_operand)},
                    "odrl:operator": {"@id": "odrl:eq"},
                    "odrl:rightOperand": {"@value": "active", "@type": "xsd:string"},
                }
            )

        perm: dict[str, Any] = {
            "odrl:action": {"@id": action},
        }
        if constraints:
            perm["odrl:constraint"] = constraints

        # Consent pre-duty
        if needs_consent:
            perm["odrl:duty"] = [
                {
                    "odrl:action": {"@id": "odrl:obtainConsent"},
                }
            ]

        return perm

    def _build_obligations(self, rule: GovernanceRuleV2) -> list[dict[str, Any]]:
        obligations: list[dict[str, Any]] = []
        ob = rule.dataspace.obligations

        delete_days = ob.delete_after_days or rule.retention_days
        if delete_days:
            obligations.append(
                {
                    "odrl:action": [
                        {
                            "rdf:value": {"@id": "odrl:delete"},
                            "odrl:refinement": [
                                {
                                    "odrl:leftOperand": {"@id": "odrl:delayPeriod"},
                                    "odrl:operator": {"@id": "odrl:lteq"},
                                    "odrl:rightOperand": {
                                        "@value": f"P{delete_days}D",
                                        "@type": "xsd:duration",
                                    },
                                }
                            ],
                        }
                    ],
                }
            )

        if ob.attribution and rule.attribution:
            obligations.append(
                {
                    "odrl:action": {"@id": "odrl:attributeTo"},
                    "odrl:attributeTo": {"@id": self._resolve_assigner(rule)},
                    "odrl:target": rule.attribution,
                }
            )

        return obligations

    def _purpose_iris(self, declared: list[str]) -> list[str]:
        """Expand ``dataspace.purpose[]`` to full profile IRIs, order-preserving.

        ``dataspace.purpose[]`` is the *only* runtime source of a dataset's
        purposes.  Entries may be written as slugs or as full IRIs; anything
        that is neither a known slug nor an absolute IRI is dropped here and
        reported by the ``purpose-declared`` compliance check, so a typo cannot
        silently become an unconstrained offer.
        """
        seen: set[str] = set()
        purposes: list[str] = []
        for entry in declared:
            slug = self.profile.purpose_slug(entry)
            iri = (
                self.profile.purpose_iri(slug)
                if slug
                else (entry if "://" in entry else None)
            )
            if iri and iri not in seen:
                purposes.append(iri)
                seen.add(iri)
        return purposes

    # `derive_purposes_from_tags` was removed here (`GOV-15`). It mapped tags to
    # purpose slugs through `OdrlProfile.tag_to_purpose`, described itself as a
    # scaffolding helper, and was called by nothing in this repository or any
    # sibling checkout.
    #
    # It is worth being clear why it does not come back rather than only that it
    # went. The unit's own rule is *purposes are declared, never derived from
    # tags*: a tag is a topic, a purpose is a reason for processing, and
    # `dataspace.purpose[]` is the only runtime source. A helper that turns the
    # first into the second is the wrong shape to have lying around next to the
    # emitter, however carefully its docstring disclaims itself — the next reader
    # sees a supported conversion. `OdrlProfile.tag_to_purpose` stays: it is
    # profile data a deployer may carry for their own authoring tools, and
    # nothing in the mapper reads it.

    # ── EDC Asset ─────────────────────────────────────────────────────────────

    def to_asset_create(
        self, dataset_key: str, rule: GovernanceRuleV2
    ) -> dict[str, Any]:
        ds = rule.dataspace
        asset_id = (
            ds.asset.id or f"{self.base_url}/datasets/{dataset_key.replace('.', '/')}"
        )
        medallion = ds.medallion or self._infer_medallion(dataset_key)
        pfx = self.profile.prefix

        data_address: dict[str, Any] = {
            "type": ds.data_address.type,
            "baseUrl": ds.data_address.base_url,
            "proxyPath": str(ds.data_address.proxy_path).lower(),
            "proxyQueryParams": str(ds.data_address.proxy_query_params).lower(),
        }
        for k, v in ds.data_address.query_params.items():
            data_address[f"queryParam:{k}"] = v

        # `dct` is declared only when something uses it. An asset carrying a
        # context prefix it never references is a claim about vocabularies this
        # asset speaks, and EDC compacts against the context it is given.
        context: dict[str, Any] = {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"}
        if rule.dcat.conforms_to or rule.documentation_url:
            context["dct"] = "http://purl.org/dc/terms/"

        return {
            "@context": context,
            "@type": "Asset",
            "@id": asset_id,
            "properties": {
                "name": rule.title or dataset_key,
                "description": rule.description or "",
                "contenttype": ds.asset.content_type,
                # The payload semantic model (`M-4`), carried into the DSP
                # catalogue so a consumer discovers it at browse time rather than
                # after negotiating. A `dct:` term where every sibling is
                # `{prefix}:` — deliberately: `dct:conformsTo` is a DCAT-AP term
                # with a meaning outside this dataspace, and re-spelling it under
                # the local profile prefix would make it a private property that
                # merely looks standard.
                "dct:conformsTo": rule.dcat.conforms_to,
                f"{pfx}:medallion": medallion,
                f"{pfx}:classification": rule.classification,
                f"{pfx}:sourceSystem": rule.source_system,
                f"{pfx}:tags": ",".join(rule.tags),
                # `subject_column(rule)`, never the two fields by hand. This
                # site had its own copy of the precedence, and the copy and the
                # helper resolved it in *opposite* orders — so a rule declaring
                # both spellings published one column here and reported the
                # other to `/internal/dataplane/authorize` (`GOV-05`). One fact,
                # one reader; `test_subject_column.py` asserts they agree.
                f"{pfx}:userFilterColumn": subject_column(rule),
                f"{pfx}:rowFilters": [
                    {"handler": f.handler, "column": f.args.column}
                    for f in rule.row_filters
                ]
                or None,
                # `GOV-14`. Parsed, merged through overlays and read by nothing
                # until now — so a producer who documented their dataset saw the
                # link go nowhere, and a consumer browsing the catalogue had no
                # way to reach it.
                #
                # Emitted here and **not** as an ODRL term, which is the whole
                # distinction the other three fields in this row fail: this is
                # *description*, so publishing it claims nothing about
                # enforcement. `notify_on_access` and `anonymize_before_use` are
                # obligations, and emitting either would tell a counterparty this
                # dataspace does something it does not — `DSSC-AUP-06`. They are
                # reported by the `declared-not-enforced` check instead.
                "dct:references": rule.documentation_url,
            },
            "dataAddress": data_address,
        }

    # ── EDC Policy Definition ─────────────────────────────────────────────────

    def to_policy_create(
        self, dataset_key: str, rule: GovernanceRuleV2
    ) -> dict[str, Any]:
        """The **contract** policy definition — the terms, not the admission.

        It used to read `access_policy_id` for its own id, which is how one
        policy ended up in both slots of the contract definition. The access half
        is `to_access_policy_create`.
        """
        policy_id = self.contract_policy_id(dataset_key, rule)
        odrl_offer = self.to_odrl_offer(dataset_key, rule)
        # EDC expects a Set (not an Offer) for PolicyDefinition
        odrl_set = {**odrl_offer, "@type": "odrl:Set"}
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "PolicyDefinition",
            "@id": policy_id,
            "policy": odrl_set,
        }

    # ── EDC Contract Definition ───────────────────────────────────────────────

    def to_contract_definition(
        self, dataset_key: str, rule: GovernanceRuleV2, policy_id: str, asset_id: str
    ) -> dict[str, Any]:
        ds = rule.dataspace
        # **Not `access_policy_id`** (`GOV-12`). A deployment that named its
        # access policy gave the *contract definition* the same `@id`, because
        # this line and `to_policy_create` both derived from that one field. The
        # two live in different EDC collections so nothing 409s — the id simply
        # stops identifying anything: a log line, an evidence row or an operator
        # grepping for it gets two entities of different kinds, and "delete the
        # policy" and "delete the contract" become the same sentence.
        #
        # `contract_definition_id` is the explicit override; the derived default
        # keeps the `-contract` suffix that already distinguished it whenever the
        # field was unset. `check_policy_contract_id_collision` fails the
        # validation gate if the two ever coincide again.
        contract_id = (
            ds.contract.contract_definition_id
            or f"{dataset_key.replace('.', '-')}-contract"
        )
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "ContractDefinition",
            "@id": contract_id,
            # **Two policies now, and they differ** — the access half hides the
            # asset from anyone the recipient/membership constraints exclude, the
            # contract half states the terms. `policy_id` is the contract one,
            # passed in by the caller that created it.
            "accessPolicyId": self.access_policy_id(dataset_key, rule),
            "contractPolicyId": ds.contract.contract_policy_id or policy_id,
            "assetsSelector": [
                {
                    "@type": "CriterionDto",
                    "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
                    "operator": "=",
                    "operandRight": asset_id,
                }
            ],
        }

    @staticmethod
    def _infer_medallion(dataset_key: str) -> str:
        for level in ("gold", "silver", "bronze", "raw", "staging"):
            if level in dataset_key:
                return level
        return "unknown"
