# Secrets

The charts never invent a secret value. Every Secret template uses Helm's `required`, so a
missing value **fails the render and names the key** instead of deploying a default nobody chose.

`.env.example` in the repository root is the authoritative catalogue of every variable, what it
does and its blast radius if leaked. `helm/secrets.example.yaml` mirrors the subset the charts
need.

## Three delivery modes

Switchable without touching a template, because all consumption already goes through `envFrom`
and `secretKeyRef`:

| Mode | How | When |
|---|---|---|
| **SOPS** (default) | values in `secrets.sops.yaml` → one rendered `Secret` per service | single source, GitOps-friendly, no extra operator |
| **External Secrets** | `global.externalSecrets.enabled: true` → `ExternalSecret` CRs against your store | you already run Vault / AWS SM / GCP SM |
| **Pre-created** | `existingSecret: <name>` per chart → the chart references it and creates nothing | secrets provisioned by another process entirely |

With External Secrets the chart declares **which** keys it needs and where they live, never
their values.

## The SOPS path

```bash
cd helm
cp secrets.example.yaml secrets.sops.yaml
$EDITOR secrets.sops.yaml          # fill every CHANGE_ME
$EDITOR .sops.yaml                 # set your age or KMS recipient
sops --encrypt --in-place secrets.sops.yaml
```

`secrets.sops.yaml` is committed **encrypted** and decrypted by helmfile at render time.
`.sops.yaml` sets `encrypted_regex: ^(secrets)$`, so keys stay readable and only values are
encrypted — diffs remain reviewable.

```bash
age-keygen -o ~/.config/sops/age/keys.txt
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

!!! danger "The plaintext form must never be committed"
    `helm/.gitignore` blocks the usual staging names, but the responsibility is yours.
    `secrets.sops.yaml` itself is *intentionally not ignored* — it is meant to be committed,
    encrypted.

### Generating values

```bash
openssl rand -hex 32                                        # API keys, client secrets
openssl rand -base64 32                                     # the oauth2-proxy cookie secret
python -c 'import secrets;print(secrets.token_urlsafe(32))' # the registry encryption passphrase
task secrets:keygen                                         # EC P-256 key material → secrets/
```

`task secrets:keygen` writes the EDR signing keys for both EDC vaults and the trust-anchor
keypair. It is idempotent — existing key files are preserved, never overwritten.

## The keys

### Critical — each is a full compromise if leaked

| Key | Consumer | Blast radius |
|---|---|---|
| `identityRegistryEncryptionKey` | identity-registry | encrypts **every participant DID private key at rest**, and derives subject ids. Leak → impersonate any participant |
| `oauth2ProxyCookieSecret` | oauth2-proxy | encrypts the browser session cookie. Leak → forge a session carrying any identity. Must be 16, 24 or 32 bytes |
| `oauth2ProxyClientSecret` | oauth2-proxy | the login client's Keycloak secret. Leak → sign in as any user of the realm |
| `participants.<name>.edcApiKey` | ds-edc + ds-connector | the EDC Management API key. Leak → create and delete assets, policies and transfers |
| `participants.<name>.connectorClientSecret` | ds-edc | this EDC's own Keycloak client for the connector's internal API and webhooks. **The extension refuses to start without it** |
| `participants.<name>.edcVault.edrSigningPrivateJwk` | ds-edc | signs Endpoint Data References. Distinct from any DID key |
| `participants.<name>.stsSecret` | ds-edc | the participant's STS client secret, as registered in the identity registry |

!!! danger "`identityRegistryEncryptionKey` must be backed up outside the cluster"
    **Losing it makes every stored private key unrecoverable.** A cluster Secret is not a
    backup. Rotating it requires re-encrypting the key table; there is no automatic migration
    path.

    The key derivation uses a per-key random salt stored beside each ciphertext, so two
    deployments sharing a passphrase produce different blobs. The salt prevents precomputation;
    it does not compensate for a weak passphrase.

### Where each key goes

| Key | Reaches |
|---|---|
| `identityRegistryEncryptionKey`, `keycloakClientSecret`, `keycloakAdminUsername`, `keycloakAdminPassword` | `ds-identity-registry` |
| `svcDsConnectorSecret`, `trustAnchorPublicJwk` | `ds-connector` |
| `svcDsFederatedCatalogSecret` | `ds-federated-catalog` |
| `svcDsPortalSecret` | `ds-portal` |
| `oauth2ProxyCookieSecret`, `oauth2ProxyClientSecret` | `ds-oauth2-proxy` |
| `postgres.<db>` | the owning service |
| `participants.<name>.*` | `ds-edc` (and the EDC API key also to `ds-connector`) |

`keycloakAdminUsername` / `keycloakAdminPassword` are needed **only** when Keycloak sync or
runtime mutation is enabled. Prefer provisioning the realm out-of-band and leaving both empty —
it keeps admin credentials out of the application namespace entirely.

### The trust anchor

| Key | Consumer | Notes |
|---|---|---|
| `trustAnchorPublicJwk` | ds-connector **and** ds-provenance | the public JWK from `task secrets:keygen`, mounted as a file |

It verifies user Verifiable Credentials on the consent and consumer APIs, and on a data
subject's own provenance view. Leaving it unset means the data-subject sovereignty control is
off, which is why both templates require it.

### Database roles

One password per least-privilege role, keyed `<service>_<participant>` for participant-scoped
services:

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

Role names match the databases provisioned in
[`helm/docs/cnpg-cluster.example.yaml`](https://github.com/spindoxlabs/ds/blob/main/helm/docs/cnpg-cluster.example.yaml).
Adding a participant means adding three entries.

## The committed dev material is public

Two categories of committed secret-looking files are **zero-config dev fixtures**, published on
purpose so the stack runs with no setup:

- `services/connector/config/{provider,consumer}-vault.properties` — EC P-256 private keys and a
  literal dev secret;
- `services/keycloak/realm-dataspaces-dev.json` — users whose password equals their username, a
  literal client secret, direct access grants enabled.

**A production deployment must not mount or import either.** The `ds-edc` chart renders its
vault from `secrets.sops.yaml`, never from the committed files: the vault seeder loads whatever
it is given with no placeholder detection, so this is a chart responsibility, not a runtime one.

## Rotation

| Secret | Rotatable | How |
|---|---|---|
| Keycloak client secrets | yes | rotate in Keycloak, update `secrets.sops.yaml`, apply — the `checksum/secret` annotation rolls the pods |
| `edcApiKey` | yes, with coordination | shared by `ds-edc` and `ds-connector`; update both together |
| `oauth2ProxyCookieSecret` | yes | invalidates every active browser session |
| `edrSigningPrivateJwk` | yes | in-flight EDRs signed with the old key stop verifying |
| Database passwords | yes | rotate the CNPG role first, then the values |
| `identityRegistryEncryptionKey` | **no automatic path** | requires re-encrypting the DID private-key table |

The identity registry additionally **rotates a participant's STS secret on every
provisioning-bundle call**, storing only a hash. It cannot re-show a secret, so rotation is the
only honest meaning of "send it again" — and it is what makes a leaked bundle invalidatable.

## Verifying

```bash
cd helm
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
helmfile -e production template >/dev/null && echo "every required secret is wired"
```

This is the check to wire into CI, together with `task secrets:check`, which refuses any file
still carrying a `CHANGE_ME`, a known dev default, a service secret equal to its own client id,
the demo-identity flag, or a missing `DS_ENV=production`.
