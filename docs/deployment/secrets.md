# Secrets

The charts never invent a secret value. Every Secret template uses Helm's
`required`, so a missing value **fails the render and names the key** instead of
deploying a default nobody chose. A successful `helmfile template` is therefore
proof that every mandatory secret is wired.

`.env.example` in the repository root is the authoritative catalogue of every
variable, what it does, and its blast radius if leaked.
`helm/secrets.example.yaml` mirrors it 1:1 — a variable documented there and
missing here is a gap.

## Three delivery modes

Switchable without touching a template, because all consumption already goes
through `envFrom` / `secretKeyRef`:

| Mode | How | When |
|------|-----|------|
| **SOPS** (default) | values in `secrets.sops.yaml` → one rendered `Secret` per service | single source, GitOps-friendly, no extra operator |
| **External Secrets** | `global.externalSecrets.enabled: true` → `ExternalSecret` CRs against `global.externalSecrets.secretStoreRef` | you already run Vault / AWS SM / GCP SM |
| **Pre-created** | `existingSecret: <name>` per chart → the chart references it and creates nothing | secrets provisioned by another process entirely |

With External Secrets, the chart declares **which** keys it needs and where they
live, never their values. Remote keys are looked up under
`global.externalSecrets.remotePrefix` (default `dataspace`), refreshed on
`refreshInterval` (default `1h`).

## The SOPS path

```bash
cd helm
cp secrets.example.yaml secrets.sops.yaml
$EDITOR secrets.sops.yaml          # fill every CHANGE_ME
$EDITOR .sops.yaml                 # set your age or KMS recipient
sops --encrypt --in-place secrets.sops.yaml
```

`secrets.sops.yaml` is committed **encrypted** and decrypted by helmfile at
render time. `.sops.yaml` sets `encrypted_regex: ^(secrets)$`, so keys stay
readable and only values are encrypted — diffs remain reviewable.

