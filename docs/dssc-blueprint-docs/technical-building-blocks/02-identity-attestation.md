# 02 — Identity and Attestation Management

> **Building block type**: Participant Agent + Facilitating (federation-level)  
> **Depends on**: 00-foundational-standards, 01-trust-framework  
> **Required by**: 03-access-usage-policies, 07-provenance-traceability, 09-data-sovereignty

---

## Purpose

Where the Trust Framework defines *which* trust services are authorised, Identity & Attestation Management is the **operational mechanism** that makes those rules real at runtime. It answers two questions for every interaction:

- **Identity**: who exactly is this participant? (cryptographically verifiable identifier)
- **Attestation**: what can we verifiably claim about them? (signed claims from a trusted issuer)

These are distinct concepts. Identity is the identifier; attestation is the set of signed claims attached to it. Both are required before a policy decision can be made.

---

## Identity Subject Types

A data space must manage identity for three distinct subject types:

| Subject | Description | Primary standards |
|---|---|---|
| **Legal entity** | A company or organisation | eIDAS 2.0 EUDIW · GLEIF LEI · X.509 PKI |
| **Natural person** | An individual or representative | eIDAS 2.0 EUDIW · OIDC · OIDC4VP |
| **Software agent** | A connector or automated system | did:key · did:web · OAuth 2.0 client credentials · mTLS |

All three receive a DID and one or more Verifiable Credentials to participate in a data space.

---

## Decentralised Identifiers (DIDs) — The Identifier Layer

### What a DID Is

A DID is a globally unique, cryptographically verifiable identifier that the holder controls via a private key. It does not require a central registry — control is proven by the ability to sign with the corresponding private key.

**DID syntax:**
```
did:method:method-specific-identifier
did:web:example-company.eu:participants:acme-corp
did:key:z6Mkf5rGMoatrSj1f4CyvuHBeXJELe9RPdzo2PKGNCKVtZxP
```

### DID Methods

| Method | Use case | Resolution |
|---|---|---|
| `did:web` | Legal entities with a known domain | Resolves to JSON-LD document at `https://{domain}/.well-known/did.json` |
| `did:key` | Ephemeral or machine identities | Self-contained — no external resolution needed |
| `did:ebsi` | EU-native, EBSI-anchored identity | Resolves via European Blockchain Services Infrastructure |

**Recommended method for organisations**: `did:web` — it is the most pragmatic for companies as the DID is tied to a domain the organisation already controls and administers.

### DID Document

The DID resolves to a DID Document containing:

```json
{
  "@context": ["https://www.w3.org/ns/did/v1"],
  "id": "did:web:example-company.eu",
  "verificationMethod": [{
    "id": "did:web:example-company.eu#key-1",
    "type": "JsonWebKey2020",
    "controller": "did:web:example-company.eu",
    "publicKeyJwk": { "kty": "EC", "crv": "P-256", ... }
  }],
  "authentication": ["did:web:example-company.eu#key-1"],
  "service": [{
    "id": "did:web:example-company.eu#connector",
    "type": "DataspaceConnector",
    "serviceEndpoint": "https://connector.example-company.eu"
  }]
}
```

---

## Verifiable Credentials (VCs) — The Attestation Layer

### VC Structure

```json
{
  "@context": [
    "https://www.w3.org/2018/credentials/v1",
    "https://w3id.org/security/suites/jws-2020/v1"
  ],
  "type": ["VerifiableCredential", "DataspaceMembershipCredential"],
  "issuer": "did:web:governance-authority.eu",
  "issuanceDate": "2025-01-15T09:00:00Z",
  "expirationDate": "2026-01-15T09:00:00Z",
  "credentialSubject": {
    "id": "did:web:example-company.eu",
    "memberOf": "https://dataspace.energy.eu",
    "role": "DataProvider",
    "complianceCertifications": ["ISO27001", "GDPR-DPO"]
  },
  "credentialStatus": {
    "id": "https://governance-authority.eu/status/2025#42",
    "type": "StatusList2021Entry",
    "statusListIndex": "42",
    "statusListCredential": "https://governance-authority.eu/status/2025"
  },
  "proof": {
    "type": "JsonWebSignature2020",
    "created": "2025-01-15T09:00:00Z",
    "verificationMethod": "did:web:governance-authority.eu#key-1",
    "jws": "eyJhbGciOiJFZERTQSIsImI2NCI6ZmFsc2V9..."
  }
}
```

### Credential Types in a Data Space

| VC Type | Issued by | Claims |
|---|---|---|
| **Membership** | Governance authority | Participant is admitted to the data space |
| **Role** | Governance authority | DataProvider / DataConsumer / ServiceProvider |
| **Compliance** | Certification body | ISO 27001 / GDPR / sector-specific |
| **Capability** | Self-asserted or endorsed | Supported protocols, data formats, processing categories |
| **Consent** | Consent management service | GDPR-compliant processing consent for a data subject |

---

## VC Lifecycle

