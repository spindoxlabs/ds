#!/usr/bin/env python3
"""Validate DSSC compliance evidence and emit audit-ready reports."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/governance/src"))

from ds.governance.mapper import GovernanceMapper  # noqa: E402
from ds.governance.resolver import GovernanceResolver  # noqa: E402


PROFILE_PATHS = {
    "core": ROOT / "services/connector/governance/governance.yaml",
}

REPORTS_DIR = ROOT / "reports/compliance"
PROFILE_REPORT_DIRS = {
    "core": REPORTS_DIR,
}

DCAT_CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

ODRL_CONTEXT = {
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "ds": GovernanceMapper.DS_NAMESPACE,
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


@dataclass
class Finding:
    check: str
    message: str
    dataset: str | None = None

    def asdict(self) -> dict[str, str]:
        data = {"check": self.check, "message": self.message}
        if self.dataset:
            data["dataset"] = self.dataset
        return data


@dataclass
class ValidationResult:
    profile: str
    governance_path: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    datasets_checked: int = 0
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def error(self, check: str, message: str, dataset: str | None = None) -> None:
        self.errors.append(Finding(check, message, dataset))

    def warning(self, check: str, message: str, dataset: str | None = None) -> None:
        self.warnings.append(Finding(check, message, dataset))

    def asdict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "governance_path": self.governance_path,
            "generated_at": self.generated_at,
            "passed": self.passed,
            "datasets_checked": self.datasets_checked,
            "checks": self.checks,
            "artifacts": self.artifacts,
            "errors": [item.asdict() for item in self.errors],
            "warnings": [item.asdict() for item in self.warnings],
        }


@dataclass(frozen=True)
class DatasetEvidence:
    key: str
    rule: Any
    offer: dict[str, Any]
    dcat_dataset: dict[str, Any]


def _selected_governance_path(profile: str, explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path).resolve()
    return PROFILE_PATHS[profile]


def validate(
    profile: str,
    governance_path: Path,
    *,
    report_dir: Path | None = None,
    write_artifacts: bool = False,
) -> ValidationResult:
    result = ValidationResult(profile=profile, governance_path=str(governance_path))
    result.checks.extend([
        "governance-file",
        "dcat-ap-fixture",
        "dcat-ap-shacl-equivalent-shape",
        "odrl-jsonld-expansion",
        "odrl-jsonld-shape",
        "policy-enforcement-shape",
        "dsp-compatibility-checklist",
        "profile-split",
    ])

    if not governance_path.exists():
        result.error("governance-file", f"Missing governance file: {governance_path}")
        return result

    resolver = GovernanceResolver.from_file(governance_path)
    mapper = GovernanceMapper("provider", "https://provider.dataspaces.test")

    exposed: list[DatasetEvidence] = []
    for key in resolver.config.sources:
        rule = resolver.resolve(key)
        if rule.dataspace.expose and rule.access_level != "secret":
            offer = mapper.to_odrl_offer(key, rule)
            exposed.append(DatasetEvidence(key, rule, offer, _to_dcat_dataset(key, rule, offer)))
    result.datasets_checked = len(exposed)
    if not exposed:
        result.error("governance-file", "No exposed non-secret dataset found")

    catalog = _to_dcat_catalog(profile, exposed)
    _validate_dcat_catalog(result, catalog)

    for evidence in exposed:
        _validate_dcat_dataset(result, evidence.key, evidence.dcat_dataset)
        expanded_offer = _expand_jsonld(evidence.offer, ODRL_CONTEXT)
        _validate_odrl_offer(result, evidence.key, evidence.rule, evidence.offer, expanded_offer)
        _validate_policy_enforcement(result, evidence.key, evidence.rule, evidence.offer)

    _validate_profile_split(result, profile, exposed)
    _validate_dsp_static(result)

    if write_artifacts or report_dir:
        _write_artifacts(result, catalog, exposed, report_dir or PROFILE_REPORT_DIRS.get(profile, REPORTS_DIR))
    return result


def _to_dcat_catalog(profile: str, datasets: list[DatasetEvidence]) -> dict[str, Any]:
    return {
        "@context": DCAT_CONTEXT,
        "@id": f"https://dataspaces.test/catalog/{profile}",
        "@type": "dcat:Catalog",
        "dct:title": f"Dataspaces {profile} catalog",
        "dct:description": "Governance-derived DSSC evidence catalog.",
        "dct:publisher": {"@id": "did:web:provider.dataspaces.test", "foaf:name": "Dataspace Provider"},
        "dct:issued": datetime.now(timezone.utc).date().isoformat(),
        "dcat:dataset": [item.dcat_dataset for item in datasets],
    }


def _to_dcat_dataset(dataset_key: str, rule: Any, offer: dict[str, Any]) -> dict[str, Any]:
    asset_id = rule.dataspace.asset.id or dataset_key
    base_url = rule.dataspace.data_address.base_url
    media_type = rule.dataspace.asset.content_type or "application/octet-stream"
    distribution_id = f"https://provider.dataspaces.test/dcat/distribution/{asset_id.replace('.', '/') }"
    dataset = {
        "@id": f"https://provider.dataspaces.test/dcat/dataset/{asset_id.replace('.', '/')}",
        "@type": "dcat:Dataset",
        "dct:identifier": asset_id,
        "dct:title": rule.title or dataset_key,
        "dct:description": rule.description or "",
        "dct:publisher": {"@id": "did:web:provider.dataspaces.test"},
        "dcat:keyword": rule.tags,
        "dct:license": rule.license,
        "dct:source": rule.source_system,
        "dct:conformsTo": {"@id": "https://semantics.dataspaces.localhost/dssc-blueprint"},
        "dcat:distribution": [{
            "@id": distribution_id,
            "@type": "dcat:Distribution",
            "dct:title": f"{rule.title or dataset_key} EDC HTTP pull distribution",
            "dcat:accessURL": base_url,
            "dcat:mediaType": media_type,
            "dct:conformsTo": {"@id": "https://w3id.org/dspace/protocol/2025-1"},
        }],
        "odrl:hasPolicy": offer,
    }
    return {k: v for k, v in dataset.items() if v is not None}


def _validate_dcat_catalog(result: ValidationResult, catalog: dict[str, Any]) -> None:
    if catalog.get("@type") != "dcat:Catalog":
        result.error("dcat-ap-shacl-equivalent-shape", "Catalog @type must be dcat:Catalog")
    for field_name in ("@id", "dct:title", "dct:publisher", "dcat:dataset"):
        if not catalog.get(field_name):
            result.error("dcat-ap-shacl-equivalent-shape", f"Catalog missing {field_name}")
    if not isinstance(catalog.get("dcat:dataset"), list):
        result.error("dcat-ap-shacl-equivalent-shape", "Catalog dcat:dataset must be a list")


def _validate_dcat_dataset(result: ValidationResult, dataset_key: str, dataset: dict[str, Any]) -> None:
    required = ["@id", "@type", "dct:identifier", "dct:title", "dct:description", "dcat:distribution"]
    for field_name in required:
        if not dataset.get(field_name):
            result.error("dcat-ap-shacl-equivalent-shape", f"Dataset missing {field_name}", dataset_key)
    if dataset.get("@type") != "dcat:Dataset":
        result.error("dcat-ap-shacl-equivalent-shape", "Dataset @type must be dcat:Dataset", dataset_key)
    if not dataset.get("dct:license"):
        result.warning("dcat-ap-shacl-equivalent-shape", "Dataset has no dct:license", dataset_key)
    distributions = dataset.get("dcat:distribution") or []
    if not isinstance(distributions, list) or not distributions:
        result.error("dcat-ap-shacl-equivalent-shape", "Dataset needs at least one distribution", dataset_key)
        return
    for distribution in distributions:
        for field_name in ("@id", "@type", "dcat:accessURL", "dcat:mediaType"):
            if not distribution.get(field_name):
                result.error("dcat-ap-shacl-equivalent-shape", f"Distribution missing {field_name}", dataset_key)
        if distribution.get("@type") != "dcat:Distribution":
            result.error("dcat-ap-shacl-equivalent-shape", "Distribution @type must be dcat:Distribution", dataset_key)


def _expand_jsonld(value: Any, context: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_expand_jsonld(item, context) for item in value]
    if isinstance(value, dict):
        expanded: dict[str, Any] = {}
        for key, item in value.items():
            if key == "@context":
                continue
            expanded[_expand_term(key, context)] = _expand_jsonld(item, context)
        return expanded
    if isinstance(value, str):
        return _expand_term(value, context)
    return value


def _expand_term(value: str, context: dict[str, str]) -> str:
    if value.startswith("http://") or value.startswith("https://") or value.startswith("urn:"):
        return value
    if ":" not in value:
        return value
    prefix, suffix = value.split(":", 1)
    base = context.get(prefix)
    return f"{base}{suffix}" if base else value


def _validate_odrl_offer(
    result: ValidationResult,
    dataset_key: str,
    rule: Any,
    offer: dict[str, Any],
    expanded_offer: dict[str, Any],
) -> None:
    context = offer.get("@context")
    if not isinstance(context, dict) or "odrl" not in context or "ds" not in context:
        result.error("odrl-jsonld-shape", "Missing ODRL/DS JSON-LD context", dataset_key)
    if offer.get("@type") != "odrl:Offer":
        result.error("odrl-jsonld-shape", "Generated policy is not an odrl:Offer", dataset_key)
    if not offer.get("@id"):
        result.error("odrl-jsonld-shape", "Generated policy has no @id", dataset_key)
    if not offer.get("odrl:assigner"):
        result.error("odrl-jsonld-shape", "Generated policy has no assigner", dataset_key)

    expanded_type = expanded_offer.get("@type")
    if expanded_type != "http://www.w3.org/ns/odrl/2/Offer":
        result.error("odrl-jsonld-expansion", "Expanded policy type is not ODRL Offer", dataset_key)
    if "http://www.w3.org/ns/odrl/2/permission" not in expanded_offer:
        result.error("odrl-jsonld-expansion", "Expanded policy has no odrl:permission", dataset_key)

    permissions = offer.get("odrl:permission")
    if rule.access_level != "secret" and not permissions:
        result.error("odrl-jsonld-shape", "Exposed dataset has no permissions", dataset_key)
    for permission in permissions or []:
        if not permission.get("odrl:action"):
            result.error("odrl-jsonld-shape", "Permission without action", dataset_key)
        for constraint in permission.get("odrl:constraint", []):
            for field_name in ("odrl:leftOperand", "odrl:operator", "odrl:rightOperand"):
                if field_name not in constraint:
                    result.error("odrl-jsonld-shape", f"Constraint missing {field_name}", dataset_key)


def _validate_policy_enforcement(result: ValidationResult, dataset_key: str, rule: Any, offer: dict[str, Any]) -> None:
    constraints = [
        constraint
        for permission in offer.get("odrl:permission", [])
        for constraint in permission.get("odrl:constraint", [])
    ]
    left_operands = {
        item.get("@id") if isinstance(item, dict) else item
        for item in (constraint.get("odrl:leftOperand") for constraint in constraints)
    }

    if rule.access_level in {"internal", "restricted"} and "ds:accessScope" not in left_operands:
        result.error("policy-enforcement-shape", "Missing ds:accessScope constraint", dataset_key)
    if rule.access_level == "restricted" and "ds:contractRequired" not in left_operands:
        result.error("policy-enforcement-shape", "Missing ds:contractRequired constraint", dataset_key)

    requires_consent = bool(rule.user_filter_column or rule.row_filters or rule.policy.consent.required)
    if requires_consent and "ds:consentStatus" not in left_operands:
        result.error("policy-enforcement-shape", "Missing ds:consentStatus constraint", dataset_key)
    if rule.classification == "pii":
        prohibited = {
            item.get("odrl:action", {}).get("@id")
            for item in offer.get("odrl:prohibition", [])
            if isinstance(item.get("odrl:action"), dict)
        }
        for action in ("odrl:transfer", "odrl:sublicense"):
            if action not in prohibited:
                result.error("policy-enforcement-shape", f"Missing PII prohibition {action}", dataset_key)


def _validate_profile_split(result: ValidationResult, profile: str, exposed: list[DatasetEvidence]) -> None:
    integration_datasets = [item.key for item in exposed if "ds_dev_" in item.key]
    if profile == "core" and integration_datasets:
        result.error("profile-split", "Core profile exposes integration datasets: " + ", ".join(integration_datasets))


def _validate_dsp_static(result: ValidationResult) -> None:
    participants = ROOT / "services/connector/governance/participants.yaml"
    text = participants.read_text() if participants.exists() else ""
    if "protocol/2025-1" not in text:
        result.warning("dsp-compatibility-checklist", "Participants do not declare DSP protocol/2025-1 addresses")
    edc_connector = ROOT / "services/edc-connector/build.gradle.kts"
    if edc_connector.exists() and "0.16.0" not in edc_connector.read_text():
        result.warning("dsp-compatibility-checklist", "EDC version 0.16.0 not found in connector build file")


def _write_artifacts(
    result: ValidationResult,
    catalog: dict[str, Any],
    datasets: list[DatasetEvidence],
    report_dir: Path,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    dcat_path = report_dir / f"{result.profile}-dcat-catalog.jsonld"
    odrl_path = report_dir / f"{result.profile}-odrl-offers.jsonld"
    json_path = report_dir / f"{result.profile}-compliance-report.json"
    md_path = report_dir / f"{result.profile}-compliance-report.md"

    dcat_path.write_text(json.dumps(catalog, indent=2, sort_keys=True), encoding="utf-8")
    odrl_path.write_text(json.dumps({
        "@context": ODRL_CONTEXT,
        "@graph": [item.offer for item in datasets],
    }, indent=2, sort_keys=True), encoding="utf-8")
    result.artifacts.update({
        "dcat_catalog": str(dcat_path),
        "odrl_offers": str(odrl_path),
        "json_report": str(json_path),
        "markdown_report": str(md_path),
    })
    json_path.write_text(json.dumps(result.asdict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")


def render_markdown(result: ValidationResult) -> str:
    lines = [
        f"# DSSC Compliance Report - {result.profile}",
        "",
        f"- Status: {'PASS' if result.passed else 'FAIL'}",
        f"- Generated at: {result.generated_at}",
        f"- Governance: `{result.governance_path}`",
        f"- Datasets checked: {result.datasets_checked}",
        f"- Checks: {', '.join(result.checks)}",
    ]
    if result.artifacts:
        lines.extend(["", "## Artifacts"])
        for name, path in result.artifacts.items():
            lines.append(f"- `{name}`: `{path}`")
    lines.extend(["", "## Errors"])
    if result.errors:
        for finding in result.errors:
            dataset = f" ({finding.dataset})" if finding.dataset else ""
            lines.append(f"- `{finding.check}`{dataset}: {finding.message}")
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings"])
    if result.warnings:
        for finding in result.warnings:
            dataset = f" ({finding.dataset})" if finding.dataset else ""
            lines.append(f"- `{finding.check}`{dataset}: {finding.message}")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def print_text(result: ValidationResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(f"DSSC compliance validation: {status}")
    print(f"Profile: {result.profile}")
    print(f"Governance: {result.governance_path}")
    print(f"Datasets checked: {result.datasets_checked}")
    print("Checks: " + ", ".join(result.checks))
    if result.artifacts:
        print("Artifacts:")
        for name, path in result.artifacts.items():
            print(f"- {name}: {path}")
    if result.errors:
        print("\nErrors:")
        for finding in result.errors:
            prefix = f"[{finding.check}]"
            dataset = f" {finding.dataset}:" if finding.dataset else ""
            print(f"- {prefix}{dataset} {finding.message}")
    if result.warnings:
        print("\nWarnings:")
        for finding in result.warnings:
            prefix = f"[{finding.check}]"
            dataset = f" {finding.dataset}:" if finding.dataset else ""
            print(f"- {prefix}{dataset} {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="core")
    parser.add_argument("--governance", help="Override governance YAML path")
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    parser.add_argument("--report-dir", type=Path, default=None, help="Directory for JSON/Markdown/DCAT/ODRL artifacts")
    parser.add_argument("--write-artifacts", action="store_true", help="Write audit artifacts to reports/compliance or --report-dir")
    args = parser.parse_args(argv)

    result = validate(
        args.profile,
        _selected_governance_path(args.profile, args.governance),
        report_dir=args.report_dir,
        write_artifacts=args.write_artifacts,
    )
    if args.format == "json":
        print(json.dumps(result.asdict(), indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(result))
    else:
        print_text(result)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
