"""Test package for ds-federated-catalog.

``SIGNING_KEY`` is regenerated per run and its value is deliberately
irrelevant. Every test here proves **authorization** — which scope reaches which
route — never authentication: the app under test runs with no issuer configured,
so `ds_auth` decodes without verifying a signature and any key would do. A
literal `"secret"` was doing the same job while reading as a hardcoded
credential and emitting an `InsecureKeyLengthWarning` per token minted.
"""
import secrets

SIGNING_KEY = secrets.token_hex(32)
