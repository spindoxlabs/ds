"""Tests for ds.governance.compliance.evidence and .runtime."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

from ds.governance.compliance import (
    ValidationResult,
    build_evidence,
    render_markdown,
    validate,
    write_artifacts,
)
from ds.governance.compliance.checks import load_exposed
from ds.governance.compliance.evidence import DSP_PROTOCOL_IRI, odrl_context
from ds.governance.compliance.runtime import RuntimeOwnerLookup, fetch_participant_dids
from ds.governance.mapper import GovernanceMapper
from ds.governance.models import OdrlProfile
from ds.governance.resolver import GovernanceResolver

PARTICIPANT = "provider"
BASE_URL = "https://provider.example.org"
PUBLISHER = "did:web:provider.example.org"


def write_governance(tmp_path: Path, config: dict) -> Path:
    path = tmp_path / "governance.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.fixture
def sample(tmp_path: Path):
    path = write_governance(
        tmp_path,
        {
            "sources": {
                "datasets.meters": {
                    "title": "Meter readings",
                    "description": "15-minute meter readings",
                    "license": "CC-BY-4.0",
                    "tags": ["energy"],
                    "access_level": "open",
                    "dataspace": {
                        "expose": True,
                        "asset": {"content_type": "application/json"},
                        "data_address": {"base_url": "https://api.example.org/meters"},
                    },
                }
            }
        },
    )
    resolver = GovernanceResolver.from_file(path)
    mapper = GovernanceMapper(participant_id=PARTICIPANT, base_url=BASE_URL)
    return path, resolver, mapper, load_exposed(resolver, mapper)


class TestBuildEvidence:
    def test_catalog_shape(self, sample):
        _, _, mapper, exposed = sample
        catalog, offers = build_evidence(
            exposed,
            mapper,
            base_url=BASE_URL,
            publisher_id=PUBLISHER,
            publisher_name="Example Provider",
            catalog_name="core",
        )
        assert catalog["@type"] == "dcat:Catalog"
        assert catalog["@id"] == f"{BASE_URL}/catalog/core"
        assert catalog["dct:publisher"]["@id"] == PUBLISHER
        assert catalog["dct:publisher"]["foaf:name"] == "Example Provider"
        assert len(catalog["dcat:dataset"]) == 1
        assert len(offers) == 1

    def test_dataset_carries_governance_metadata(self, sample):
        _, _, mapper, exposed = sample
        catalog, _ = build_evidence(
            exposed,
            mapper,
            base_url=BASE_URL,
            publisher_id=PUBLISHER,
            publisher_name="Example Provider",
            catalog_name="core",
        )
        dataset = catalog["dcat:dataset"][0]
        assert dataset["@type"] == "dcat:Dataset"
        assert dataset["dct:title"] == "Meter readings"
        assert dataset["dct:license"] == "CC-BY-4.0"
        assert dataset["dcat:keyword"] == ["energy"]
        assert dataset["odrl:hasPolicy"]["@type"] == "odrl:Offer"

    def test_distribution_declares_dsp_protocol(self, sample):
        _, _, mapper, exposed = sample
        catalog, _ = build_evidence(
            exposed,
            mapper,
            base_url=BASE_URL,
            publisher_id=PUBLISHER,
            publisher_name="P",
            catalog_name="core",
        )
        distribution = catalog["dcat:dataset"][0]["dcat:distribution"][0]
        assert distribution["@type"] == "dcat:Distribution"
        assert distribution["dcat:accessURL"] == "https://api.example.org/meters"
        assert distribution["dcat:mediaType"] == "application/json"
        assert distribution["dct:conformsTo"]["@id"] == DSP_PROTOCOL_IRI

    def test_base_url_drives_iris_not_a_hardcoded_host(self, sample):
        """Evidence must be generatable for any deployment, not just dev.

        Requires participant_did — without it the mapper's assigner fallback
        still emits the dev domain.
        """
        _, _, _, exposed = sample
        mapper = GovernanceMapper(
            participant_id="acme",
            base_url="https://acme.example",
            participant_did="did:web:acme.example",
        )
        catalog, _ = build_evidence(
            exposed,
            mapper,
            base_url="https://acme.example",
            publisher_id="did:web:acme.example",
            publisher_name="ACME",
            catalog_name="prod",
        )
        assert catalog["@id"].startswith("https://acme.example/")
        assert catalog["dcat:dataset"][0]["@id"].startswith("https://acme.example/")
        assert "dataspaces.localhost" not in json.dumps(catalog)

    def test_none_valued_fields_are_dropped(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"a": {"access_level": "open", "dataspace": {"expose": True}}}},
        )
        resolver = GovernanceResolver.from_file(path)
        mapper = GovernanceMapper(participant_id=PARTICIPANT, base_url=BASE_URL)
        catalog, _ = build_evidence(
            load_exposed(resolver, mapper),
            mapper,
            base_url=BASE_URL,
            publisher_id=PUBLISHER,
            publisher_name="P",
            catalog_name="core",
        )
        assert "dct:license" not in catalog["dcat:dataset"][0]


class TestOdrlContext:
    def test_uses_profile_prefix_and_namespace(self):
        profile = OdrlProfile(namespace="https://acme.example/policy/", prefix="acme")
        context = odrl_context(profile)
        assert context["acme"] == "https://acme.example/policy/"
        assert context["odrl"] == "http://www.w3.org/ns/odrl/2/"


class TestWriteArtifacts:
    def test_writes_all_four_artifacts(self, sample, tmp_path: Path):
        path, _, mapper, exposed = sample
        catalog, offers = build_evidence(
            exposed,
            mapper,
            base_url=BASE_URL,
            publisher_id=PUBLISHER,
            publisher_name="P",
            catalog_name="core",
        )
        result = validate(path, participant_id=PARTICIPANT, base_url=BASE_URL)
        out = tmp_path / "reports"
        write_artifacts(
            result, catalog, offers, out, profile=mapper.profile, name="core"
        )

        assert (out / "core-dcat-catalog.jsonld").exists()
        assert (out / "core-odrl-offers.jsonld").exists()
        assert (out / "core-compliance-report.json").exists()
        assert (out / "core-compliance-report.md").exists()
        assert set(result.artifacts) == {
            "dcat_catalog",
            "odrl_offers",
            "json_report",
            "markdown_report",
        }

    def test_artifacts_are_valid_json_ld(self, sample, tmp_path: Path):
        path, _, mapper, exposed = sample
        catalog, offers = build_evidence(
            exposed,
            mapper,
            base_url=BASE_URL,
            publisher_id=PUBLISHER,
            publisher_name="P",
            catalog_name="core",
        )
        result = validate(path, participant_id=PARTICIPANT, base_url=BASE_URL)
        out = tmp_path / "reports"
        write_artifacts(result, catalog, offers, out, profile=mapper.profile, name="core")

        loaded = json.loads((out / "core-odrl-offers.jsonld").read_text())
        assert "@context" in loaded
        assert len(loaded["@graph"]) == 1
        assert json.loads((out / "core-dcat-catalog.jsonld").read_text())["@type"] == "dcat:Catalog"

    def test_creates_nested_output_directory(self, sample, tmp_path: Path):
        path, _, mapper, exposed = sample
        catalog, offers = build_evidence(
            exposed, mapper, base_url=BASE_URL, publisher_id=PUBLISHER,
            publisher_name="P", catalog_name="core",
        )
        result = validate(path, participant_id=PARTICIPANT, base_url=BASE_URL)
        out = tmp_path / "deep" / "nested" / "reports"
        write_artifacts(result, catalog, offers, out, profile=mapper.profile, name="core")
        assert (out / "core-dcat-catalog.jsonld").exists()


class TestRenderMarkdown:
    def test_reports_pass(self):
        result = ValidationResult(governance_path="g.yaml", datasets_checked=3)
        rendered = render_markdown(result)
        assert "- Status: PASS" in rendered
        assert "- Datasets checked: 3" in rendered
        assert "## Errors\n- None" in rendered

    def test_reports_findings_with_dataset_scope(self):
        result = ValidationResult(governance_path="g.yaml")
        result.error("data-address", "bad url", "datasets.meters")
        result.warning("owner-declared", "no owner")
        rendered = render_markdown(result)
        assert "- Status: FAIL" in rendered
        assert "`data-address` (datasets.meters): bad url" in rendered
        assert "`owner-declared`: no owner" in rendered


class TestRuntimeOwnerLookup:
    def _client(self, handler) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_resolves_owner_from_live_registry(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/owners/resolve"
            assert request.url.params["alias"] == "example-org"
            return httpx.Response(
                200, json={"id": "example-org", "did": "did:web:example-org.test"}
            )

        with RuntimeOwnerLookup("http://ir.test", client=self._client(handler)) as lookup:
            entry = lookup.by_id("example-org")
            assert entry is not None
            assert entry.did == "did:web:example-org.test"

    def test_unknown_owner_returns_none_on_404(self):
        with RuntimeOwnerLookup(
            "http://ir.test", client=self._client(lambda r: httpx.Response(404))
        ) as lookup:
            assert lookup.by_id("ghost") is None

    def test_results_are_cached_per_alias(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.params["alias"])
            return httpx.Response(200, json={"id": "example-org"})

        with RuntimeOwnerLookup("http://ir.test", client=self._client(handler)) as lookup:
            lookup.by_id("example-org")
            lookup.by_id("example-org")
        assert calls == ["example-org"]

    def test_token_is_sent_as_bearer(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"id": "o"})

        with RuntimeOwnerLookup(
            "http://ir.test", token="tok-1", client=self._client(handler)
        ) as lookup:
            lookup.by_id("o")
        assert seen["auth"] == "Bearer tok-1"

    def test_transport_error_is_raised_not_swallowed(self):
        """A dead registry must fail loudly, not silently pass validation."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with RuntimeOwnerLookup("http://ir.test", client=self._client(handler)) as lookup:
            with pytest.raises(RuntimeError, match="Failed to resolve owner"):
                lookup.by_id("example-org")

    def test_all_falls_back_to_resolved_when_admin_forbidden(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/admin/owners":
                return httpx.Response(403)
            return httpx.Response(200, json={"id": "example-org"})

        with RuntimeOwnerLookup("http://ir.test", client=self._client(handler)) as lookup:
            lookup.by_id("example-org")
            assert [entry.id for entry in lookup.all()] == ["example-org"]

    def test_all_uses_admin_listing_when_available(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/admin/owners":
                return httpx.Response(200, json=[{"id": "a"}, {"id": "b"}])
            return httpx.Response(404)

        with RuntimeOwnerLookup("http://ir.test", client=self._client(handler)) as lookup:
            assert sorted(entry.id for entry in lookup.all()) == ["a", "b"]


class TestFetchParticipantDids:
    def test_returns_dids(self):
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json=[{"did": "did:web:a.test"}, {"did": "did:web:b.test"}]
                )
            )
        )
        assert fetch_participant_dids("http://ir.test", client=client) == {
            "did:web:a.test",
            "did:web:b.test",
        }

    def test_returns_none_when_unavailable(self):
        """Unavailable participant registry downgrades the check, not the whole run."""
        client = httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(401))
        )
        assert fetch_participant_dids("http://ir.test", client=client) is None


