from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
import jwt
from ds.governance import (
    DIRECT_USER_MATCH,
    DataplaneDecision,
    DataplaneRowFilter,
)
from ds_auth.production import ProductionGuard
from ds_auth.service_token import ServiceTokenProvider
from ds_obs import configure_logging, install_metrics
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATASET_API_", extra="ignore")

    connector_internal_url: str = "http://172.17.0.1:30001"
    # This service's own identity on ds-connector's /internal/* API.
    # `svc-ds-dataset-api` holds `connector.internal` with `svc-ds-connector` in
    # its audience. This replaced `connector_api_key`, which was the same value
    # as EDC's Management API key — one secret across two trust boundaries.
    keycloak_token_url: str = (
        "http://172.17.0.1:9080/realms/dataspaces/protocol/openid-connect/token"
    )
    service_client_id: str = "svc-ds-dataset-api"
    service_client_secret: str = "svc-ds-dataset-api"
    external_query_url: str | None = None
    extra_datasets_path: str | None = None
    # Verify the EDR token's signature against ds's JWKS proxy. Off only for a
    # stack whose EDC JWKS is unreachable; `_check_production_config` refuses it
    # in production, because with it off a bearer string is an assertion.
    verify_edr: bool = True


settings = Settings()

# Before anything in this process logs. Unconfigured, the root logger drops
# INFO, so every `log.info` here reached nobody and only failures were visible.
configure_logging("dataset-api-mock")

app = FastAPI(title="dataset-api-mock", version="0.1.0")
install_metrics(app, "dataset-api")

_token_provider = ServiceTokenProvider(
    token_url=settings.keycloak_token_url,
    client_id=settings.service_client_id,
    client_secret=settings.service_client_secret,
)


def _check_production_config() -> None:
    """Refuse to run with the dev client secret when ``DS_ENV=production``.

    A weak secret still authenticates, so nothing about a running system would
    look wrong. Registering it here is what makes the omission loud.
    """
    guard = ProductionGuard("dataset-api")
    guard.forbid_default(
        "DATASET_API_SERVICE_CLIENT_SECRET",
        settings.service_client_secret,
        {"svc-ds-dataset-api"},
        "Set the Keycloak client secret for svc-ds-dataset-api.",
    )
    if not settings.verify_edr:
        guard.forbid_default(
            "DATASET_API_VERIFY_EDR",
            "false",
            {"false"},
            "Nothing else validates the EDR token in this topology — with "
            "verification off, any bearer string names any consumer.",
        )
    guard.enforce()


_check_production_config()


# A handler this data plane implements, named here and nowhere else.
#
# **Handler names do not belong in `ds.governance`.** ds passes the string
# through from `governance.yaml` and never interprets it — `DataplaneRowFilter`
# says so where it declares `args` open, "a handler defines its own arguments and
# the PDP does not interpret them". Which registry resolves a principal to column
# values is a property of the data plane holding the data, so a control-plane
# library enumerating handlers would invite ds to reason about one.
#
# The two ends agree through `governance.yaml`, which is the producer's
# declaration and the actual source of truth: the connector reads the handler
# from it, and this plane must recognise what it reads.
# `tests/test_dataset_fixtures.py` checks that against the file rather than
# against a shared constant.
#
# `DIRECT_USER_MATCH` is imported rather than spelled here for the one reason
# that does not apply to this: it is named by
# `celine-utils/schema/governance.schema.json` and is what the legacy
# `user_filter_column` spelling migrates to, so it is part of the shape itself.
REC_REGISTRY = "rec_registry"


# The REC registry, collapsed into a fixture.
#
# The real data plane resolves a `rec_registry` filter against two systems: the
# identity-registry bridges a subject DID to the Keycloak username ds sends as a
# *principal*, and the REC registry resolves that member to the meters they own.
# A stand-in has neither behind it, so both hops live here — and the member and
# sensor ids are `fixtures/ds_e2e_rec.yaml`'s, so a query answers the same
# whichever backend holds :30002.
#
# `ds-e2e-METER-9999` deliberately belongs to nobody: a run that returns it has
# lost the filter, and that must look like a failure rather than a bigger result.
REC_MEMBERS: dict[str, dict[str, list[str]]] = {
    "subject@example.test": {
        "dids": ["did:web:rec.dataspaces.localhost:users:data-subject"],
        "devices": ["ds-e2e-METER-0001"],
    },
    "dual@example.test": {
        "dids": ["did:web:rec.dataspaces.localhost:users:dual-user"],
        "devices": ["ds-e2e-METER-0002"],
    },
}


