"""ds-sts — minimal Security Token Service for DCP.

Issues Self-Issued ID Tokens (SI tokens) that EDC presents during DSP
negotiation as proof of identity. Each participant runs its own STS instance.

Token flow (EDC DCP):
  1. EDC connector calls POST /token with client_credentials grant
  2. STS issues a signed JWT (ES256) where:
       - sub / iss = participant DID
       - jti = unique token ID
       - bearerAccessScope = requested access scope
  3. EDC includes this JWT as Bearer token in DSP requests
  4. Counterparty EDC verifies the JWT signature via the DID document's publicKeyJwk

Endpoints:
  POST /token            OAuth2 client_credentials → signed SI JWT
  GET  /jwks             JWKS (public key) for token verification
  GET  /.well-known/openid-configuration  OIDC discovery
  GET  /health
"""
from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, status
from fastapi.responses import JSONResponse

from .config import get_settings
from .metrics import install_metrics
from .token import create_si_token, get_public_jwk

app = FastAPI(title="ds-sts", version="0.1.0")
install_metrics(app, "ds-sts")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/jwks")
def jwks():
    """Return the JWKS containing the participant's public key."""
    return {"keys": [get_public_jwk()]}


@app.get("/.well-known/openid-configuration")
def openid_configuration():
    s = get_settings()
    base = f"https://sts-{s.participant_did.split(':')[-1]}"
    return {
        "issuer": s.participant_did,
        "token_endpoint": f"{base}/token",
        "jwks_uri": f"{base}/jwks",
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
    }


@app.post("/token")
async def token(
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    client_secret: Annotated[str, Form()],
    scope: Annotated[str | None, Form()] = None,
    audience: Annotated[str | None, Form()] = None,
    bearer_access_scope: Annotated[str | None, Form()] = None,
    token: Annotated[str | None, Form()] = None,
):
    """Issue a Self-Issued ID Token (ES256) for the registered client."""
    s = get_settings()

    if grant_type != "client_credentials":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_grant_type"},
        )

    if client_id != s.client_id or client_secret != s.client_secret:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client"},
        )

    now = int(time.time())
    claims = {
        "iss": s.participant_did,
        "sub": s.participant_did,
        "aud": [audience or "https://w3id.org/dspace/2024/1/dsp"],
        "iat": now,
        "exp": now + s.token_ttl,
        "jti": str(uuid.uuid4()),
    }
    requested_scope = bearer_access_scope or scope
    if requested_scope:
        claims["bearer_access_scope"] = requested_scope
        claims["bearerAccessScope"] = requested_scope
    claims["token"] = token or str(uuid.uuid4())
    token_str = create_si_token(claims)
    return JSONResponse({
        "access_token": token_str,
        "token_type": "bearer",
        "expires_in": s.token_ttl,
        "scope": requested_scope or "",
    })
