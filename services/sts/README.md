# ds-sts

A minimal Security Token Service (STS) for the Dataspace Credential Protocol. Each participant runs their own instance. Issues ES256-signed Self-Issued ID tokens used by EDC during DSP negotiation as proof of participant identity.

Provider port: `38080`
Consumer port: `38081`
Caddy URLs: `https://sts-provider.dataspaces.localhost`, `https://sts-consumer.dataspaces.localhost`

---

## Purpose

In the DCP identity flow, when an EDC connector initiates a DSP request to a counterparty, it first calls its configured STS to obtain a signed JWT. This JWT is presented as the Bearer token in the DSP request header, proving the requester's identity by containing the participant DID as `sub` and `iss`.

The counterparty EDC verifies the JWT by resolving the participant's `did:web:` DID document and checking the signature against the `publicKeyJwk` in the verification method.

This service handles that token issuance step.

---

## Endpoints

### `POST /token`

OAuth2 `client_credentials` grant. Issues a signed ES256 JWT (Self-Issued ID token).

Request form fields:
- `grant_type` — must be `client_credentials`
- `client_id` — participant DID (e.g. `did:web:provider.dataspaces.localhost`)
- `client_secret` — shared secret matching `STS_CLIENT_SECRET`
- `scope` (optional) — placed in `bearerAccessScope` claim
- `audience` (optional) — JWT `aud` claim; defaults to the DSP audience URI

Response:
```json
{
  "access_token": "<es256-jwt>",
  "token_type": "bearer",
  "expires_in": 300,
  "scope": "dataspaces.query"
}
```

Token claims:
- `iss` — participant DID
- `sub` — participant DID
- `aud` — counterparty or DSP audience
- `iat`, `exp`, `jti` — standard claims
- `bearerAccessScope` — EDC reads this for scope-based policy evaluation

### `GET /jwks`

Returns the participant's public key as a JWKS. EDC and counterparties use this to verify tokens issued by this STS.

### `GET /.well-known/openid-configuration`

OIDC discovery document pointing to the token endpoint and JWKS URI.

### `GET /health`

Liveness check.

---

## Key management

The private key is an EC P-256 JWK stored in a JSON file at `STS_PRIVATE_KEY_PATH`. The matching public key is embedded in the participant's DID document at `caddy/did/{participant}.dataspaces.localhost/did.json`.

For dev, private keys are at `src/ds/connector/config/{participant}-key.json`. Regenerate with `scripts/gen-keys.sh`.

---

## Configuration

All settings use the `STS_` prefix:

- `STS_PARTICIPANT_DID` — participant DID URI
- `STS_PRIVATE_KEY_PATH` — path to the JWK private key file
- `STS_CLIENT_ID` — OAuth2 client ID (should match participant DID)
- `STS_CLIENT_SECRET` — shared secret used to authenticate the EDC connector
- `STS_TOKEN_TTL` — JWT validity in seconds (default 300)

The matching EDC properties:
```properties
edc.iam.sts.oauth.token.url=http://sts-provider:8080/token
edc.iam.sts.oauth.client.id=did:web:provider.dataspaces.localhost
edc.iam.sts.oauth.client.secret.alias=sts-provider-client-secret
```

The alias `sts-provider-client-secret` is resolved from the EDC filesystem vault at `src/ds/connector/config/provider-vault.properties`.

---

## Development

```bash
cd src/ds/sts
uv sync
uvicorn ds.sts.main:app --reload --port 38080
```

```bash
docker compose -f docker-compose.yml up
```
