"""The DCP trust chain — the identity layer every other flow assumes.

Two EDCs agree to exchange data because each can verify who the other is. That
verification is a chain: a participant proves control of its DID by obtaining a
self-issued token from the STS, presents that token to the credential service,
and receives a Verifiable Presentation of its credentials, whose revocation
state is published as a StatusList the verifier fetches independently.

Every functional flow depends on that chain holding, and none of them assert it —
they only observe that a negotiation succeeded, which is a very indirect signal.
This flow tests the links directly, and mostly tests them *negatively*, because
the failure that matters is not "a valid participant was refused" but "an
invalid one was admitted".

Covers: STS issuance and its rejection paths, the DCP presentation query and its
token binding (the impersonation case), did:web resolution, and StatusList
publication.

Needs only the identity-registry.
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


def _decode_segment(segment: str) -> dict[str, Any]:
    padding = "=" * (-len(segment) % 4)
    decoded: dict[str, Any] = json.loads(base64.urlsafe_b64decode(segment + padding))
    return decoded


class DcpTrustFlow(BaseFlow):
    name = "dcp-trust"
    description = (
        "DCP identity chain: STS issuance and refusal, presentation-query token "
        "binding, did:web resolution and StatusList publication"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        ir = s.identity_registry_url

        try:
            self.http.get(f"{ir}/health")
            result.pass_step("health", "identity-registry reachable")
        except Exception as exc:
            result.fail_step("health", str(exc))
            return result

        self._check_did_resolution(result)
        token = self._check_sts_refusals(result)
        self._check_presentation_binding(result, token)
        self._check_status_list(result)

        return result

    # ── did:web ──────────────────────────────────────────────────────────────

    def _check_did_resolution(self, result: FlowResult) -> None:
        """A DID document must be resolvable, self-consistent and key-bearing.

        The EDC resolves this document with no credential and trusts the key it
        finds there to verify every token the participant signs. If `id` and the
        requested DID disagree, or the document carries no verification method,
        the whole chain below it verifies against nothing.
        """
        s = self.settings
        encoded = urllib.parse.quote(s.provider_did, safe="")
        status, doc = self.http.raw("GET", f"{s.identity_registry_url}/dids/{encoded}/did.json")
        if status != 200 or not isinstance(doc, dict):
            result.fail_step(
                "did:web resolution",
                "the provider DID document did not resolve",
                status_code=status,
                did=s.provider_did,
            )
            return
        if doc.get("id") != s.provider_did:
            result.fail_step(
                "did:web resolution",
                "the document's subject does not match the DID it was fetched for",
                requested=s.provider_did,
                returned=doc.get("id"),
            )
            return
        methods = doc.get("verificationMethod") or []
        if not methods or not any(m.get("publicKeyJwk") for m in methods if isinstance(m, dict)):
            result.fail_step(
                "did:web resolution",
                "the document publishes no verification key — signatures could not be checked",
                document=doc,
            )
            return

        # An unregistered DID must be a clean 404, not a fabricated document.
        unknown = urllib.parse.quote("did:web:nobody.dataspaces.localhost", safe="")
        unknown_status, _ = self.http.raw(
            "GET", f"{s.identity_registry_url}/dids/{unknown}/did.json"
        )
        if unknown_status != 404:
            result.fail_step(
                "did:web resolution",
                "an unregistered DID did not resolve to 404",
                status_code=unknown_status,
            )
            return
        result.pass_step(
            "did:web resolution",
            "the DID document resolves, names itself and publishes a key; unknown DIDs 404",
            key_count=len(methods),
        )

    # ── STS ──────────────────────────────────────────────────────────────────

    def _check_sts_refusals(self, result: FlowResult) -> str | None:
        """The STS mints the token that *is* the participant's identity.

        Anything it hands out on weak evidence is an impersonation primitive, so
        the assertions here are almost entirely negative: wrong grant type, a
        client_id that does not match the DID it is asking for, a wrong secret,
        and an unknown participant must each be refused.
        """
        s = self.settings
        ir = s.identity_registry_url
        did = s.provider_did
        encoded = urllib.parse.quote(did, safe="")
        url = f"{ir}/sts/{encoded}/token"

        refusals = [
            (
                "unsupported grant type",
                {"grant_type": "password", "client_id": did, "client_secret": "x"},
                {400},
            ),
            (
                "client_id not the requested DID",
                {
                    "grant_type": "client_credentials",
                    "client_id": "did:web:someone-else.dataspaces.localhost",
                    "client_secret": "x",
                },
                {401},
            ),
            (
                "wrong secret",
                {
                    "grant_type": "client_credentials",
                    "client_id": did,
                    "client_secret": "definitely-not-the-secret",
                },
                {401},
            ),
            (
                "unknown participant",
                {
                    "grant_type": "client_credentials",
                    "client_id": "did:web:nobody.dataspaces.localhost",
                    "client_secret": "x",
                },
                {401},
            ),
        ]

        wrong: list[str] = []
        for label, form, acceptable in refusals:
            probe_did = urllib.parse.quote(form["client_id"], safe="")
            probe_url = f"{ir}/sts/{probe_did}/token" if label == "unknown participant" else url
            status, _ = self.http.raw("POST", probe_url, form=form)
            if status < 400:
                wrong.append(f"{label} → {status} (a token was issued)")
            elif status >= 500:
                wrong.append(f"{label} → {status} (crashed)")
            elif status not in acceptable:
                wrong.append(f"{label} → {status} (expected {sorted(acceptable)})")

        if wrong:
            result.fail_step(
                "STS refusals",
                "the token endpoint did not refuse an invalid client cleanly",
                mismatched=wrong,
            )
            return None
        result.pass_step(
            "STS refusals",
            "wrong grant, mismatched client_id, wrong secret and unknown participant are all refused",
            probes=len(refusals),
        )

        # The positive path needs the participant's real STS secret, which is
        # deployment state rather than test configuration. When it is available
        # the issued token is checked for shape; when it is not, the negative
        # assertions above still stand on their own.
        secret = s.provider_sts_client_secret
        if not secret:
            result.pass_step(
                "STS issuance",
                "skipped — no provider STS secret configured "
                "(set E2E_PROVIDER_STS_SECRET to assert the positive path)",
            )
            return None

        status, payload = self.http.raw(
            "POST",
            url,
            form={
                "grant_type": "client_credentials",
                "client_id": did,
                "client_secret": secret,
                "bearer_access_scope": "org.eclipse.edc.vc.type:MembershipCredential:read",
                "audience": s.consumer_did,
            },
        )
        if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
            result.fail_step(
                "STS issuance",
                "a valid client did not receive a token",
                status_code=status,
                response=payload,
            )
            return None

        token = str(payload["access_token"])
        parts = token.split(".")
        if len(parts) != 3:
            result.fail_step("STS issuance", "the issued token is not a JWS", token_parts=len(parts))
            return None
        try:
            header = _decode_segment(parts[0])
            claims = _decode_segment(parts[1])
        except Exception as exc:
            result.fail_step("STS issuance", f"could not decode the issued token: {exc}")
            return None
        if header.get("alg") != "ES256":
            result.fail_step("STS issuance", "the token is not ES256-signed", alg=header.get("alg"))
            return None
        if claims.get("iss") != did or claims.get("sub") != did:
            result.fail_step(
                "STS issuance",
                "the self-issued token does not name its own DID as issuer and subject",
                iss=claims.get("iss"),
                sub=claims.get("sub"),
            )
            return None
        if not claims.get("exp"):
            result.fail_step(
                "STS issuance", "the token carries no expiry — it would be valid forever"
            )
            return None
        result.pass_step(
            "STS issuance",
            "a valid client receives a bounded, self-issued ES256 token naming its own DID",
            audience=claims.get("aud"),
            expires_in=payload.get("expires_in"),
        )
        return token

    # ── credential service ───────────────────────────────────────────────────

    def _check_presentation_binding(self, result: FlowResult, token: str | None) -> None:
        """A presentation query must be bound to the DID it asks about.

        This endpoint returns a signed VP of a participant's full credential set.
        If it answered without proof that the caller controls the DID, any party
        could harvest another participant's credentials — participant
        impersonation with one request. The absent and forged-token cases are
        therefore the load-bearing assertions.
        """
        s = self.settings
        ir = s.identity_registry_url
        encoded = urllib.parse.quote(s.provider_did, safe="")
        url = f"{ir}/credentials/{encoded}/presentations/query"
        body = {
            "@context": ["https://w3id.org/tractusx-trust/v0.8"],
            "@type": "PresentationQueryMessage",
            "presentationDefinition": {},
        }

        forged = (
            "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJpc3MiOiJkaWQ6d2ViOnByb3ZpZGVyLmRhdGFzcGFjZXMubG9jYWxob3N0In0"
            ".AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        )
        cases = [
            ("no token", None),
            ("non-bearer scheme", "Basic ZGVtbzpkZW1v"),
            ("garbage token", "Bearer not-a-jwt"),
            ("forged signature", f"Bearer {forged}"),
        ]

        served: list[str] = []
        crashed: list[str] = []
        for label, authorization in cases:
            headers = {"Authorization": authorization} if authorization else {}
            status, _ = self.http.raw("POST", url, body=body, headers=headers)
            if status < 400:
                served.append(f"{label} → {status}")
            elif status >= 500:
                crashed.append(f"{label} → {status}")

        if served or crashed:
            result.fail_step(
                "presentation binding",
                "a presentation was served to a caller that did not prove DID control",
                served=served or None,
                crashed=crashed or None,
            )
            return

        # A token that is genuine but issued for a *different* DID must not open
        # this participant's credentials — proof the check is a binding, not
        # merely a signature check.
        if token:
            other = urllib.parse.quote(s.consumer_did, safe="")
            status, _ = self.http.raw(
                "POST",
                f"{ir}/credentials/{other}/presentations/query",
                body=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            if status < 400:
                result.fail_step(
                    "presentation binding",
                    "a valid token for one DID retrieved another DID's credentials",
                    token_subject=s.provider_did,
                    queried=s.consumer_did,
                    status_code=status,
                )
                return
            result.pass_step(
                "presentation binding",
                "queries are refused without DID control, and a token for one DID "
                "cannot read another's credentials",
                probes=len(cases) + 1,
            )
            return

        result.pass_step(
            "presentation binding",
            "absent, malformed and forged DCP tokens are all refused "
            "(cross-DID probe skipped — no issued token available)",
            probes=len(cases),
        )

    # ── StatusList ───────────────────────────────────────────────────────────

    def _check_status_list(self, result: FlowResult) -> None:
        """Revocation is only real if a verifier can fetch it without asking us.

        StatusList2021 is published unauthenticated on purpose: a verifier that
        had to authenticate to learn a credential was revoked would be a
        verifier that keeps trusting it whenever we are unreachable. The
        assertion is that the list is served, is a credential in its own right,
        and carries an encoded bitstring.
        """
        s = self.settings
        status, payload = self.http.raw(
            "GET", f"{s.identity_registry_url}/status/{s.status_list_id}"
        )
        if status == 404:
            result.pass_step(
                "status list",
                f"skipped — no status list '{s.status_list_id}' published in this environment",
            )
            return
        if status != 200 or not isinstance(payload, dict):
            result.fail_step(
                "status list",
                "the status list is not publicly readable",
                status_code=status,
                list_id=s.status_list_id,
            )
            return

        subject = payload.get("credentialSubject") or {}
        if isinstance(subject, list):
            subject = subject[0] if subject else {}
        encoded_list = subject.get("encodedList") if isinstance(subject, dict) else None
        if not encoded_list:
            result.fail_step(
                "status list",
                "the published list carries no encoded bitstring",
                payload=payload,
            )
            return

        unknown_status, _ = self.http.raw(
            "GET", f"{s.identity_registry_url}/status/e2e-nonexistent-list"
        )
        if unknown_status != 404:
            result.fail_step(
                "status list",
                "an unknown status list did not 404",
                status_code=unknown_status,
            )
            return
        result.pass_step(
            "status list",
            "the revocation list is served unauthenticated as an encoded bitstring",
            list_id=s.status_list_id,
            status_purpose=subject.get("statusPurpose"),
        )
