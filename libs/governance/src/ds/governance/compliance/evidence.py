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

from ..mapper import GovernanceMapper
from ..models import GovernanceRuleV2, OdrlProfile
from .checks import DatasetEvidence, ValidationResult

DCAT_CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

DSP_PROTOCOL_IRI = "https://w3id.org/dspace/protocol/2025-1"


def odrl_context(profile: OdrlProfile) -> dict[str, str]:
    return {
        "odrl": "http://www.w3.org/ns/odrl/2/",
        profile.prefix: profile.namespace,
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }


def _slug(asset_id: str) -> str:
    return quote(asset_id.replace(".", "/"), safe="/")


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
    dataset = {
        "@id": f"{root}/dcat/dataset/{slug}",
        "@type": "dcat:Dataset",
        "dct:identifier": item.asset_id,
        "dct:title": rule.title or item.key,
        "dct:description": rule.description or "",
        "dct:publisher": {"@id": publisher_id},
        "dcat:keyword": rule.tags,
        "dct:license": rule.license,
        "dct:source": rule.source_system,
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
) -> dict[str, Any]:
    return {
        "@context": DCAT_CONTEXT,
        "@id": catalog_id,
        "@type": "dcat:Catalog",
        "dct:title": title,
        "dct:description": "Governance-derived dataspace catalog.",
        "dct:publisher": {"@id": publisher_id, "foaf:name": publisher_name},
        "dct:issued": datetime.now(timezone.utc).date().isoformat(),
        "dcat:dataset": datasets,
    }


def build_evidence(
    exposed: list[DatasetEvidence],
    mapper: GovernanceMapper,
    *,
    base_url: str,
    publisher_id: str,
    publisher_name: str,
    catalog_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (dcat_catalog, odrl_offers)."""
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
