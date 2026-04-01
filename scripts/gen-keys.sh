#!/usr/bin/env bash
# gen-keys.sh — regenerate all participant and trust-anchor key pairs.
#
# Writes EC P-256 JWK files (private) to src/ds/connector/config/ and
# updates public keys in caddy/did/*/did.json.
#
# Run once at setup, or whenever keys need rotation.
#
# Requires: python3 with cryptography package installed.
# Install:  pip install cryptography
#           (or: uv tool install cryptography)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - <<EOF
import json, base64, sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ec import generate_private_key, SECP256R1

REPO_ROOT = Path("$REPO_ROOT")

def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()

participants = [
    ("provider", "did:web:provider.dataspaces.localhost"),
    ("consumer", "did:web:consumer.dataspaces.localhost"),
    ("trust-anchor", "did:web:trust-anchor.dataspaces.localhost"),
]

for name, did in participants:
    key = generate_private_key(SECP256R1())
    pub = key.public_key()
    pub_nums = pub.public_numbers()
    priv_nums = key.private_numbers()
    x = b64url(pub_nums.x.to_bytes(32, 'big'))
    y = b64url(pub_nums.y.to_bytes(32, 'big'))
    d = b64url(priv_nums.private_value.to_bytes(32, 'big'))
    kid = f"{did}#key-1"

    # Write private key
    priv_path = REPO_ROOT / "src/ds/connector/config" / f"{name}-key.json"
    priv_path.write_text(json.dumps(
        {"kty":"EC","crv":"P-256","x":x,"y":y,"d":d,"kid":kid,"use":"sig"}, indent=2
    ))
    print(f"Written: {priv_path}")

    # Update DID document public key
    did_dir = REPO_ROOT / "caddy/did" / f"{did.split(':')[-1]}.dataspaces.localhost" if "trust-anchor" not in name else REPO_ROOT / "caddy/did/trust-anchor.dataspaces.localhost"
    did_path = did_dir / "did.json"
    if did_path.exists():
        doc = json.loads(did_path.read_text())
        for vm in doc.get("verificationMethod", []):
            if vm.get("id") == kid:
                vm["publicKeyJwk"] = {"kty":"EC","crv":"P-256","x":x,"y":y,"kid":kid,"use":"sig"}
        did_path.write_text(json.dumps(doc, indent=2))
        print(f"Updated: {did_path}")

print("")
print("Keys regenerated. Re-run scripts/issue-vcs.py to re-issue membership VCs.")
EOF