DATASETS: dict[str, dict[str, Any]] = {
    "datasets.gold.om_weather_features": {
        "asset_id": "datasets.gold.om_weather_features",
        "requires_consent": False,
        "rows": [
            {"timestamp": "2026-05-11T08:00:00Z", "location": "EC-001",
             "temperature_c": 18.7, "wind_ms": 2.8, "ghi": 426},
            {"timestamp": "2026-05-11T08:15:00Z", "location": "EC-001",
             "temperature_c": 18.9, "wind_ms": 2.6, "ghi": 441},
            {"timestamp": "2026-05-11T08:30:00Z", "location": "EC-001",
             "temperature_c": 19.1, "wind_ms": 2.5, "ghi": 455},
        ],
    },
    # Declared exactly as `services/connector/governance-rec/governance.yaml`
    # declares it: a `rec_registry` filter on `device_id`. It used to key rows by
    # subject DID in a column `sub`, which no decision could ever narrow — ds
    # sends registry-native principals for a handler this fixture did not
    # implement, against a column these rows did not have, so the one
    # consent-gated dataset in the platform was unserveable here.
    "datasets.silver.meters_15m": {
        "asset_id": "datasets.silver.meters_15m",
        "requires_consent": True,
        # **The model these columns mean, stated by the thing that renders them.**
        #
        # `governance.yaml`'s `dcat.conforms_to` says what the *producer declares*
        # and is what ds publishes into the DSP catalogue. This says what the data
        # plane actually serves. They are two holders of one fact, and until both
        # existed nothing could compare them — a producer could declare SAREF4ENER
        # and return whatever it liked, with `dct:conformsTo` an unverified claim
        # in the catalogue (rulebook `data-models.md` §3, `T-3`).
        #
        # The IRI belongs to the *participant*, not to ds and not to a standards
        # body: this is the REC's own model for its own response shape, served by
        # the REC's own connector at `/ns/{slug}`. A deployment aligning to
        # SAREF4ENER or CIM registers that IRI here instead — the mechanism does
        # not care which, and `M-6` is why ds must not.
        "conforms_to": "https://rec.dataspaces.localhost/ns/meter-readings",
        # **What each column means**, in the shape the real plane derives
        # `/vocabulary` from — a mapping spec, `source` naming the column this
        # fixture actually returns and `target` the term it carries. The real
        # dataset-api resolves this from `governance.yaml`'s `ontology.spec` or
        # `ontology.spec_file` at export; there is no exporter here, so the
        # resolved form is what the fixture holds.
        #
        # Note `device_id` → `deviceId`. The column and the term are *not* the
        # same string, and that is the whole reason the route exists: a consumer
        # reading rows cannot guess the mapping from the payload, and a JSON
        # Schema of the columns would not tell it either.
        "ontology": {
            "target_type": "https://rec.dataspaces.localhost/ns/meter-readings",
            "fields": [
                {
                    "source": "timestamp",
                    "target": "https://rec.dataspaces.localhost/ns/meter-readings#timestamp",
                    "datatype": "xsd:dateTime",
                },
                {
                    "source": "device_id",
                    "target": "https://rec.dataspaces.localhost/ns/meter-readings#deviceId",
                    "datatype": "xsd:string",
                },
                {
                    "source": "kwh",
                    "target": "https://rec.dataspaces.localhost/ns/meter-readings#kwh",
                    "datatype": "xsd:decimal",
                },
            ],
        },
        "row_filters": [{"handler": REC_REGISTRY, "args": {"column": "device_id"}}],
        "rows": [
            {"timestamp": "2026-05-11T08:00:00Z", "device_id": "ds-e2e-METER-0001", "kwh": 0.42},
            {"timestamp": "2026-05-11T08:15:00Z", "device_id": "ds-e2e-METER-0001", "kwh": 0.37},
            {"timestamp": "2026-05-11T08:00:00Z", "device_id": "ds-e2e-METER-0002", "kwh": 0.55},
            {"timestamp": "2026-05-11T08:15:00Z", "device_id": "ds-e2e-METER-0002", "kwh": 0.51},
            {"timestamp": "2026-05-11T08:00:00Z", "device_id": "ds-e2e-METER-9999", "kwh": 9.99},
        ],
    },
    # **The second provider's dataset** (`D-54`, `DID-15`). The grid operator
    # publishes the state of the grid it operates: no data subject in it, so no
    # consent, no row filter and no member registry behind it. Its presence here
    # is what lets a consumer negotiate with *two* counterparties for two
    # differently-shaped datasets — the first fixture in this repository where
    # "which provider" is a question rather than a default.
    #
    # Served by this same stand-in: in a deployment it is the DSO's own system,
    # and here the asset id is what routes the query.
    "datasets.gold.grid_capacity": {
        "asset_id": "datasets.gold.grid_capacity",
        "requires_consent": False,
        # A second participant, a second model, served by that participant. The
        # point of two is that neither is the platform's: `conforms_to` is per
        # dataset and per producer, and two producers in one dataspace declaring
        # different models is the normal case, not a conflict to resolve.
        "conforms_to": "https://grid-operator.dataspaces.localhost/ns/grid-capacity",
        "ontology": {
            "target_type": "https://grid-operator.dataspaces.localhost/ns/grid-capacity",
            "fields": [
                {
                    "source": "timestamp",
                    "target": "https://grid-operator.dataspaces.localhost/ns/grid-capacity#timestamp",
                    "datatype": "xsd:dateTime",
                },
                {
                    "source": "substation",
                    "target": "https://grid-operator.dataspaces.localhost/ns/grid-capacity#substation",
                    "datatype": "xsd:string",
                },
                {
                    "source": "headroom_kw",
                    "target": "https://grid-operator.dataspaces.localhost/ns/grid-capacity#headroomKw",
                    "datatype": "xsd:decimal",
                },
                {
                    "source": "load_kw",
                    "target": "https://grid-operator.dataspaces.localhost/ns/grid-capacity#loadKw",
                    "datatype": "xsd:decimal",
                },
            ],
        },
        "rows": [
            {"timestamp": "2026-05-11T08:00:00Z", "substation": "SS-014",
             "headroom_kw": 320.5, "load_kw": 179.5},
            {"timestamp": "2026-05-11T09:00:00Z", "substation": "SS-014",
             "headroom_kw": 288.0, "load_kw": 212.0},
            {"timestamp": "2026-05-11T08:00:00Z", "substation": "SS-027",
             "headroom_kw": 96.2, "load_kw": 403.8},
        ],
    },
}


