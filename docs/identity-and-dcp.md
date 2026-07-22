# Identity & DCP (Dataspace Credential Protocol)

This document describes how participant identities are established, how Verifiable Credentials are issued, and how DCP identity verification works during DSP negotiation.

---

## Participant identities

Each participant in the dataspace is identified by a `did:web:` URI. The identity-registry (`services/identity-registry/`) is the single source of truth for all identity operations (DSSC BB02). DID documents are served dynamically from the identity-registry's database — EDC resolves them directly via the `identity-did-web` module over HTTP (`edc.iam.did.web.use.https=false`), with `*.dataspaces.localhost` hostnames resolving via Docker network aliases on the Caddy service. DID resolution is also available on port 9010 for host-side development and testing.

| Participant | DID | Resolution path |
|-------------|-----|----------------|
| Provider | `did:web:provider.dataspaces.localhost` | identity-registry `GET /dids/did:web:provider.dataspaces.localhost/did.json` |
| Consumer | `did:web:consumer.dataspaces.localhost` | identity-registry `GET /dids/did:web:consumer.dataspaces.localhost/did.json` |
| Trust anchor | `did:web:trust-anchor.dataspaces.localhost` | identity-registry `GET /dids/did:web:trust-anchor.dataspaces.localhost/did.json` |

### Dual roles

A participant can hold multiple roles (e.g. both provider and consumer). The `roles` field on the participant record is a JSON array (e.g. `["provider", "consumer"]`). One MembershipCredential VC is issued per role, each with a single `credentialSubject.role` value (e.g. `"Provider"` or `"Consumer"`). This aligns with the DSSC blueprint where Role VCs are separate credentials.

Each connector instance still runs as a single role at runtime — a dual-role participant deploys two connector instances sharing the same DID.

### DID lifecycle

- **Trust anchor bootstrap:** `ir-cli bootstrap` creates the trust anchor DID with an auto-generated EC P-256 key pair and a self-issued MembershipCredential (idempotent, first-time setup)
- **Participant registration:** `ir-cli participant add` or `POST /admin/participants` creates a participant DID with an auto-generated EC P-256 key pair and one MembershipCredential per role
- **Key rotation:** `ir-cli key rotate` or `POST /admin/keys/rotate/{did}` deactivates the current key, generates a new one with an incremented key index, and updates the DID document

Private keys are stored in the identity-registry's database and never leave the identity-registry process. EDC connectors access identity operations (STS signing, credential presentations) through the identity-registry's HTTP API.

### DID document structure

Each DID document contains an EC P-256 `JsonWebKey2020` verification method with `assertionMethod`:

```json
{
  "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/suites/jws-2020/v1"],
  "id": "did:web:provider.dataspaces.localhost",
  "verificationMethod": [{
    "id": "did:web:provider.dataspaces.localhost#key-1",
    "type": "JsonWebKey2020",
    "controller": "did:web:provider.dataspaces.localhost",
    "publicKeyJwk": { "kty": "EC", "crv": "P-256", "x": "...", "y": "...", "kid": "did:web:provider.dataspaces.localhost#key-1", "use": "sig" }
  }],
  "assertionMethod": ["did:web:provider.dataspaces.localhost#key-1"],
  "authentication": ["did:web:provider.dataspaces.localhost#key-1"]
}
```

---

## Verifiable Credentials

Each participant holds a `MembershipCredential` VC issued by the trust anchor. These VCs prove that a participant is a recognized member of the dataspace.

### Issuance

VCs are issued by the identity-registry:

- `MembershipCredential` VCs are auto-issued when registering a participant via `ir-cli participant add` or `POST /admin/participants`
- Additional membership VCs can be issued via `ir-cli credential issue-membership` or `POST /admin/credentials/membership`
- `DataSubjectCredential` VCs are issued via `ir-cli credential issue-data-subject` or `POST /admin/credentials/data-subject`
- All credentials include a `StatusList2021Entry` for revocation tracking

### VC structure

