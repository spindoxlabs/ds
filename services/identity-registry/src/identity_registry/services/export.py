from __future__ import annotations

import json
from pathlib import Path


def export_private_key(
    base_path: str,
    participant_name: str,
    private_jwk: dict,
) -> Path:
    keys_dir = Path(base_path) / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_path = keys_dir / f"{participant_name}-key.json"
    key_path.write_text(json.dumps(private_jwk, indent=2))
    return key_path


def export_credential(
    base_path: str,
    participant_name: str,
    credential_filename: str,
    credential_json: dict,
) -> Path:
    cred_dir = Path(base_path) / "credentials" / participant_name
    cred_dir.mkdir(parents=True, exist_ok=True)
    cred_path = cred_dir / credential_filename
    cred_path.write_text(json.dumps(credential_json, indent=2))
    return cred_path
