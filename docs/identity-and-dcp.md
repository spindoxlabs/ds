# Identity & DCP (Dataspace Credential Protocol)

This document describes how participant identities are established, how Verifiable Credentials are issued, and how DCP identity verification works during DSP negotiation.

---

## Participant identities

Each participant in the dataspace is identified by a `did:web:` URI. DID documents are dynamically served by the identity-registry service (`services/identity-registry/`) at `GET /dids/{did}/did.json`.

| Participant | DID | DID document |
|-------------|-----|-------------|
| Provider | `did:web:provider.dataspaces.localhost` | `GET /dids/did:web:provider.dataspaces.localhost/did.json` |
| Consumer | `did:web:consumer.dataspaces.localhost` | `GET /dids/did:web:consumer.dataspaces.localhost/did.json` |
| Trust anchor | `did:web:trust-anchor.dataspaces.localhost` | `GET /dids/did:web:trust-anchor.dataspaces.localhost/did.json` |

Identity lifecycle:

- The trust anchor DID is bootstrapped via `ir-cli bootstrap` (first-time setup, idempotent)
- Participant DIDs are created via `ir-cli participant add` or `POST /admin/participants`
- The identity-registry auto-generates EC P-256 key pairs when creating a DID

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

### Key generation

Key generation is handled by the identity-registry's `crypto.py` service (EC P-256 via the `cryptography` library):

- `ir-cli bootstrap` creates the trust-anchor key pair (stored in the database only, not exported to the filesystem)
- `ir-cli participant add` creates a participant key pair and exports the private key to the shared `identity-data` volume
- Key rotation via `ir-cli key rotate` or `POST /admin/keys/rotate/{did}` (deactivates the old key, generates a new one with incremented key index, and re-exports)
- Private keys are exported to `{EXPORT_BASE_PATH}/keys/{name}-key.json` (default `EXPORT_BASE_PATH=/data`)

---

## Verifiable Credentials

Each participant holds a `MembershipCredential` VC issued by the trust anchor. These VCs prove that a participant is a recognized member of the dataspace.

### Issuance

VCs are issued by the identity-registry service:

- `MembershipCredential` VCs are auto-issued when registering a participant via `ir-cli participant add` or `POST /admin/participants`
- Additional membership VCs can be issued via `ir-cli credential issue-membership` or `POST /admin/credentials/membership`
- `DataSubjectCredential` VCs are issued via `ir-cli credential issue-data-subject` or `POST /admin/credentials/data-subject`
- All credentials include a `StatusList2021Entry` for revocation tracking
- Credentials are exported to the shared `identity-data` volume at `{EXPORT_BASE_PATH}/credentials/{name}/membership-vc.json`

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

## Security Token Service (STS)

Each participant runs their own STS instance (`services/sts/`). The STS issues ES256-signed Self-Issued JWTs consumed by EDC during DCP handshake.

STS instances load private keys from the shared `identity-data` volume (exported by identity-registry) rather than from static key files.

### Token flow

1. EDC needs to authenticate to a counterparty during DSP negotiation
2. EDC calls `POST /token` on the participant's STS (OAuth2 `client_credentials`)
3. STS returns an ES256 JWT with claims:

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

### STS endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /token` | Issue SI token (client_credentials grant) |
| `GET /jwks` | Public key (JWKS format) |
| `GET /.well-known/openid-configuration` | OIDC discovery |
| `GET /health` | Liveness check |

### STS instances

| Instance | Port | DID |
|----------|------|-----|
| `sts-provider` | 38080 | `did:web:provider.dataspaces.localhost` |
| `sts-consumer` | 38081 | `did:web:consumer.dataspaces.localhost` |

---

## VC Wallet (Credential Service)

Each participant runs a VC wallet instance (`services/vc-wallet/`) that holds their pre-issued VCs and returns them as Verifiable Presentations when queried by EDC.

Wallets load credentials from the shared `identity-data` volume exported by identity-registry, rather than from static files.

### Presentation query flow

1. During DSP negotiation, EDC calls `POST /api/v1/presentations/query`
2. The wallet wraps all held VCs in a `VerifiablePresentation`
3. EDC includes the VP in the DSP message
4. The counterparty verifies the VP against the sender's DID document

### Wallet instances

| Instance | Port | DID | Credentials path |
|----------|------|-----|-----------------|
| `vc-wallet-provider` | 38082 | `did:web:provider.dataspaces.localhost` | `identity-data/credentials/provider/` |
| `vc-wallet-consumer` | 38083 | `did:web:consumer.dataspaces.localhost` | `identity-data/credentials/consumer/` |

---

## DCP negotiation flow

When a consumer requests a dataset from a provider, the full DCP verification sequence is:

```
Consumer EDC                                     Provider EDC
    │                                                 │
    │  1. Get SI token from STS                       │
    ├─→ sts-consumer POST /token                      │
    │                                                 │
    │  2. Get VP from wallet                          │
    ├─→ vc-wallet-consumer POST /presentations/query  │
    │                                                 │
    │  3. Send DSP CatalogRequest with SI token + VP  │
    ├────────────────────────────────────────────────→ │
    │                                                 │
    │                     4. Verify SI token signature │
    │                        (resolve consumer DID)    │
    │                     5. Verify VP + VC signatures │
    │                        (check trust anchor DID)  │
    │                     6. Check trusted issuer list │
    │                     7. Evaluate ODRL constraints │
    │                        (AccessScope, Consent)    │
    │                                                 │
    │  8. Return catalog / agreement                  │
    │←────────────────────────────────────────────────┤
```

Notes on identity-registry integration:

- **Step 4** (resolve consumer DID): the consumer's DID document is resolved from the identity-registry at `GET /dids/{did}/did.json`
- **Step 5** (check trust anchor DID): the trust anchor's DID document is also served by identity-registry, allowing signature verification against the trust anchor's public key
- Keys and VCs referenced throughout the flow are dynamically managed by identity-registry (creation, rotation, revocation)

### EDC trust configuration

Provider EDC is configured to trust the trust anchor as a VC issuer:

```properties
# services/connector/config/provider.properties
edc.iam.trustedissuer.0.id=did:web:trust-anchor.dataspaces.localhost
```

---

## DSSC Blueprint alignment

| Building Block | Implementation |
|---------------|---------------|
| BB01 (Trust Framework) | Trust anchor issues membership VCs; EDC verifies issuer chain |
| BB02 (Identity & Attestation) | `did:web:` URIs with `JsonWebKey2020`, ES256 SI tokens; identity-registry manages DID lifecycle, key generation, and VC issuance |
| DCP | Full Dataspace Credential Protocol via EDC `controlplane-dcp-bom` |