```json
{
  "@context": [
    "https://www.w3.org/2018/credentials/v1",
    "https://w3id.org/security/suites/jws-2020/v1",
    "https://dataspaces.localhost/ns/credentials/v1"
  ],
  "id": "urn:uuid:...",
  "type": ["VerifiableCredential", "MembershipCredential"],
  "issuer": "did:web:trust-anchor.dataspaces.localhost",
  "issuanceDate": "2026-01-01T00:00:00Z",
  "expirationDate": "2027-01-01T00:00:00Z",
  "credentialSubject": {
    "id": "did:web:provider.dataspaces.localhost",
    "memberOf": "https://dataspaces.localhost/dataspace",
    "role": "Provider",
    "allowedScopes": ["dataspaces.query"]
  },
  "credentialStatus": {
    "id": "https://trust-anchor.dataspaces.localhost/status/1#0",
    "type": "StatusList2021Entry",
    "statusPurpose": "revocation",
    "statusListIndex": "0",
    "statusListCredential": "https://trust-anchor.dataspaces.localhost/status/1"
  },
  "proof": {
    "type": "JsonWebSignature2020",
    "created": "2026-01-01T00:00:00Z",
    "verificationMethod": "did:web:trust-anchor.dataspaces.localhost#key-1",
    "proofPurpose": "assertionMethod",
    "jws": "..."
  }
}
```

---

## STS token signing

EDC connectors obtain Self-Issued (SI) tokens by calling the identity-registry directly. The identity-registry signs ES256 JWTs using the participant's database-stored private key.

### Token flow

1. EDC needs to authenticate to a counterparty during DSP negotiation
2. EDC calls `POST /sts/{did}/token` on the identity-registry (OAuth2 `client_credentials` grant)
3. The identity-registry looks up the participant's private key in its database, signs an ES256 JWT, and returns it

### SI token claims

```json
{
  "iss": "did:web:provider.dataspaces.localhost",
  "sub": "did:web:provider.dataspaces.localhost",
  "aud": "did:web:consumer.dataspaces.localhost",
  "iat": 1700000000,
  "exp": 1700003600,
  "jti": "unique-id",
  "bearerAccessScope": "dataspaces.query"
}
```

---

## Credential presentations

EDC connectors obtain Verifiable Presentations by calling the identity-registry directly. The identity-registry builds VPs from the participant's database-stored VCs.

### Presentation query flow

1. During DSP negotiation, EDC calls `POST /credentials/{did}/presentations/query` on the identity-registry
2. The identity-registry retrieves the participant's VCs from its database, wraps them in a `VerifiablePresentation`, and returns it
3. EDC includes the VP in the DSP message
4. The counterparty verifies the VP against the sender's DID document (resolved directly from the identity-registry)

---

## DCP negotiation flow

When a consumer requests a dataset from a provider, the full DCP verification sequence is:

```
Consumer EDC                                     Provider EDC
    |                                                 |
    |  1. Get SI token from identity-registry         |
    |---> POST /sts/{consumer-did}/token              |
    |                                                 |
    |  2. Get VP from identity-registry               |
    |---> POST /credentials/{consumer-did}/           |
    |     presentations/query                         |
    |                                                 |
    |  3. Send DSP request with SI token + VP         |
    |------------------------------------------------>|
    |                                                 |
    |                     4. Verify SI token signature |
    |                        identity-registry        |
    |                        GET /dids/{consumer-did}/|
    |                        did.json                 |
    |                                                 |
    |                     5. Verify VC issuer          |
    |                        identity-registry        |
    |                        GET /dids/{trust-anchor- |
    |                        did}/did.json            |
    |                                                 |
    |                     6. Check trusted issuer list |
    |                                                 |
    |                     7. Evaluate ODRL constraints |
    |                        AccessScopeFunction -->  |
    |                        ds-connector -->          |
    |                        identity-registry        |
    |                        /admin/participants/check |
    |                                                 |
    |  8. Return DSP response                         |
    |<------------------------------------------------|
```

### Step details