```
1. ONBOARDING    Participant applies → submits evidence
2. VERIFICATION  Issuer verifies legal identity and compliance
3. ISSUANCE      VC signed with issuer's private key → delivered to holder
4. STORAGE       Held in participant's VC wallet (connector-side)
5. PRESENTATION  Holder creates Verifiable Presentation (VP) → presents via OIDC4VP
6. VERIFICATION  Verifier checks: signature valid? issuer trusted? not revoked?
7. LIFECYCLE     Expiry monitoring → renewal → revocation on offboarding
```

### Verifiable Presentation (VP)

When presenting credentials, the holder assembles a VP — a signed wrapper that selects which VCs to disclose. This allows selective disclosure: a participant can prove membership without revealing other credentials.

```json
{
  "@context": ["https://www.w3.org/2018/credentials/v1"],
  "type": "VerifiablePresentation",
  "holder": "did:web:example-company.eu",
  "verifiableCredential": [ /* selected VCs */ ],
  "proof": { /* holder's signature over the VP */ }
}
```

---

## Natural Person Identity — Special Requirements

When a data space involves natural persons (B2C, C2B, C2I2B scenarios), the identity management capability must handle natural person identity in addition to legal entity identity.

### Key additional requirements:

**GDPR Article 6 legal basis**: Any processing of natural person identity data requires a documented legal basis. Consent management must be integrated with the identity layer.

**eIDAS 2.0 EU Digital Identity Wallet (EUDIW)**: The EUDIW provides a standardised, government-issued VC wallet for EU citizens. Data spaces targeting consumer participation should plan for EUDIW compatibility.

**Personal Data Intermediary (PDI)**: In B2I2B and C2I2B scenarios, an intermediary manages identity and consent on behalf of natural persons. PDIs operating under the EU Data Governance Act must be registered as data intermediation service providers.

### Scenario matrix for identity requirements:

| Scenario | Identity type needed | Consent management |
|---|---|---|
| B2B (non-personal data) | Legal entity only | Not required |
| B2B (with personal data) | Legal entity + natural person | Required (cross-organisational) |
| B2C | Legal entity + consumer | Required if personal data involved |
| C2B | Natural person as provider | Required (GDPR legal basis for collection) |
| C2I2B | Natural person + intermediary | Required (PDI manages consent) |

---

## Implementation Architecture

```
┌─────────────────────────────────────────────────┐
│              VC Wallet (per participant)         │
│  - Stores issued credentials                    │
│  - Creates Verifiable Presentations on request  │
│  - Manages key material (HSM recommended)       │
└────────────────────┬────────────────────────────┘
                     │ OIDC4VP
┌────────────────────▼────────────────────────────┐
│          Presentation Endpoint (connector)       │
│  - Accepts VP requests                          │
│  - Returns signed VPs                           │
│  - Rate-limited and logged                      │
└────────────────────┬────────────────────────────┘
                     │ DID resolution + sig verify
┌────────────────────▼────────────────────────────┐
│          Verification Service (verifier side)    │
│  - Resolves issuer DID Document                 │
│  - Verifies JWS signature                       │
│  - Checks W3C Status List 2021 revocation       │
│  - Returns verified claims to Policy Engine     │
└─────────────────────────────────────────────────┘
```

---

## Implementation Checklist

- [ ] Assign a DID to every participant (legal entity and each connector)
- [ ] Implement `did:web` DID Document endpoint at `/.well-known/did.json`
- [ ] Implement VC wallet with secure key storage (HSM or equivalent)
- [ ] Implement OIDC4VP presentation endpoint
- [ ] Implement VP verification (DID resolution, signature check, revocation check)
- [ ] Implement W3C Status List 2021 issuer-side status publication
- [ ] Define credential schemas and publish in vocabulary hub
- [ ] Implement credential expiry monitoring and renewal workflow
- [ ] For natural-person scenarios: integrate consent management service
- [ ] For cross-border scenarios: assess eIDAS 2.0 EUDIW compatibility

---

## Key Design Decisions

**Key management**: Private keys used to sign VPs must be protected. For production, use a Hardware Security Module (HSM) or a cloud KMS with attestation. Never store private keys in application configuration files.

**DID Document caching**: DID Documents should be cached with a TTL matching the expected update frequency. Cache invalidation must be triggered when a participant rotates keys (key rotation must be a supported operation).

**Schema governance**: Credential schemas must be versioned. A v1 membership credential issued before a schema change must still be verifiable. Implement schema versioning in the `@context` URL.

---

## References

- [W3C DID Core 1.0](https://www.w3.org/TR/did-core/)
- [W3C Verifiable Credentials 2.0](https://www.w3.org/TR/vc-data-model-2.0/)
- [W3C Status List 2021](https://www.w3.org/community/reports/credentials/CG-FINAL-vc-status-list-2021-20230102/)
- [OpenID Connect for Verifiable Presentations](https://openid.net/specs/openid-4-verifiable-presentations-1_0.html)
- [eIDAS 2.0 — EU Digital Identity Wallet](https://digital-strategy.ec.europa.eu/en/policies/eu-digital-identity)
- [GLEIF LEI — Legal Entity Identifier](https://www.gleif.org/en/lei-solutions/api-use-the-lei)
- [EU Data Governance Act — Data Intermediaries](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R0868)