class TestValidateAgainstRuntime:
    def test_runtime_lookup_satisfies_owner_checks(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": {
                        "access_level": "open",
                        "ownership": [{"name": "example-org"}],
                        "dataspace": {
                            "expose": True,
                            "data_address": {"base_url": "https://api.example.org"},
                        },
                    }
                }
            },
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/owners/resolve":
                return httpx.Response(
                    200, json={"id": "example-org", "did": "did:web:example-org.test"}
                )
            return httpx.Response(404)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with RuntimeOwnerLookup("http://ir.test", client=client) as lookup:
            result = validate(
                path,
                participant_id=PARTICIPANT,
                base_url=BASE_URL,
                owners=lookup,
                participant_dids={"did:web:example-org.test"},
            )
        assert result.passed
        assert result.errors == []

    def test_runtime_lookup_catches_unregistered_owner(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": {
                        "access_level": "open",
                        "ownership": [{"name": "ghost-org"}],
                        "dataspace": {
                            "expose": True,
                            "data_address": {"base_url": "https://api.example.org"},
                        },
                    }
                }
            },
        )
        client = httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(404))
        )
        with RuntimeOwnerLookup("http://ir.test", client=client) as lookup:
            result = validate(
                path, participant_id=PARTICIPANT, base_url=BASE_URL, owners=lookup
            )
        assert not result.passed
        assert result.errors[0].check == "owner-resolvable"