```bash
age-keygen -o ~/.config/sops/age/keys.txt   # generate a recipient
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

!!! danger "The plaintext form must never be committed"
    `helm/.gitignore` blocks the usual staging names (`secrets.dec.yaml`,
    `secrets.yaml`), but the responsibility is yours. `secrets.sops.yaml` itself
    is *intentionally not ignored* — it is meant to be committed, encrypted.

### Generating values

```bash
openssl rand -hex 32                                        # API keys, AUTH_SECRET
python -c 'import secrets;print(secrets.token_urlsafe(32))' # Fernet passphrase
task secrets:keygen                                         # EC P-256 key material → secrets/
```

`task secrets:keygen` writes the EDR signing keys for both EDC vaults and the
trust-anchor keypair. It is idempotent: existing key files are preserved, never
overwritten.

## Key reference

### Critical — each is a full compromise if leaked

| Key | Consumer | Blast radius |
|-----|----------|--------------|
| `identityRegistryEncryptionKey` | identity-registry | Fernet passphrase encrypting **every participant DID private key at rest**. Leak → impersonate any participant. |
| `authSecret` | portal | Auth.js session encryption. Leak → forge portal sessions carrying arbitrary user identity and VC claims. |
| `participants.<name>.edcApiKey` | ds-edc + ds-connector | EDC Management API key, and the `X-Api-Key` accepted by the connector's `/internal/*`. Leak → create and delete assets, policies and transfers; read consented-subject lists; forge audit events. |
| `participants.<name>.edcVault.edrSigningPrivateJwk` | ds-edc | Signs Endpoint Data References. Distinct from any DID key. |
| `participants.<name>.stsSecret` | ds-edc | The participant's STS client secret, as registered in the identity registry. |

!!! danger "`identityRegistryEncryptionKey` must be backed up outside the cluster"
    **Losing it makes every stored private key unrecoverable.** A cluster Secret
    is not a backup. Rotating it requires re-encrypting the key table — there is
    no automatic migration path today.

    The KDF uses a per-key random salt stored alongside each ciphertext, so two
    deployments sharing a passphrase produce different blobs. The salt prevents
    precomputation; it does not compensate for a weak passphrase.

### Keycloak service clients

One per confidential client in `services/keycloak/clients.yaml`. In dev each
defaults to its own `client_id` — guessable, and three of them hold admin-level
authority.

| Key | Client | Notable scopes |
|-----|--------|----------------|
| `svcDsIdentityRegistrySecret` | `svc-ds-identity-registry` | `identity-registry.admin` |
| `svcDsOnboardingSecret` | `svc-ds-onboarding` | `identity-registry.admin` |
| `svcDsPortalSecret` | `svc-ds-portal` | `connector.admin`, `identity-registry.read` |
| `svcDsConnectorSecret` | `svc-ds-connector` | `identity-registry.read`, `provenance.write` |
| `svcDsFederatedCatalogSecret` | `svc-ds-federated-catalog` | `identity-registry.read` |
| `svcDsDatasetApiSecret` | `svc-ds-dataset-api` | `connector.internal` |
| `svcEdcSecret` | `svc-edc` | `identity-registry.read`, `connector.webhook` |
| `authKeycloakSecret` | `ds-portal` | the **public-facing** OIDC login client, not a service client |
| `keycloakClientSecret` | `ds-identity-registry` | the registry's own Keycloak client |

`keycloakAdminUsername` / `keycloakAdminPassword` are needed **only** when
`global.keycloak.sync.enabled` is true. Prefer provisioning the realm
out-of-band and leaving both empty — it keeps admin credentials out of the
application namespace.

### Trust anchor

| Key | Consumer | Notes |
|-----|----------|-------|
| `trustAnchorPublicJwk` | ds-connector | Public JWK from `task secrets:keygen` (`secrets/trust-anchor.public.jwk.json`), mounted as a file at `trustAnchor.keyMountPath`. It verifies user VCs on the consent and consumer APIs. |

Leaving it unset in production means the data-subject sovereignty control is off,
which is why the template requires it.

### Database roles

One password per least-privilege role, keyed `<service>_<participant>` for
participant-scoped services:

```yaml
secrets:
  postgres:
    identity_registry: …
    connector_provider: …
    provenance_provider: …
    edc_provider: …
    connector_consumer: …
    provenance_consumer: …
    edc_consumer: …
```

The role names match the databases provisioned in
[`helm/docs/cnpg-cluster.example.yaml`](https://github.com/spindoxlabs/ds/blob/main/helm/docs/cnpg-cluster.example.yaml).
Adding a participant means adding three entries here.

## The committed dev material is public

Two categories of committed secret-looking files are **zero-config dev
fixtures**, published on purpose so the stack runs with no setup:

- `services/connector/config/{provider,consumer}-vault.properties` — EC P-256
  private keys and `insecure-dev-secret`
- `services/keycloak/realm-dataspaces-dev.json` — four users whose password
  equals their username

A production deployment must not mount or import either. The `ds-edc` chart
renders its vault from `secrets.sops.yaml`, never from the committed files;
`FilesystemVaultSeederExtension` loads whatever it is given without placeholder
detection, so this is a chart responsibility, not a runtime one.

## Rotation

| Secret | Rotatable | How |
|--------|-----------|-----|
| Keycloak client secrets | yes | rotate in Keycloak, update `secrets.sops.yaml`, `helmfile apply` — the Deployment's `checksum/secret` annotation rolls the pods |
| `edcApiKey` | yes, with coordination | shared by `ds-edc`, `ds-connector` and the external dataset API; update all three together |
| `authSecret` | yes | invalidates every active portal session |
| `edrSigningPrivateJwk` | yes | in-flight EDRs signed with the old key stop verifying |
| DB passwords | yes | rotate the CNPG role first, then the values |
| `identityRegistryEncryptionKey` | **no automatic path** | requires re-encrypting the DID private-key table |

## Verifying

```bash
cd helm
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
helmfile -e production template >/dev/null && echo "every required secret is wired"
```

A failed render names the missing key. This is the check to wire into CI —
along with `task secrets:check`, which refuses any file still carrying a
`CHANGE_ME`, a known dev default, a service secret equal to its client id,
`DS_DEMO_IDENTITY_ENABLED=true`, or a missing `DS_ENV=production`.
