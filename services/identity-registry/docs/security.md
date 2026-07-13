# Identity Registry -- Security Model

This document describes the authentication, key management, credential lifecycle,
and network security architecture of the Identity Registry service.

## Authentication model

The service defines three trust levels for its endpoints.

### Admin endpoints (`/admin/*`)

Admin endpoints require a JWT Bearer token containing the `identity-registry.admin`
scope in the `scope` claim (space-separated string).

Token verification depends on configuration:

- **When `OIDC_ISSUER_URL` is set:** the service performs JWKS discovery via
  `{issuer_url}/.well-known/openid-configuration` and verifies the token
  signature using RS256 or ES256.
- **When `OIDC_ISSUER_URL` is NOT set (dev mode):** the JWT is decoded without
  signature verification -- the token is parsed but not cryptographically
  verified. This mode is intended for development only.

Scope enforcement applies in both modes: the token must contain
`identity-registry.admin` in the `scope` claim.

HTTP responses:

- `401` -- missing or invalid token
- `403` -- valid token but missing required scope

> **Note:** The Keycloak mapping endpoints (`/keycloak/mapping/*`) also require
> the `identity-registry.admin` scope despite being registered on the internal
> router.

### Internal endpoints (`/participants`, `/participants/{did}/check`)

Internal endpoints require no authentication. They rely on network-level trust:
the service uses `expose:` rather than `ports:` in Docker Compose, so these
endpoints are only reachable from within the container network.

### Public endpoints (`/dids/{did}/did.json`, `/status/{list-id}`, `/health`)

Public endpoints require no authentication. DID documents and status lists are
meant to be publicly resolvable by design.

## Key management

### Key generation

- EC P-256 key pairs are generated via the `cryptography` library (`ec.SECP256R1()`).
- Key ID format: `{did}#key-{index}` (e.g. `did:web:provider.dataspaces.localhost#key-1`).

### Storage

- Private keys are stored in the database as JSONB (`private_jwk` column in
  the `keys` table).
- Private JWK format: `{kty: "EC", crv: "P-256", x, y, d, kid, use: "sig"}`.
- Public JWK: same structure without the `d` parameter.

### Trust anchor vs. participant keys

- The **trust anchor** private key stays in the database only -- it is NOT
  exported to the shared volume (the bootstrap command does not call
  `export_private_key`).
- **Participant keys** can be exported to the shared volume (via `export.py`)
  for STS consumption at `/data/keys/{name}-key.json`.

### Key rotation

When a key is rotated:

1. The old key is marked inactive (`active=False`, `rotated_at` timestamp set).
2. A new key is generated with an incremented index.
3. The DID record is updated to point to the new key.

## Credential lifecycle

### Issuance

- `MembershipCredential` -- auto-issued when registering participants (via CLI
  or API).
- `DataSubjectCredential` -- issued on demand via API or CLI.
- All credentials include a `credentialStatus` field with a `StatusList2021Entry`.

### StatusList2021 revocation tracking

- 16 KB bitstring = 131072 slots (`BITSTRING_SIZE = 16384` bytes).
- Each credential receives a slot index at issuance.
- Revocation flips the bit at the credential's slot index.
- The bitstring is stored compressed (zlib + base64) when served.
- The `StatusList2021Credential` is served at `GET /status/{list-id}`.

### Revocation

- Revoking a credential sets `status=revoked` and the `revoked_at` timestamp,
  and flips the corresponding bit in the StatusList.
- Deactivating a participant also revokes all their active credentials.

## Network security

| Layer | Mechanism |
|---|---|
| Container isolation | `expose:` (not `ports:`) in Docker Compose -- service is only reachable from within the container network |
| Admin endpoints | JWT scope validation (`identity-registry.admin`) |
| Internal endpoints | Network-restricted (no auth, but not exposed to the host) |
| Public endpoints | Intentionally open -- DID resolution and status lists must be publicly accessible |
| Health check | `GET /health` returns service status, no auth required |

## Export and volume security

- Private keys are exported to the shared volume at
  `{EXPORT_BASE_PATH}/keys/{name}-key.json`.
- Credentials are exported to
  `{EXPORT_BASE_PATH}/credentials/{name}/{filename}`.
- The shared volume (`identity-data`) is mounted by the STS and vc-wallet
  containers.
- The trust anchor private key is NOT exported -- it stays in the database only.
- Exported files are plain JSON with no encryption at the filesystem level.
  The volume itself should be secured at the infrastructure layer.

## Production hardening checklist

- [ ] Set `IDENTITY_REGISTRY_OIDC_ISSUER_URL` to enable JWT signature verification on admin endpoints
- [ ] Replace the default `IDENTITY_REGISTRY_ENCRYPTION_KEY` with a strong Fernet key (default: `dev-encryption-key-change-in-production`)
- [ ] Use external secret management (e.g. Vault, cloud KMS) for the encryption key
- [ ] Replace default `KEYCLOAK_CLIENT_SECRET` (`insecure-dev-secret`)
- [ ] Enable mTLS for internal endpoints in production
- [ ] Review key rotation frequency -- currently manual via `ir-cli key rotate` or `POST /admin/keys/rotate/{did}`
- [ ] Restrict shared volume permissions (`identity-data`)
- [ ] Consider encrypting exported private keys on disk (currently plain JSON)
- [ ] Enable audit logging for admin operations
- [ ] Set up monitoring for StatusList capacity (131072 slots)