1. **SI token:** Consumer EDC calls `POST /sts/{consumer-did}/token` on the identity-registry. The identity-registry signs an ES256 JWT using the consumer's database-stored private key.
2. **VP:** Consumer EDC calls `POST /credentials/{consumer-did}/presentations/query` on the identity-registry. The identity-registry builds a VP from the consumer's database-stored VCs.
3. **DSP request:** Consumer EDC sends the DSP CatalogRequest (or negotiation message) with the SI token and VP attached.
4. **SI token verification:** Provider EDC resolves the consumer's DID document directly from the identity-registry (`GET /dids/{consumer-did}/did.json`) via the `identity-did-web` module and verifies the SI token signature against the consumer's public key.
5. **VC issuer verification:** Provider EDC resolves the trust anchor's DID document directly from the identity-registry (`GET /dids/{trust-anchor-did}/did.json`) and verifies the VC signatures against the trust anchor's public key.
6. **Trusted issuer check:** Provider EDC checks that the VC issuer DID is in its configured trusted issuer list.
7. **ODRL constraint evaluation:** Provider EDC's AccessScopeFunction calls ds-connector, which calls the identity-registry at `/admin/participants/check` for scope validation.
8. **DSP response:** Provider EDC returns the catalog, agreement, or transfer response.

### EDC trust configuration

Provider EDC is configured to trust the trust anchor as a VC issuer:

```properties
# services/connector/config/provider.properties
edc.iam.trusted-issuer.0.id=did:web:trust-anchor.dataspaces.localhost
```

---

## EDR signing key separation (DSSC BB05)

EDR (Endpoint Data Reference) tokens use a separate non-DID key stored in the EDC vault, distinct from the DID-bound keys managed by the identity-registry. This separation ensures that BB05 (Data Exchange) signing is independent from BB02 (Identity & Attestation) key material.

---

## DSSC Blueprint alignment

| Building Block | Implementation |
|---------------|---------------|
| BB01 (Trust Framework) | Local trust anchor created via `ir-cli bootstrap`; trust anchor issues MembershipCredentials; EDC verifies issuer chain |
| BB02 (Identity & Attestation) | identity-registry: DID lifecycle, key management, VC issuance, STS token signing, credential presentation service; `did:web:` URIs with `JsonWebKey2020` and ES256 signatures |
| BB05 (Data Exchange) | EDC connectors with DCP; separate EDR signing keys in EDC vault (independent from BB02 identity keys) |
| DCP | Full Dataspace Credential Protocol: EDC connectors call identity-registry for SI tokens, VPs, and DID document resolution (directly, no proxy) |

---

## Multi-dataspace federation (future work)

Cross-dataspace interaction (e.g. providers in dataspace X negotiating with consumers in dataspace Y) is architecturally supported but not yet implemented.

### What works today

- **`did:web` cross-domain resolution:** DID documents resolve via standard HTTP GET — a connector in dataspace X can resolve `did:web:participant.dataspace-y.example` if network-reachable
- **StatusList revocation checks:** `statusListCredential` URLs are absolute HTTP URIs — any verifier from any dataspace can check revocation status
- **EDC multi-trusted-issuer:** EDC supports multiple trusted issuers via indexed properties (`edc.iam.trusted-issuer.N.id`), allowing a connector to trust VCs from multiple trust anchors

### Gaps

- **Automated trust anchor discovery:** No trust anchor registry federation — trust anchors must be manually configured per connector
- **Cross-dataspace participant registration:** The identity-registry's scope check (`/admin/participants/check`) only knows local participants — foreign participants would fail scope validation
- **Catalogue federation:** DSSC BB05 describes harvestable DCAT catalogues for cross-space discovery, not yet implemented

### DSSC blueprint references

- BB01 (Trust Framework): supports multiple trust anchors per dataspace (§4.1)
- BB05 (Publication & Discovery): standardised `GET /catalogue` for cross-space harvesting (§8.3)
- Services Architecture: extensible to cross-data-space federation (§5.4)
