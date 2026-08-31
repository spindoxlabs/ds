"""Audit evidence generation — DCAT-AP catalog and ODRL offers as JSON-LD.

Separate from validation: validation gates an import, evidence is the
deliverable handed to an auditor.  Both derive from the same resolved rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..dcat import CATALOG_CONTEXT, DSP_PROTOCOL_IRI, to_catalog_record, to_data_service
from ..mapper import GovernanceMapper
from ..models import GovernanceRuleV2, OdrlProfile
from .checks import DatasetEvidence, ValidationResult

DCAT_CONTEXT = CATALOG_CONTEXT


def odrl_context(profile: OdrlProfile) -> dict[str, str]:
    return {
        "odrl": "http://www.w3.org/ns/odrl/2/",
        profile.prefix: profile.namespace,
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }


def _slug(asset_id: str) -> str:
    return quote(asset_id.replace(".", "/"), safe="/")


def _temporal(dcat: Any) -> dict[str, Any] | None:
    """`dct:temporal` as a `dct:PeriodOfTime`, or nothing.

    An open-ended period is legitimate — a dataset that started in 2020 and is
    still accruing has a start and no end — so only a period with *neither* bound
    is dropped. Emitting a bare `dct:PeriodOfTime` node with no properties would
    assert that a temporal coverage exists and then decline to say what it is.
    """
    period = {
        "dcat:startDate": dcat.temporal.start,
        "dcat:endDate": dcat.temporal.end,
    }
    period = {k: v for k, v in period.items() if v is not None}
    return {"@type": "dct:PeriodOfTime", **period} if period else None


def to_dcat_dataset(
    item: DatasetEvidence,
    offer: dict[str, Any],
    *,
    base_url: str,
    publisher_id: str,
) -> dict[str, Any]:
    rule: GovernanceRuleV2 = item.rule
    root = base_url.rstrip("/")
    slug = _slug(item.asset_id)
    dcat = rule.dcat
    dataset = {
        "@id": f"{root}/dcat/dataset/{slug}",
        "@type": "dcat:Dataset",
        "dct:identifier": item.asset_id,
        "dct:title": rule.title or item.key,
        "dct:description": rule.description or "",
        # The producer's own publisher URI wins over the participant emitting the
        # evidence. They are different claims: a participant may host datasets for
        # several owners, so `publisher_id` is who published the *catalogue* and
        # `dcat.publisher_uri` is who published the *dataset*. Collapsing them
        # attributes an owner's data to whoever happened to sync it.
        "dct:publisher": {"@id": dcat.publisher_uri or publisher_id},
        "dcat:keyword": rule.tags,
        "dct:license": rule.license,
        "dct:source": rule.source_system,
        # ── The canonical `dcat:` block, which ds used to drop entirely ───────
        "dcat:theme": [{"@id": t} for t in dcat.themes] or None,
        "dct:language": [{"@id": u} for u in dcat.language_uris] or None,
        "dct:spatial": [{"@id": u} for u in dcat.spatial_uris] or None,
        "dct:accrualPeriodicity": (
            {"@id": dcat.accrual_periodicity} if dcat.accrual_periodicity else None
        ),
        # The dataset's payload semantic model (`M-4`). It sits on the **dataset**,
        # not the distribution: the distribution already carries a `dct:conformsTo`
        # naming the *protocol* (DSP), and a column's meaning is a property of the
        # data, not of the way it is fetched. Two different conformance claims, and
        # putting them on one node would make them indistinguishable to a reader.
        "dct:conformsTo": ({"@id": dcat.conforms_to} if dcat.conforms_to else None),
        "dct:temporal": _temporal(dcat) if dcat.temporal else None,
        "dcat:distribution": [
            {
                "@id": f"{root}/dcat/distribution/{slug}",
                "@type": "dcat:Distribution",
                "dct:title": f"{rule.title or item.key} EDC HTTP pull distribution",
                "dcat:accessURL": rule.dataspace.data_address.base_url,
                "dcat:mediaType": rule.dataspace.asset.content_type
                or "application/octet-stream",
                "dct:conformsTo": {"@id": DSP_PROTOCOL_IRI},
            }
        ],
        "odrl:hasPolicy": offer,
    }
    return {k: v for k, v in dataset.items() if v is not None}


def to_dcat_catalog(
    datasets: list[dict[str, Any]],
    *,
    catalog_id: str,
    title: str,
    publisher_id: str,
    publisher_name: str,
    service_endpoint: str | None = None,
) -> dict[str, Any]:
    """The evidence catalogue as a `dcat:Catalog`.

    ``dcat:service`` and ``dcat:record`` are mandatory (`DSSC-PUB-41`, `-45`;
    rulebook `C-7`, `C-8`) and both were absent. The shapes come from
    :mod:`ds.governance.dcat`, shared with the federated index so the two
    catalogues this platform publishes cannot answer the same requirement
    differently.

    ``dcat:dataset`` stays inlined alongside the records. `PUB-45` asks that a
    catalogue reference its entries; it does not ask that the description be
    withheld, and dropping the inline datasets would break every consumer for
    no gain in conformance. A record carries what the *catalogue* knows about
    the entry, which is exactly what was previously unsayable.
    """
    issued = datetime.now(timezone.utc).date().isoformat()
    entry_ids = [ds["@id"] for ds in datasets if ds.get("@id")]
    catalog: dict[str, Any] = {
        "@context": DCAT_CONTEXT,
        "@id": catalog_id,
        "@type": "dcat:Catalog",
        "dct:title": title,
        "dct:description": "Governance-derived dataspace catalog.",
        "dct:publisher": {"@id": publisher_id, "foaf:name": publisher_name},
        "dct:issued": issued,
        "dcat:dataset": datasets,
        "dcat:record": [
            to_catalog_record(
                dataset_id=iri,
                record_id=f"{catalog_id}/record/{quote(iri, safe='')}",
                modified=issued,
                source=catalog_id,
            )
            for iri in entry_ids
        ],
    }
    if service_endpoint:
        catalog["dcat:service"] = [
            to_data_service(
                service_id=f"{catalog_id}#dsp",
                title=f"{publisher_name} DSP endpoint",
                endpoint_url=service_endpoint,
                serves_dataset=entry_ids,
                conforms_to=DSP_PROTOCOL_IRI,
            )
        ]
    return catalog


def build_evidence(
    exposed: list[DatasetEvidence],
    mapper: GovernanceMapper,
    *,
    base_url: str,
    publisher_id: str,
    publisher_name: str,
    catalog_name: str,
    service_endpoint: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (dcat_catalog, odrl_offers).

    ``service_endpoint`` is this participant's DSP protocol URL. It is optional
    because the evidence bundle is generated from governance files alone and a
    caller may not know the deployment's endpoint; when it is not supplied the
    catalogue omits ``dcat:service`` rather than inventing a URL, which would be
    worse than the absence it replaces.
    """
    offers = [mapper.to_odrl_offer(item.key, item.rule) for item in exposed]
    datasets = [
        to_dcat_dataset(item, offer, base_url=base_url, publisher_id=publisher_id)
        for item, offer in zip(exposed, offers)
    ]
    catalog = to_dcat_catalog(
        datasets,
        catalog_id=f"{base_url.rstrip('/')}/catalog/{catalog_name}",
        title=f"{publisher_name} {catalog_name} catalog",
        publisher_id=publisher_id,
        publisher_name=publisher_name,
        service_endpoint=service_endpoint,
    )
    return catalog, offers


