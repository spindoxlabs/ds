#!/usr/bin/env python3
"""Compatibility wrapper for the local-dev VC issuer."""
from __future__ import annotations

from credential_issuer import main


if __name__ == "__main__":
    raise SystemExit(main(["issue"]))
