# ds

A DSSC/CEEDS aligned dataspace platform for energy communities.

## Architecture

- [Architecture overview](architecture.md)
- [Identity and DCP](identity-and-dcp.md)
- [Data exchange flow](data-exchange-flow.md)
- [Governance and ODRL](governance-and-odrl.md)
- [Consent and sovereignty](consent-and-sovereignty.md)
- [Owner identity and ownership](owner-identity-and-ownership.md)
- [Provenance and lineage](provenance-and-lineage.md)

## Deployment

- [Deployment overview](deployment/index.md) — Helm charts, topology, security contract
- [Prerequisites](deployment/prerequisites.md) — CloudNativePG, Keycloak, cert-manager, ingress
- [Keycloak requirements](deployment/keycloak.md) — the realm contract
- [Configuration reference](deployment/configuration.md) — `values.yaml`, key by key
- [Secrets](deployment/secrets.md) — delivery modes, key reference, rotation
- [Exposure and network policy](deployment/exposure.md) — public surface, NetworkPolicies
- [Operations](deployment/operations.md) — install, upgrade, day-2, troubleshooting

## Blueprints

- [DSSC Blueprint reference](dssc-blueprint-docs/README.md)
- [CEEDS Blueprint reference](ceeds-blueprint-docs/README.md)
- [CEEDS benchmark](ceeds-benchmark.md)