def _load_extra_datasets(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise RuntimeError(f"Extra dataset file not found: {dataset_path}")
    payload = json.loads(dataset_path.read_text())
    datasets = payload.get("datasets", payload)
    if not isinstance(datasets, dict):
        raise RuntimeError("Extra dataset file must contain a dataset object")
    for name, spec in datasets.items():
        _validate_dataset(name, spec)
    return datasets


def _validate_dataset(name: str, spec: dict[str, Any]) -> None:
    """Refuse a dataset that does not say enough about itself to be served.

    **`requires_consent` is mandatory and is not defaulted.** Reading an absent
    one as `False` is the fail-open direction: it would publish a PII dataset as
    open and serve every row unfiltered, and a missing key is exactly how that
    arrives. `asset_id` likewise — it is what the agreement names, so a wrong or
    absent one makes every verdict about some other dataset.

    A local dataset must carry `rows`; an external one names its query instead.
    Both used to be read with `spec["…"]`, so an extra dataset omitting either
    became a `KeyError` — a 500 out of `/catalogue`, which is unauthenticated
    and is the first thing the portal calls.
    """
    if not isinstance(spec, dict):
        raise RuntimeError(f"Dataset {name!r} must be an object")
    if "requires_consent" not in spec:
        raise RuntimeError(
            f"Dataset {name!r} does not declare `requires_consent`. It has no default: "
            "an absent one would publish a consent-gated dataset as open."
        )
    if not spec.get("asset_id"):
        raise RuntimeError(f"Dataset {name!r} declares no `asset_id`")
    if spec.get("source") == "external":
        if not spec.get("external_sql"):
            raise RuntimeError(f"External dataset {name!r} declares no `external_sql`")
    elif not isinstance(spec.get("rows"), list):
        raise RuntimeError(f"Dataset {name!r} declares no `rows`")
    # A mapping is optional — a dataset stating no semantic model is a legitimate
    # claim. A *malformed* one is not: every field is read by attribute below, so
    # it would surface as a 500 out of `/vocabulary`, which is unauthenticated
    # and reads to a consumer as the participant's fault rather than the
    # fixture's. Same argument as `rows` and `requires_consent` above.
    ontology = spec.get("ontology")
    if ontology is not None:
        fields = ontology.get("fields") if isinstance(ontology, dict) else None
        if not isinstance(fields, list) or not fields:
            raise RuntimeError(
                f"Dataset {name!r} declares an `ontology` with no `fields`; a mapping "
                "that maps no column describes nothing."
            )
        for field in fields:
            if not isinstance(field, dict) or not field.get("source") or not field.get("target"):
                raise RuntimeError(
                    f"Dataset {name!r} has an ontology field without both `source` "
                    f"(the column) and `target` (the term it carries): {field!r}"
                )
    if spec["requires_consent"] and not _row_filter_spec(spec):
        raise RuntimeError(
            f"Dataset {name!r} requires consent but declares no row filter. ds narrows "
            "these rows by one, so a dataset without one can only be served whole."
        )


def _row_filter_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    """The dataset's own row filter, as `governance.yaml` declares one.

    `subject_column` is the older spelling and still works for an extra dataset
    file: it means `direct_user_match` on that column. Both are read through here
    so nothing downstream has to know which was used.
    """
    for row_filter in spec.get("row_filters") or []:
        if row_filter.get("handler"):
            return row_filter
    column = spec.get("subject_column")
    if column:
        return {"handler": DIRECT_USER_MATCH, "args": {"column": column}}
    return None


DATASETS.update(_load_extra_datasets(settings.extra_datasets_path))
for _name, _spec in DATASETS.items():
    _validate_dataset(_name, _spec)


def _catalogue_entry(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    medallion = "gold" if ".gold." in name else "silver" if ".silver." in name else "bronze"
    access_level = "restricted" if spec["requires_consent"] else "internal"
    keywords = [medallion]
    if spec["requires_consent"]:
        keywords.extend(["pii", "consent"])

    return {
        "@id": spec["asset_id"],
        "id": spec["asset_id"],
        "name": name,
        "asset_id": spec["asset_id"],
        "dct:title": name.replace("_", " ").replace(".", " / "),
        "title": name,
        "dct:description": (
            "Consent-protected smart meter sample rows."
            if spec["requires_consent"]
            else "Open weather feature sample rows."
        ),
        "description": (
            "Consent-protected smart meter sample rows."
            if spec["requires_consent"]
            else "Open weather feature sample rows."
        ),
        "dcat:keyword": keywords,
        # Absent rather than null when the dataset declares none: a dataset that
        # states no model and a dataset that states "no model" are different
        # claims, and only the first is what an undeclared one means.
        **(
            {"dct:conformsTo": {"@id": spec["conforms_to"]}}
            if spec.get("conforms_to")
            else {}
        ),
        "access_level": access_level,
        "requires_consent": spec["requires_consent"],
        # An external dataset holds no rows here; its count is the upstream's and
        # is not worth a call from a catalogue listing.
        "rows": len(spec.get("rows") or []),
        "odrl:hasPolicy": {
            "@type": "odrl:Offer",
            "odrl:permission": [
                {
                    "odrl:action": "use",
                    "odrl:constraint": [
                        {
                            "odrl:leftOperand": "ds:consentStatus",
                            "odrl:operator": "odrl:eq",
                            "odrl:rightOperand": "granted",
                        }
                    ]
                    if spec["requires_consent"]
                    else [],
                }
            ],
        },
    }


# The prefixes a fixture mapping may use in a `datatype`. The real plane resolves
# these through the `celine-ontologies` registry, which knows every vocabulary in
# the ecosystem; a stand-in serving three fixture datasets needs the two its own
# documents can contain, and an unknown one is refused rather than emitted (see
# `_vocabulary_document`) — an unexpandable CURIE in a context is not a smaller
# failure than a missing one, it is the same failure found by the consumer.
_PREFIXES = {
    "dct": "http://purl.org/dc/terms/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


def _vocabulary_document(spec: dict[str, Any]) -> dict[str, Any]:
    """The JSON-LD document `/catalogue/{id}/vocabulary` serves for one dataset.

    Derived from the dataset's mapping, never written beside it. That is the
    load-bearing property of the seam rather than an implementation preference:
    a hand-maintained response would be a third holder of one fact, next to the
    mapping and the rows, and this whole route exists because two holders with
    nothing comparing them had already drifted.

    Keyed by **source column**, so the context lines up with what `/query`
    actually returns — a consumer applies it to a row unchanged.
    """
    mapping = spec["ontology"]
    context: dict[str, Any] = {}
    used: set[str] = set()

    for field in mapping.get("fields") or []:
        term: dict[str, str] = {"@id": field["target"]}
        if datatype := field.get("datatype"):
            term["@type"] = datatype
            if ":" in datatype and "://" not in datatype:
                used.add(datatype.partition(":")[0])
        context[field["source"]] = term

    document: dict[str, Any] = {"@context": context}
    if target_type := mapping.get("target_type"):
        document["@type"] = target_type
    if conforms_to := spec.get("conforms_to"):
        # The same IRI the catalogue entry carries. A dataset cannot advertise
        # one model here and another there — which is the thing the contract
        # check compares, so the two must come from one field.
        used.add("dct")
        document["dct:conformsTo"] = {"@id": conforms_to}

    if unknown := used - set(_PREFIXES):
        raise HTTPException(500, f"Mapping uses undeclared prefixes: {sorted(unknown)}")
    # Prefixes first, and only the ones in play: a document using none of Dublin
    # Core should not declare it.
    return {"@context": {**{p: _PREFIXES[p] for p in sorted(used)}, **context},
            **{k: v for k, v in document.items() if k != "@context"}}


def _dataset_enabled(spec: dict[str, Any]) -> bool:
    return spec.get("source") != "external" or bool(settings.external_query_url)


def _enabled_datasets() -> dict[str, dict[str, Any]]:
    return {name: spec for name, spec in DATASETS.items() if _dataset_enabled(spec)}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/datasets")
async def datasets() -> dict[str, list[dict[str, Any]]]:
    return {
        "datasets": [
            {
                "name": name,
                "asset_id": spec["asset_id"],
                "requires_consent": spec["requires_consent"],
                "rows": len(spec.get("rows") or []),
            }
            for name, spec in _enabled_datasets().items()
        ]
    }


@app.get("/subjects/{subject_id}/datasets")
async def subject_datasets(subject_id: str) -> dict[str, Any]:
    """Return datasets containing data owned by a data subject.

    This endpoint is the data adapter's inventory view. It does not grant
    access; sharing is still enforced by ds-connector consent checks.
    """
    owned: list[dict[str, Any]] = []
    for name, spec in _enabled_datasets().items():
        row_filter = _row_filter_spec(spec)
        if not row_filter:
            continue
        subject_column = row_filter["args"].get("column")
        if not subject_column:
            continue

        # The caller names the person as the dataspace does — by DID — while the
        # rows are keyed by whatever the *handler* resolves from them. Asking the
        # handler is the whole point: a `rec_registry` dataset keys rows by
        # device, so comparing the DID to the column directly finds nothing and
        # reports the subject owns no data.
        values = _handler_values(row_filter["handler"], [subject_id])
        sample_rows = list(spec.get("rows") or [])
        subject_match = spec.get("subject_id") == subject_id or any(
            row.get(subject_column) in values for row in sample_rows
        )
        if not subject_match:
            continue

        owned.append({
            "name": name,
            "asset_id": spec["asset_id"],
            "title": name.replace("_", " ").replace(".", " / "),
            "requires_consent": spec["requires_consent"],
            "subject_column": subject_column,
            "sample_rows": sum(1 for row in sample_rows if row.get(subject_column) in values),
            "source": spec.get("source", "local"),
        })
    return {"subject_id": subject_id, "datasets": owned}


def _handler_values(handler: str, principals: list[str]) -> set[str]:
    """The column values `principals` admit, under `handler`.

    This is the one piece of a row filter the PDP cannot compute: it names the
    people, and the handler knows how a person maps to values in the column.

    An unknown handler yields the empty set, and every caller reads that as
    *these rows and no others* — never as *no filter*. That direction is not
    symmetric: withholding rows from someone entitled to them is a bug report,
    while serving rows for a narrowing this plane could not apply is a breach.
    """
    if handler == DIRECT_USER_MATCH:
        # The column holds the principal itself, so there is nothing to resolve.
        return set(principals)
    if handler == REC_REGISTRY:
        # Keyed by username, because that is what ds sends as a principal. The
        # DIDs are accepted too so `/subjects/{did}/datasets` can use the same
        # resolution — that route is the subject's own inventory view and names
        # them the way the portal holds them.
        values: set[str] = set()
        for username, member in REC_MEMBERS.items():
            if username in principals or set(member["dids"]) & set(principals):
                values.update(member["devices"])
        return values
    return set()


@app.get("/catalogue")
async def catalogue() -> dict[str, list[dict[str, Any]]]:
    return {"datasets": [_catalogue_entry(name, spec) for name, spec in _enabled_datasets().items()]}


@app.get("/catalogue/{asset_id:path}/vocabulary")
async def catalogue_vocabulary(asset_id: str) -> Response:
    """What this dataset's columns mean — the semantic sibling of `/schema`.

    **Declared before `/catalogue/{asset_id:path}`, and that is not cosmetic.**
    FastAPI matches in declaration order and the sibling route's `:path`
    converter is greedy, so with the order reversed this path is swallowed as an
    asset id ending in `/vocabulary` and answers 404 — which reads as "this
    dataset declares no model" and is the one wrong answer this route can give.

    Unauthenticated, like `/catalogue`: a consumer decides whether it *can* use a
    dataset before it negotiates for it, so gating the vocabulary would gate
    discovery. It describes the shape of the data, not the data.

    404 means the dataset is unknown **or** declares no mapping. That is not the
    same claim as "this dataset has no semantic model"; the catalogue entry's
    `dct:conformsTo` is where a declared model is stated, and its absence there
    is what silence means.
    """
    for name, spec in _enabled_datasets().items():
        if asset_id in {name, spec["asset_id"]}:
            if not spec.get("ontology"):
                raise HTTPException(404, f"Dataset {asset_id!r} declares no semantic model")
            # `application/ld+json` explicitly: FastAPI would serve
            # `application/json` for a returned dict, and a consumer
            # content-negotiating for JSON-LD would skip it.
            return Response(
                content=json.dumps(_vocabulary_document(spec), ensure_ascii=False),
                media_type="application/ld+json",
            )
    raise HTTPException(404, f"Unknown asset {asset_id!r}")


@app.get("/catalogue/{asset_id:path}")
async def catalogue_item(asset_id: str) -> dict[str, Any]:
    for name, spec in _enabled_datasets().items():
        if asset_id in {name, spec["asset_id"]}:
            return _catalogue_entry(name, spec)
    raise HTTPException(404, f"Unknown asset {asset_id!r}")


class DatasetQueryModel(BaseModel):
    """Mirrors `celine.dataset.schemas.dataset_query.DatasetQueryModel`.

    Field for field, including the defaults. A mock whose request model differs
    from the real one validates a contract nobody runs.
    """

    sql: str | None = None
    limit: int = 100
    offset: int = 0
    skip_count: bool = False


class DatasetQueryResult(BaseModel):
    """Mirrors `celine.dataset.schemas.dataset_query.DatasetQueryResult`."""

    items: list[dict[str, Any]]
    offset: int
    limit: int
    count: int
    total: int | None = None


@app.post("/query", response_model=DatasetQueryResult)
async def query(
    body: DatasetQueryModel,
    authorization: str | None = Header(default=None),
    edc_contract_agreement_id: str | None = Header(default=None),
    edc_transfer_process_id: str | None = Header(default=None),
    edc_purpose: str | None = Header(default=None),
) -> DatasetQueryResult:
    """Query datasets — in dataspace mode, or the way this service always worked.

    **`Edc-Contract-Agreement-Id` present → dataspace mode.** Absent → the plain
    path, which is what a non-dataspace deployment runs today and which this
    change must not disturb.

    Dataspace mode never falls back to the plain path on failure. A fallback
    between two authorization regimes is a bypass with extra steps.

    The datasets come from the query itself, never from a parameter: what a
    caller may read is decided by ds from the agreement, and letting the caller
    *name* the dataset alongside it invites the two to disagree.
    """
    dataset_names = _datasets_in_sql(body.sql)
    if not dataset_names:
        raise HTTPException(400, "No known dataset referenced in the query")

    if len(dataset_names) > 1:
        # ds authorises every dataset the statement touches, and this plane used
        # to serve `dataset_names[0]` regardless — so a join asked about two and
        # got one, silently, with the audit event naming only the one served.
        # This mock cannot execute a join; refusing says so, where picking the
        # first says nothing and looks like an answer.
        raise HTTPException(
            400,
            "This data plane serves one dataset per statement, and this one names "
            f"{len(dataset_names)}: {', '.join(sorted(dataset_names))}",
        )

    if edc_contract_agreement_id is None:
        return await _plain_query(dataset_names, body)

    return await _dataspace_query(
        dataset_names,
        body,
        bearer=authorization,
        agreement_id=edc_contract_agreement_id,
        transfer_id=edc_transfer_process_id,
        purpose=edc_purpose,
    )


def _datasets_in_sql(sql: str | None) -> list[str]:
    """Which known datasets does this statement touch?

    The real service resolves them through the catalogue and its SQL parser;
    the FIWARE/QuantumLeap module resolves them its own way. Matching known
    names against the statement is the mock's equivalent — the *contract* is
    "the query says which datasets", and that is what has to be identical.

    **Not `name in sql`.** Plain containment let a comment, a string literal or a
    longer identifier select a dataset: `-- see datasets.silver.meters_15m` named
    it, and so did `WHERE note = 'datasets.silver.meters_15m'` and a table called
    `datasets.silver.meters_15m_v2`. That decides which asset id goes to
    `authorize`, so it decides which agreement and which consent pool answer —
    a caller who could steer it chose the dataset the decision was about while
    the statement read from another.

    Comments and single-quoted literals are removed first, then each known name
    must appear delimited: no identifier character and no dot on either side.
    Double-quoted text is left alone — in SQL that is a quoted identifier, so
    `"datasets.silver.meters_15m"` is a genuine reference to it.
    """
    if not sql:
        return []
    statement = _strip_sql_noise(sql)
    return [
        name
        for name in _enabled_datasets()
        if re.search(rf"(?<![\w.]){re.escape(name)}(?![\w.])", statement)
    ]


def _strip_sql_noise(sql: str) -> str:
    """`sql` with comments and single-quoted literals blanked out.

    Blanked rather than deleted, so nothing on either side of a removed run is
    joined into a new identifier.
    """
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    return re.sub(r"'(?:[^']|'')*'", " ", without_line)


async def _rows_for(dataset_names: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    name = dataset_names[0]
    spec = DATASETS[name]
    rows = (
        await _query_external(spec)
        if spec.get("source") == "external"
        else list(spec["rows"])
    )
    return rows, spec


def _page(rows: list[dict[str, Any]], body: DatasetQueryModel) -> DatasetQueryResult:
    window = rows[body.offset : body.offset + body.limit]
    return DatasetQueryResult(
        items=window,
        offset=body.offset,
        limit=body.limit,
        count=len(window),
        total=None if body.skip_count else len(rows),
    )


async def _plain_query(dataset_names: list[str], body: DatasetQueryModel) -> DatasetQueryResult:
    """Non-dataspace mode: no ds involvement at all, by design.

    **A consent-gated dataset is not reachable this way.** Omitting
    `Edc-Contract-Agreement-Id` used to select a path that returned every row of
    any enabled dataset — `requires_consent: true` included — with no token, no
    decision and no audit event. That is not a second mode of access, it is the
    absence of one: the header is chosen by the caller, so the gate was opt-in
    for the party it exists to constrain.

    Datasets with no data subject behind them still flow, which is what this path
    is for. A deployment that wants no dataspace at all runs exactly as before;
    one that has consent-gated data now has to prove an agreement to read it.
    """
    gated = [name for name in dataset_names if DATASETS[name]["requires_consent"]]
    if gated:
        raise HTTPException(
            403,
            f"{', '.join(sorted(gated))} is consent-gated and cannot be read without a "
            "contract agreement: send Edc-Contract-Agreement-Id, the EDR token and "
            "Edc-Purpose so ds can decide whose rows may leave",
        )
    rows, _ = await _rows_for(dataset_names)
    return _page(rows, body)


async def _dataspace_query(
    dataset_names: list[str],
    body: DatasetQueryModel,
    *,
    bearer: str | None,
    agreement_id: str,
    transfer_id: str | None,
    purpose: str | None,
) -> DatasetQueryResult:
    consumer_did = await _verified_consumer(bearer)

    decision = await _authorize(
        consumer_did=consumer_did,
        agreement_id=agreement_id,
        transfer_id=transfer_id,
        purpose=[p.strip() for p in (purpose or "").split(",") if p.strip()],
        dataset_ids=[DATASETS[n]["asset_id"] for n in dataset_names],
    )
    if not decision.allowed:
        # The reason is ds's, and it is safe to relay: it names the gate, never
        # who else holds the agreement.
        raise HTTPException(403, f"Refused by ds: {decision.reason}")

    rows, spec = await _rows_for(dataset_names)
    verdict = decision.verdict_for(spec["asset_id"])
    if verdict is None or not verdict.allowed:
        # The envelope allowed, this dataset did not — or ds never mentioned it.
        # Either way nothing here has been permitted to serve it.
        raise HTTPException(
            403, f"Refused by ds: {verdict.reason if verdict else 'dataset_undecided'}"
        )

    if verdict.row_filter is not None:
        rows = _apply_row_filter(rows, verdict.row_filter)

    await _audit_query(
        dataset_id=spec["asset_id"],
        consumer_id=consumer_did,
        subject_id=None,
        agreement_id=agreement_id,
        transfer_id=transfer_id,
        row_count=len(rows),
        # **Deliberately not the filter's principals.** `/internal/audit/query`
        # declares `authorized_subject_ids`, and a PEP structurally cannot fill
        # it: ds translates subject DIDs into registry-native principals before
        # the filter leaves, precisely so a DID does not travel with the payload.
        # Sending the principals instead would put usernames into a `QueryExecuted`
        # provenance event, which rulebook `L-3` limits to codes, pseudonymous
        # DIDs and hashes. The field is the PDP's to fill, not this one's.
        authorized_subject_ids=None,
    )
    return _page(rows, body)


def _apply_row_filter(
    rows: list[dict[str, Any]], row_filter: DataplaneRowFilter
) -> list[dict[str, Any]]:
    """Narrow `rows` to the ones the filter admits.

    The filter arrives whole — handler, args and principals — because the
    handler is what knows how a principal maps to values in the column. This
    service implements two (`direct_user_match`, `rec_registry`); the real
    dataset-api registers several through `celine.dataset...row_filters`.

    **An unimplemented handler withholds every row.** It is not a permission to
    serve unfiltered: an *allow* carrying a filter says "these rows", and a PEP
    that cannot work out which rows has not been told it may serve them all.
    That is the whole failure this shape exists to prevent — the previous reading
    (`row_filter["column"]`) matched no key the connector sends, so the request
    died as a 500 with the narrowing never applied.
    """
    if row_filter.handler not in _IMPLEMENTED_HANDLERS:
        log.warning(
            "No implementation for row filter handler %r — withholding every row",
            row_filter.handler,
        )
        raise HTTPException(
            403,
            f"Cannot enforce row filter handler {row_filter.handler!r}: "
            "this data plane implements no such handler, so no rows may be served",
        )

    column = row_filter.args.get("column")
    if not column:
        raise HTTPException(
            403,
            f"Row filter handler {row_filter.handler!r} names no column to filter on",
        )

    # An empty principal set narrows to nothing. It never widens to everything:
    # ds denies before sending one, and reading it as "no filter" is precisely
    # how a consent-gated dataset leaks. The same holds for a principal the
    # handler cannot resolve — an unknown member owns no devices, so their rows
    # are none, not all.
    values = _handler_values(row_filter.handler, list(row_filter.principals))
    return [row for row in rows if row.get(column) in values]


_IMPLEMENTED_HANDLERS = {DIRECT_USER_MATCH, REC_REGISTRY}


_jwks_cache: dict[str, Any] = {}


async def _verified_consumer(bearer: str | None) -> str:
    """The consumer DID this request proves, from the EDR token's ``aud``.

    **Nothing else validates this token.** The EDC data-plane proxy was removed
    upstream (`data-plane-public-api-v2`, deprecated), so the EDR endpoint we
    hand out *is* this service — there is no proxy in front to check the
    signature. And the token carries no ``exp``
    (`DataPlaneAuthorizationServiceImpl.createTokenParams` at v0.16.0), so a
    leaked one is valid until the agreement behind it is revoked. Verifying it
    here is the only thing standing between a bearer string and somebody's data.

    ``aud`` is the one identity fact that must never come from a header: it is
    what ds checks the agreement against.
    """
    if not settings.verify_edr:
        # Dev escape hatch, off by default and refused in production by the
        # guard above — it exists so a stack without a reachable EDC JWKS can
        # still be brought up, not so a deployment can skip verification.
        return _unverified_aud(bearer)

    token = (bearer or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Dataspace mode requires the EDR token")

    claims = None
    for key in await _verification_keys():
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["ES256", "RS256"],
                options={"verify_aud": False, "verify_exp": False},
            )
            break
        except Exception:  # noqa: BLE001 — try the next key, refuse if none fit
            continue
    if claims is None:
        # Every key in the set is tried rather than the one matching `kid`: EDC
        # sets `kid` to its **vault alias** (`participant-private-key`) while the
        # JWK carries its own (`edr-rec-key-1`), so a kid-indexed lookup
        # never matches. The set is one or two keys, so trying them all costs
        # nothing and survives a rotation that changes either name.
        #
        # Drop the cached set, as `_verification_keys` says it does: the commonest
        # cause of no key fitting is that the provider rotated, and a cache that
        # is never invalidated makes that a restart rather than a retry. It
        # cannot be used to force fetches — reaching here already means the token
        # verified against nothing we hold.
        _jwks_cache.pop("keys", None)
        raise HTTPException(401, "EDR token is not valid")

    audience = claims.get("aud")
    if isinstance(audience, list):
        audience = audience[0] if audience else None
    if not audience:
        raise HTTPException(401, "EDR token names no audience")
    return str(audience)


def _unverified_aud(bearer: str | None) -> str:
    token = (bearer or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Dataspace mode requires the EDR token")
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "EDR token is not a JWT") from exc
    audience = claims.get("aud")
    if isinstance(audience, list):
        audience = audience[0] if audience else None
    if not audience:
        raise HTTPException(401, "EDR token names no audience")
    log.warning("EDR signature NOT verified — DATASET_API_VERIFY_EDR is off")
    return str(audience)


async def _verification_keys() -> list[Any]:
    """The provider's EDR signing keys, via ds.

    ds serves the public half of the vault key EDC signs with
    (`/internal/edr-jwks`), so this service never needs the EDC vault or the
    management credential. Cached after the first fetch; a verification failure
    clears the cache so a rotation does not need a restart.
    """
    from jwt import PyJWK

    if _jwks_cache.get("keys"):
        return _jwks_cache["keys"]

    url = f"{settings.connector_internal_url.rstrip('/')}/internal/edr-jwks"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=await _internal_headers())
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # 502, not the 500 an uncaught `raise_for_status` produced. Both refuse
        # the request, but a 500 says this service is broken when what happened
        # is that ds would not answer — and it is the shape an operator reads to
        # decide which component to look at.
        raise HTTPException(
            502, f"ds-connector would not publish the EDR keys: {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, "ds-connector unreachable for the EDR key set") from exc

    keys = []
    for entry in response.json().get("keys", []):
        try:
            keys.append(PyJWK.from_dict({**entry, "alg": entry.get("alg", "ES256")}).key)
        except Exception:  # noqa: BLE001 — an unusable key is not a fatal one
            log.warning("Unusable JWK in the EDR key set: %s", entry.get("kid"))
    if not keys:
        raise HTTPException(503, "ds published no usable EDR verification key")
    _jwks_cache["keys"] = keys
    return keys


async def _authorize(
    *,
    consumer_did: str,
    agreement_id: str,
    transfer_id: str | None,
    purpose: list[str],
    dataset_ids: list[str],
) -> DataplaneDecision:
    """Ask ds whether rows may flow, and which.

    One call, one decision. This service assembles nothing: agreement validity,
    the agreement↔consumer binding, purpose admissibility and the consent pool
    are all ds's to answer, because ds is the control plane.

    The answer is parsed as `ds.governance.DataplaneDecision` — the shared shape,
    so a change on the connector side that this service has not caught up with
    fails here rather than downstream of the narrowing.
    """
    url = f"{settings.connector_internal_url.rstrip('/')}/internal/dataplane/authorize"
    payload = {
        "consumer_did": consumer_did,
        "agreement_id": agreement_id,
        "transfer_id": transfer_id,
        "purpose": purpose,
        "dataset_ids": dataset_ids,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=await _internal_headers())
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"ds-connector refused the check: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        # ds unreachable is a denial, never an allow: the control plane not
        # answering is exactly when the data plane must not improvise.
        raise HTTPException(502, "ds-connector unreachable") from exc
    try:
        return DataplaneDecision.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        # A decision we cannot read is a decision we did not receive. The
        # tempting alternative — read the keys we recognise and ignore the rest —
        # is what serves rows past a narrowing that arrived under a new name.
        log.error("Unreadable decision from ds-connector: %s", exc)
        raise HTTPException(502, "ds-connector returned an unreadable decision") from exc


async def _internal_headers() -> dict[str, str]:
    """Authenticate to ds-connector's ``/internal/*`` API as this service.

    ``svc-ds-dataset-api`` holds ``connector.internal`` with ``svc-ds-connector``
    in its audience. This replaced the ``X-Api-Key`` the PEP used to send: that
    key is the *same* value as EDC's Management API key, so one leak yielded
    contract administration, the data-plane signing keys behind
    ``/internal/edr-jwks`` and the subject pools behind
    ``/internal/consent/check`` at once — and every caller arrived as the same
    anonymous bearer, so no audit trail could tell the dataset-api from the EDC.

    No fallback: the connector no longer accepts that header, so one could only
    turn a clear configuration error into a 403 at query time.

    **Keycloak not answering is a denial too.** The token fetch used to escape as
    whatever `httpx` raised — a 500 out of the middle of `/query`, and on the
    audit call a 500 raised *after* the decision was taken and the rows narrowed.
    A PEP that cannot prove who it is has not been told it may serve anything.
    """
    try:
        token = await _token_provider()
    except httpx.HTTPStatusError as exc:
        log.error("Keycloak refused the service token: %s", exc.response.status_code)
        raise HTTPException(
            502, f"Keycloak refused this service's token: {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        log.error("Keycloak unreachable for the service token: %s", exc)
        raise HTTPException(502, "Keycloak unreachable — cannot authenticate to ds") from exc
    return {"Authorization": f"Bearer {token}"}


async def _audit_query(
    dataset_id: str,
    consumer_id: str | None,
    subject_id: str | None,
    agreement_id: str | None,
    transfer_id: str | None,
    row_count: int,
    authorized_subject_ids: list[str] | None,
) -> None:
    """Record the disclosure, before it becomes one.

    **Every failure here refuses the query.** It used to depend on how the audit
    call failed: a non-2xx was ignored entirely, a `RequestError` was swallowed,
    and an `HTTPStatusError` out of the token fetch escaped as a 500 — three
    outcomes for one event, two of which served the rows anyway.

    Refusing is the coherent one, and it is available *because of where this
    sits*: the rows have been read and narrowed but not yet returned, so a
    request that fails here discloses nothing and therefore needs no record.
    Serving them would leave a disclosure with no `QueryExecuted` event, which
    rulebook `L-1` does not allow to be optional.

    This deliberately differs from the connector's provenance emission, which is
    non-fatal and retried (`L-4`). That code records things that have already
    happened — a negotiation concluded, a transfer started — and cannot un-happen
    them, so its only choice is to retry. This one still can.
    """
    url = f"{settings.connector_internal_url.rstrip('/')}/internal/audit/query"
    payload = {
        "dataset_id": dataset_id,
        "consumer_id": consumer_id,
        "user_id": subject_id,
        "subject_id": subject_id,
        "agreement_id": agreement_id,
        "transfer_id": transfer_id,
        "row_count": row_count,
        "authorized_subject_ids": authorized_subject_ids,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=await _internal_headers())
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.error("Query audit refused by ds-connector: %s", exc.response.status_code)
        raise HTTPException(
            502, f"ds-connector refused the query audit: {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        log.error("Query audit could not be recorded: %s", exc)
        raise HTTPException(502, "ds-connector unreachable — the query cannot be recorded") from exc


async def _query_external(spec: dict[str, Any]) -> list[dict[str, Any]]:
    if not settings.external_query_url:
        raise HTTPException(503, "DATASET_API_EXTERNAL_QUERY_URL is not configured")

    payload = {
        "sql": spec["external_sql"],
        "limit": spec.get("external_limit", 50),
        "offset": 0,
        "skip_count": True,
    }
    # Authenticated like every other outbound call this service makes. It went
    # out bare, which meant either the upstream accepts anonymous queries — so
    # anyone who can reach it holds the same access this service does — or the
    # call never worked and the dataset was unserveable. Neither is a state to
    # leave a data plane in, and the second hides the first.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.external_query_url.rstrip('/')}/query",
                json=payload,
                headers=await _internal_headers(),
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            exc.response.status_code,
            f"External dataset-api error: {exc.response.text}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"External dataset-api unreachable: {exc}") from exc

    body = response.json()
    rows = list(body.get("items") or [])
    subject_column = spec.get("subject_column")
    subject_id = spec.get("subject_id")
    if subject_column and subject_id:
        rows = [{**row, subject_column: subject_id} for row in rows]
    return rows


