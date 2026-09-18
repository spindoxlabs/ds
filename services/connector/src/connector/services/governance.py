"""Governance YAML → EDC payload service."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ds.governance.mapper import GovernanceMapper
from ds.governance.models import GovernanceRuleV2, OdrlProfile
from ds.governance.resolver import GovernanceResolver
from ds.governance.sharing import SharingOfferCatalogue

from ..schemas.edc import AssetCreate, ContractDefCreate, DataAddress, PolicyCreate


class ConnectorGovernanceMapper:
    """Translates GovernanceRuleV2 into EDC Management API Pydantic objects."""

    def __init__(
        self,
        participant_id: str,
        participant_base_url: str,
        profile: OdrlProfile | None = None,
        owner_did_resolver: Callable[[str], str | None] | None = None,
        participant_did: str | None = None,
        dataspace_uri: str | None = None,
        sharing_offers: SharingOfferCatalogue | None = None,
    ):
        self.participant_id = participant_id
        self.base_url = participant_base_url.rstrip("/")
        # `participant_did` is the ODRL assigner for any dataset whose owner has
        # no DID of its own — that is, the identity a consumer verifies the offer
        # against. `GovernanceMapper` falls back to
        # `did:web:{participant_id}.dataspaces.localhost`, which is the dev
        # domain: a deployment that did not forward `CONNECTOR_PARTICIPANT_DID`
        # published every policy under a DID that resolves to nothing.
        #
        # `dataspace_uri` and `sharing_offers` are what the **access** policy
        # needs: the value of the `memberOf` claim to compare against, and the
        # offers the `odrl:recipient` set is derived from.
        self._mapper = GovernanceMapper(
            participant_id=participant_id,
            base_url=participant_base_url,
            profile=profile,
            owner_did_resolver=owner_did_resolver,
            participant_did=participant_did,
            dataspace_uri=dataspace_uri,
            sharing_offers=sharing_offers,
        )

    def bind_offers(self, catalogue: SharingOfferCatalogue | None) -> None:
        """See `GovernanceMapper.bind_offers`."""
        self._mapper.bind_offers(catalogue)

    @property
    def profile(self) -> OdrlProfile:
        """The active ODRL profile — the taxonomy sync validates purposes against.

        Exposed because the sync-time gate has to check a rule against the *same*
        profile the mapper will use. Reading a second profile would let a dataset
        pass validation and then be mapped against a different vocabulary.
        """
        return self._mapper.profile

    def to_asset_create(self, dataset_key: str, rule: GovernanceRuleV2) -> AssetCreate:
        """The published asset, built by `GovernanceMapper` and typed here.

        **The properties come from the library mapper, not from a second copy.**
        This method used to spell the whole dict out again, and the copies
        disagreed in the way a second copy always eventually does: the library's
        knew `dct:conformsTo` and `dct:references`, this one did not, and *this
        one is the one the sync calls*. So a producer declaring
        `dcat.conforms_to` had it validated, published into the DCAT evidence and
        served at `/ns/{slug}` — and it never reached the DSP catalogue at all,
        which is the one place a consumer discovers it before negotiating.

        Nothing noticed for the reason a second copy is dangerous: every test
        asserting the property is emitted asserted it against the *library*
        mapper's output, which was correct throughout. `ds-e2e --flow
        semantic-model` reads the asset EDC actually holds, and is what found it.

        What stays here is what only the connector knows: the owner alias and its
        resolved DID.
        """
        ds = rule.dataspace
        pfx = self._mapper.profile.prefix

        extra: dict[str, str] = {}
        for k, v in ds.data_address.query_params.items():
            extra[f"queryParam:{k}"] = v

        owner_alias = rule.ownership[0].name if rule.ownership else ""
        owner_did = ""
        if owner_alias and self._mapper.owner_did_resolver:
            owner_did = self._mapper.owner_did_resolver(owner_alias) or ""

        published = self._mapper.to_asset_create(dataset_key, rule)

        return AssetCreate(
            id=published["@id"],
            properties={
                **published["properties"],
                f"{pfx}:owner": owner_alias,
                f"{pfx}:ownerDid": owner_did,
            },
            # Carried through, so a `dct:` property arrives with `dct` declared.
            # Without it EDC keeps the key as an opaque string and the CURIE
            # expands to nothing for whoever reads the catalogue.
            context=published.get("@context"),
            data_address=DataAddress(
                type=ds.data_address.type,
                base_url=ds.data_address.base_url,
                proxy_path=str(ds.data_address.proxy_path).lower(),
                proxy_query_params=str(ds.data_address.proxy_query_params).lower(),
                extra=extra,
            ),
        )

    def to_policy_create(
        self, dataset_key: str, rule: GovernanceRuleV2
    ) -> PolicyCreate:
        """The **contract** policy: the terms a counterparty negotiates against."""
        policy_id = self._mapper.contract_policy_id(dataset_key, rule)

        odrl_offer = self._mapper.to_odrl_offer(dataset_key, rule)
        odrl_set = self._to_edc_policy({**odrl_offer, "@type": "odrl:Set"})
        odrl_set["@id"] = policy_id
        if "odrl:assigner" not in odrl_set:
            odrl_set["odrl:assigner"] = {"@id": self.participant_id}
        odrl_set.pop("odrl:obligation", None)
        odrl_set.pop("odrl:prohibition", None)

        return PolicyCreate(id=policy_id, policy=odrl_set)

    def to_access_policy_create(
        self, dataset_key: str, rule: GovernanceRuleV2
    ) -> PolicyCreate:
        """The **access** policy: who is admitted to see and ask for the asset.

        A separate PolicyDefinition, referenced by the contract definition's
        `accessPolicyId`. EDC evaluates it in the `catalog` scope, so a
        counterparty the recipient set excludes never sees the dataset in a
        catalogue and is refused if it asks for it by id anyway.
        """
        policy_id = self._mapper.access_policy_id(dataset_key, rule)
        odrl_set = self._to_edc_policy(
            self._mapper.to_access_odrl_set(dataset_key, rule)
        )
        odrl_set["@id"] = policy_id
        if "odrl:assigner" not in odrl_set:
            odrl_set["odrl:assigner"] = {"@id": self.participant_id}
        return PolicyCreate(id=policy_id, policy=odrl_set)

    def to_contract_definition(
        self,
        dataset_key: str,
        rule: GovernanceRuleV2,
        policy_id: str,
        asset_id: str,
        access_policy_id: str | None = None,
    ) -> ContractDefCreate:
        ds = rule.dataspace
        # **Not `access_policy_id`** — `GOV-12`, which the library mapper fixed
        # and this copy did not: the contract definition took the same `@id` as
        # the policy whenever a deployment named one, so the id stopped saying
        # which entity was meant.
        contract_id = (
            ds.contract.contract_definition_id
            or f"{dataset_key.replace('.', '-')}-contract"
        )
        return ContractDefCreate(
            id=contract_id,
            access_policy_id=access_policy_id
            or self._mapper.access_policy_id(dataset_key, rule),
            contract_policy_id=ds.contract.contract_policy_id or policy_id,
            assets_selector=[
                {
                    "@type": "CriterionDto",
                    "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
                    "operator": "=",
                    "operandRight": asset_id,
                }
            ],
        )

    # `_infer_medallion` lived here too, character for character identical to
    # `GovernanceMapper`'s. It went with the property dict it served: two copies
    # of one rule stay equal only until one of them is edited.

    @classmethod
    def _to_edc_policy(cls, value):
        """Compact ODRL term objects where EDC's v3 policy validator expects strings."""
        if isinstance(value, list):
            return [cls._to_edc_policy(item) for item in value]
        if not isinstance(value, dict):
            return value

        result = {key: cls._to_edc_policy(item) for key, item in value.items()}
        result.pop("odrl:duty", None)
        for key in ("odrl:leftOperand",):
            nested = result.get(key)
            if isinstance(nested, dict) and "@id" in nested:
                result[key] = nested["@id"]
        constraints = result.get("odrl:constraint")
        if isinstance(constraints, list):
            result["odrl:constraint"] = [
                cls._to_edc_constraint(constraint)
                for constraint in constraints
                if not (
                    isinstance(constraint, dict)
                    and constraint.get("odrl:leftOperand") == "ds:consentStatus"
                )
            ]
        return result

    #: ``odrl:purpose`` in absolute form. The compact form must not reach EDC:
    #: it is stored verbatim as the left operand and then treated as an IRI
    #: whose scheme is ``odrl``, which JSON-LD refuses to compact
    #: (IRI_CONFUSED_WITH_PREFIX) — taking the whole DSP catalogue response down
    #: with a 500. Every other operand the mapper emits is already absolute.
    PURPOSE_OPERAND = "http://www.w3.org/ns/odrl/2/purpose"

    #: ``odrl:recipient`` in absolute form, for exactly the reasons above: it is
    #: an ODRL term whose compact spelling EDC would store verbatim and then fail
    #: to compact. The right operand is a list of participant DIDs, flattened to
    #: plain strings because that is what ``RecipientFunction`` compares
    #: ``ParticipantAgent.getIdentity()`` against.
    RECIPIENT_OPERAND = "http://www.w3.org/ns/odrl/2/recipient"

    _IRI_OPERANDS = {
        "odrl:purpose": PURPOSE_OPERAND,
        PURPOSE_OPERAND: PURPOSE_OPERAND,
        "odrl:recipient": RECIPIENT_OPERAND,
        RECIPIENT_OPERAND: RECIPIENT_OPERAND,
    }

    @classmethod
    def _to_edc_constraint(cls, constraint):
        """Make an IRI-valued constraint safe for EDC's policy store and serialiser.

        The public ODRL offer keeps the idiomatic ``odrl:purpose`` and
        ``{"@id": <iri>}`` forms, because a purpose *is* an IRI reference and the
        offer carries an ``@context`` that defines the prefix. EDC has neither
        luxury: it stores operands as literals and re-serialises them, so the
        left operand is expanded to an absolute IRI and the right operand
        flattened to plain strings — which is also the shape
        ``ConsentStatusFunction`` reads the negotiated purposes back out of.

        ``odrl:recipient`` goes through the same treatment. It arrived later and
        by a different route (the access policy, not the offer), which is exactly
        how a second operand ends up with a second, subtly different flattener.
        """
        if not isinstance(constraint, dict):
            return constraint
        expanded = cls._IRI_OPERANDS.get(constraint.get("odrl:leftOperand"))
        if expanded is None:
            return constraint

        right = constraint.get("odrl:rightOperand")
        if isinstance(right, dict) and "@id" in right:
            right = right["@id"]
        elif isinstance(right, list):
            right = [
                item["@id"] if isinstance(item, dict) and "@id" in item else item
                for item in right
            ]
        return {
            **constraint,
            "odrl:leftOperand": expanded,
            "odrl:rightOperand": right,
        }


def load_exposed_datasets(
    governance_yaml_path: str,
    overlay_name: str | None = None,
) -> dict[str, GovernanceRuleV2]:
    """Load governance.yaml (with optional overlay) and return datasets
    where expose: true and access_level != secret."""
    path = Path(governance_yaml_path)
    resolver = GovernanceResolver.from_file_with_override(
        path, overlay_name=overlay_name
    )
    result: dict[str, GovernanceRuleV2] = {}
    for key in resolver.config.sources:
        rule = resolver.resolve(key)
        if rule.dataspace.expose and rule.access_level != "secret":
            result[key] = rule
    return result


def owner_by_edc_id(
    governance_yaml_path: str, overlay_name: str | None = None
) -> dict[str, str]:
    """Map every EDC object id this connector publishes to its owning organisation.

    EDC labels **assets** with `ds:owner`, so an asset can be owner-scoped by
    reading the object itself. Policy definitions and contract definitions carry no
    such property — but they are not anonymous either: their ids are *derived from
    the dataset key* (`{key}-policy`, `{key}-contract`, or the explicit override in
    `dataspace.contract`), which is exactly the mapping needed, in the one place
    that already knows both sides.

    The alternative — asking EDC — does not work: a contract definition references
    assets only through a selector, and a policy definition references nothing at
    all. Governance is the only thing that knows a policy belongs to an owner.

    Unowned datasets are omitted rather than mapped to `""`, so a caller cannot
    tell "unowned" from "unknown id" by the shape of the result.
    """
    index: dict[str, str] = {}
    for key, rule in load_exposed_datasets(
        governance_yaml_path, overlay_name=overlay_name
    ).items():
        owner = rule.ownership[0].name if rule.ownership else ""
        if not owner:
            continue
        ds = rule.dataspace
        policy_id = ds.contract.contract_policy_id or f"{key.replace('.', '-')}-policy"
        access_policy_id = (
            ds.contract.access_policy_id or f"{key.replace('.', '-')}-access-policy"
        )
        contract_id = (
            ds.contract.contract_definition_id or f"{key.replace('.', '-')}-contract"
        )
        for object_id in (policy_id, access_policy_id, contract_id):
            if object_id:
                index[object_id] = owner
    return index
