# ds-vc-wallet — Agent Guide

## Service identity

- **Role**: DCP Credential Service — holds Verifiable Credentials and returns Verifiable Presentations
- **Language**: Python 3.12, FastAPI
- **Ports**: 38082 (provider), 38083 (consumer)
- **URLs**: `https://vc-wallet-provider.dataspaces.localhost`, `https://vc-wallet-consumer.dataspaces.localhost`
- **Database**: none (credentials stored as JSON files)

## Source layout

```
src/vc_wallet/
├── main.py        FastAPI app — presentations/query, credentials CRUD, /health
└── config.py      Pydantic settings (VcWalletSettings)
```

Credential storage:

```
data/credentials/
├── provider/membership-vc.json     MembershipCredential VC (issued by trust anchor)
└── consumer/membership-vc.json     MembershipCredential VC (issued by trust anchor)
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Change VP generation logic | `main.py` (presentations_query handler) |
| Add new credential types | `main.py` + issue new VCs via `scripts/issue-vcs.py` |
| Change config/env vars | `config.py` |

## Coding conventions

- Each participant runs their own wallet instance with its own DID and credential directory
- `POST /api/v1/presentations/query` returns a `VerifiablePresentation` wrapping all held VCs
- Credentials are W3C `VerifiableCredential` with `JsonWebSignature2020` proof
- Currently returns all VCs regardless of the query's presentation definition — no full DIF Presentation Exchange matching
- Credential revocation (StatusList2021) is referenced in VCs but not enforced at runtime

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `VC_WALLET_PARTICIPANT_DID` | — | `did:web:` URI for this participant |
| `VC_WALLET_CREDENTIALS_PATH` | — | Directory containing VC JSON files |

## Integration points

- **Called by**: EDC connectors during DSP negotiation (DCP Credential Service API)
- **No downstream dependencies**
- Credentials issued by `scripts/issue-vcs.py` using trust anchor's private key
