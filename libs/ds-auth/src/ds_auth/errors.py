"""Authentication / authorization errors — framework-free.

The FastAPI layer (:mod:`ds_auth.fastapi`) maps these onto HTTP responses.
Keeping them free of any web framework lets the core be reused from CLIs,
workers, or tests.
"""
from __future__ import annotations


class AuthError(Exception):
    """Base class for all ds-auth failures."""


class TokenMissing(AuthError):
    """No bearer token was presented."""


class TokenInvalid(AuthError):
    """The token was present but failed verification (signature, aud, exp, …)."""


class PermissionDenied(AuthError):
    """The caller is authenticated but lacks the required permission/perimeter."""


class AuthConfigError(AuthError):
    """The service is misconfigured (e.g. no issuer set outside dev).

    This is a server fault, not a client one — the FastAPI layer maps it to 500.
    """
