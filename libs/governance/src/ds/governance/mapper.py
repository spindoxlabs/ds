"""GovernanceMapper — converts GovernanceRuleV2 to ODRL and EDC payloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import GovernanceRuleV2, OdrlProfile, subject_column

# No module-level tag→purpose mapping — deployers configure this via
# OdrlProfile.tag_to_purpose so the platform stays domain-neutral.

RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

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


def requires_consent(rule: GovernanceRuleV2) -> bool:
    """Whether this dataset may only be accessed with the subject's consent.

    **One predicate, because there are two readers.** The mapper decides whether
    the published offer carries a consent constraint; `matrix.py` decides whether
    the compliance report says the dataset is consent-gated. They disagreed:
    the matrix included `classification == "pii"` and the mapper did not, so a
    `pii` dataset with no filter and no `consent.required` was **reported gated
    and published ungated** — the divergence pointing the wrong way, since the
    report is what an auditor reads.

    `pii` is in, and it is the rulebook's own switch: *"`classification: pii` on
    a dataset is the switch. A dataset carrying that classification is subject to
    everything on this page"* (Rulebook · Personal data). A producer that
    classifies a dataset `pii` has declared it personal data; publishing it
    without a consent term would say the opposite on the wire.

    A `pii` dataset with no row filter is a **separate** defect and stays one:
    `check_consent_coherence` warns *"classified 'pii' but declares no row-level
    filtering"*, because a gate no column can evaluate per subject is a gate in
    name. Gating it here does not fix that; it stops the offer under-claiming
    while the warning names what is missing.
    """
    return bool(
        rule.policy.consent.required
        or rule.row_filters
        or rule.user_filter_column
        or rule.classification == "pii"
    )


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

    @property
    def owner_did_resolver(self) -> Callable[[str], str | None] | None:
        return self._resolve_owner_did

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
        policy = rule.policy
        access_level = rule.access_level or "internal"

        action_keys = policy.permitted_actions or _LEVEL_ACTION_KEYS.get(
            access_level, ["{query}"]
        )
        permitted = self._resolve_actions(action_keys)
        prohibited = policy.prohibited_actions or _CLASS_PROHIBITIONS.get(
            rule.classification or "green", []
        )
        purposes = self._purpose_iris(policy.purpose)

        offer_id = f"urn:offer:{self.participant_id}:{dataset_key.replace('.', ':')}"

        permissions = [
            self._build_permission(
                action, access_level, rule.access_requirements, purposes, policy, rule
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

    def _build_permission(
        self,
        action: str,
        access_level: str,
        access_requirements: str | None,
        purposes: list[str],
        policy: Any,
        rule: GovernanceRuleV2,
    ) -> dict[str, Any]:
        p = self.profile
        constraints: list[dict[str, Any]] = []

        # Membership constraint — driven by access_requirements when set, else by access_level
        reqs = access_requirements or "all"
        needs_membership = reqs in ("partner", "contract") or access_level in (
            "internal",
            "restricted",
        )
        if needs_membership:
            scope = policy.audience.required_scope
            if rule.ownership:
                owner_alias = rule.ownership[0].name
                if reqs == "partner":
                    scope = f"owner:{owner_alias}:partner"
                else:
                    scope = f"owner:{owner_alias}:member"
            constraints.append(
                {
                    "odrl:leftOperand": {"@id": p.term(p.membership_operand)},
                    "odrl:operator": {"@id": "odrl:eq"},
                    "odrl:rightOperand": {"@value": scope, "@type": "xsd:string"},
                }
            )

        # Contract gate — `access_requirements: contract`, `access_level:
        # restricted`, or an explicit `obligations.contract_required`. The EDC
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
            or policy.obligations.contract_required
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
        ob = rule.policy.obligations

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
        """Expand ``policy.purpose[]`` to full profile IRIs, order-preserving.

        ``policy.purpose[]`` is the *only* runtime source of a dataset's
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
    # `policy.purpose[]` is the only runtime source. A helper that turns the
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
        policy_id = (
            rule.dataspace.contract.access_policy_id
            or f"{dataset_key.replace('.', '-')}-policy"
        )
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
            "accessPolicyId": ds.contract.access_policy_id or policy_id,
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
