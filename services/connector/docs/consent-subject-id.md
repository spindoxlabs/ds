# Subject Identity in the Consent System

How subject identity flows from authentication through consent management to row-level data filtering.

---

## Subject identity chain

The consent system uses DIDs (Decentralized Identifiers) as the canonical subject identity. The identity flows through five stages:

| Stage | Component | What happens |
|-------|-----------|-------------|
| 1. Authentication | Keycloak | User authenticates via OIDC; JWT includes `dataspace_did` claim (set by the dataspace scope) |
| 2. Token parsing | Portal (`subjectFromAccessToken`) | Extracts subject ID from JWT using priority chain (see below) |
| 3. Header propagation | Portal -> ds-connector | Portal passes subject ID via `X-Subject-Id` header on consent API calls |
| 4. Consent storage | ds-connector | Stores subject ID in `ConsentRecord.subject_id` |
| 5. Row filtering | dataset-api -> ds-connector | Calls `GET /internal/consent/check`, gets consented subject IDs, filters rows |

### Subject ID priority chain

`subjectFromAccessToken` in `src/routes/demo/+page.server.ts` resolves the subject ID using the first available value:

```
DEMO_SUBJECT_ID env var
  -> dataspace_did JWT claim
    -> preferred_username JWT claim
      -> sub JWT claim
        -> fallback
```

This chain is backward compatible -- if `dataspace_did` is not present in the JWT (e.g. before identity-registry sync), the existing `preferred_username` or `sub` claims are used.

---

## Why DIDs for subject identity

- **Stability**: Keycloak `preferred_username` is a display name that users can change; it is not a stable identifier
- **Canonical identity**: DIDs are the standard dataspace identifier for participants and subjects
- **Cross-participant consistency**: The same DID identifies a subject across all participants in the dataspace
- **Credential binding**: The `dataspace_did` attribute is populated by identity-registry's Keycloak sync (`POST /admin/keycloak/sync`), linking the Keycloak account to the subject's DataSubjectCredential

---

## End-to-end flow

```mermaid
sequenceDiagram
    participant User
    participant KC as Keycloak
    participant IR as identity-registry
    participant Portal as ds-portal
    participant Conn as ds-connector
    participant DA as dataset-api

    Note over IR,KC: Onboarding (one-time)
    IR->>KC: POST /admin/keycloak/sync
    Note over KC: Sets dataspace_did user attribute

    Note over User,DA: Login and consent
    User->>KC: Authenticate (OIDC)
    KC-->>User: JWT with dataspace_did claim
    User->>Portal: Access consent portal
    Portal->>Portal: subjectFromAccessToken extracts DID
    Portal->>Conn: GET /consent/my (X-Subject-Id: did:web:...)
    Conn-->>Portal: Consent requests for this subject

    Note over User,DA: Consent approval
    User->>Portal: Approve consent request
    Portal->>Conn: POST /consent/my/{id}/approve (X-Subject-Id: did:web:...)
    Conn->>Conn: Store subject_id in ConsentRecord

    Note over User,DA: Data query with row filtering
    DA->>Conn: GET /internal/consent/check?dataset_id=...&consumer_did=...
    Conn-->>DA: { subject_ids: ["did:web:subject1", "did:web:subject2"] }
    DA->>DA: WHERE user_filter_column IN (subject_ids)
    DA-->>User: Filtered rows (only consented subjects)
```

---

## Configuration

| Variable | Component | Purpose |
|----------|-----------|---------|
| `DEMO_SUBJECT_ID` | Portal | Override subject ID for development/testing (highest priority) |
| `dataspace_did` | Keycloak user attribute | Set by identity-registry sync; appears as JWT claim |

---

## Related

- [Consent & Data Sovereignty](../../../docs/consent-and-sovereignty.md) -- consent lifecycle and enforcement
- [ds-connector README](../README.md) -- consent API endpoints
- [ds-portal README](../../portal/README.md) -- authentication and route access