def write_artifacts(
    result: ValidationResult,
    catalog: dict[str, Any],
    offers: list[dict[str, Any]],
    report_dir: Path,
    *,
    profile: OdrlProfile,
    name: str,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "dcat_catalog": report_dir / f"{name}-dcat-catalog.jsonld",
        "odrl_offers": report_dir / f"{name}-odrl-offers.jsonld",
        "json_report": report_dir / f"{name}-compliance-report.json",
        "markdown_report": report_dir / f"{name}-compliance-report.md",
    }

    paths["dcat_catalog"].write_text(
        json.dumps(catalog, indent=2, sort_keys=True), encoding="utf-8"
    )
    paths["odrl_offers"].write_text(
        json.dumps(
            {"@context": odrl_context(profile), "@graph": offers},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    result.artifacts.update({key: str(path) for key, path in paths.items()})
    paths["json_report"].write_text(
        json.dumps(result.asdict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    paths["markdown_report"].write_text(render_markdown(result), encoding="utf-8")


def render_markdown(result: ValidationResult) -> str:
    lines = [
        "# Governance Compliance Report",
        "",
        f"- Status: {'PASS' if result.passed else 'FAIL'}",
        f"- Generated at: {result.generated_at}",
        f"- Governance: `{result.governance_path}`",
        f"- Datasets checked: {result.datasets_checked}",
        f"- Checks: {', '.join(result.checks)}",
    ]
    if result.artifacts:
        lines.extend(["", "## Artifacts"])
        lines.extend(f"- `{name}`: `{path}`" for name, path in result.artifacts.items())
    for label, findings in (("Errors", result.errors), ("Warnings", result.warnings)):
        lines.extend(["", f"## {label}"])
        if findings:
            for finding in findings:
                dataset = f" ({finding.dataset})" if finding.dataset else ""
                lines.append(f"- `{finding.check}`{dataset}: {finding.message}")
        else:
            lines.append("- None")
    lines.append("")
    return "\n".join(lines)
