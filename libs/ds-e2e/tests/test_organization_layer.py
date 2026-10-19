"""The pure halves of the organization-layer flows, and their skip contract."""

from __future__ import annotations

import base64
import gzip
import json
from typing import Any
from unittest.mock import MagicMock

from ds_e2e.config import E2ESettings
from ds_e2e.flows.organization_layer import (
    LayerVerdictsFlow,
    OrganizationReissueFlow,
    OrganizationRowsFlow,
    parse_reissue,
    presented_credentials,
    status_bit,
)


def _jwt(claims: dict[str, Any]) -> str:
    def seg(value: dict[str, Any]) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{seg({'alg': 'ES256'})}.{seg(claims)}.c2ln"


def _credential(cid: str, organization: str, index: int) -> str:
    return _jwt(
        {
            "vc": {
                "id": cid,
                "type": ["VerifiableCredential", "OrganizationCredential"],
                "credentialSubject": {
                    "id": "did:web:x",
                    "organizationId": organization,
                },
                "credentialStatus": [
                    {
                        "statusPurpose": "revocation",
                        "statusListCredential": "http://issuer.example.org/status/1",
                        "statusListIndex": str(index),
                    },
                    {
                        "statusPurpose": "suspension",
                        "statusListCredential": "http://issuer.example.org/status/2",
                        "statusListIndex": str(index),
                    },
                ],
            }
        }
    )


def test_both_presentation_spellings_are_read() -> None:
    vp = _jwt({"vp": {"verifiableCredential": [_credential("urn:a", "ex-org", 9)]}})
    for response in (
        {"presentation": [vp]},
        {"dcp:presentation": {"@value": [vp]}},
    ):
        (found,) = presented_credentials(response)
        assert found.id == "urn:a"
        assert found.organization_id == "ex-org"
        assert "OrganizationCredential" in found.types
        assert found.status["suspension"] == ("http://issuer.example.org/status/2", 9)


def test_a_response_that_is_not_a_presentation_reads_as_none() -> None:
    assert presented_credentials("nope") == []
    assert presented_credentials({}) == []


def test_status_bits_are_read_msb_first() -> None:
    bits = bytearray(4)
    bits[1] |= 1 << (7 - 3)  # index 11
    encoded = "u" + base64.urlsafe_b64encode(
        gzip.compress(bytes(bits))
    ).decode().rstrip("=")
    assert status_bit(encoded, 11) is True
    assert status_bit(encoded, 10) is False
    assert status_bit(encoded, 12) is False


def test_the_reissue_output_is_parsed() -> None:
    out = (
        "ex-org:\n"
        "  organizationId        'ex-org'\n"
        "  organizationType      None  (omitted: no role)\n"
        "  issued                urn:uuid:new\n"
        "  delivered             http://holder.example.org/credentials\n"
        "  suspended             urn:uuid:old\n"
        "\n1 organisation(s), 1 reissued, 0 failed\n"
    )
    assert parse_reissue(out) == {
        "issued": "urn:uuid:new",
        "delivered": True,
        "suspended": ["urn:uuid:old"],
        "errors": [],
    }


def test_an_undelivered_reissue_is_not_read_as_delivered() -> None:
    out = (
        "ex-org:\n  issued                urn:uuid:new\n"
        "  ERROR  not delivered, nothing suspended: 503\n"
    )
    parsed = parse_reissue(out)
    assert parsed["delivered"] is False
    assert parsed["suspended"] == []
    assert parsed["errors"]


def test_each_flow_skips_by_name_with_no_target() -> None:
    """No target configured: a SKIP naming the settings, and nothing called."""
    settings = E2ESettings()
    for flow_cls in (OrganizationRowsFlow, LayerVerdictsFlow, OrganizationReissueFlow):
        http = MagicMock()
        result = flow_cls(settings, http).execute()
        assert result.skipped, flow_cls.name
        (step,) = result.steps
        assert "Missing:" in step.detail
        assert "E2E_" in step.detail
        http.raw.assert_not_called()
        http.bearer_headers_for.assert_not_called()
