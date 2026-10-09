# Secrets

The charts never invent a secret value. Every Secret template uses Helm's `required`, so a
missing value **fails the render and names the key** instead of deploying a default nobody chose.

`.env.example` in the repository root is the authoritative catalogue of every variable, what it
does and its blast radius if leaked. `helm/secrets.example.yaml` mirrors the subset the charts
need.

## Two delivery modes

Switchable without touching a template, because all consumption already goes through `envFrom`
and `secretKeyRef`:

| Mode | How | When |
|---|---|---|
| **SOPS** (default) | values in `secrets.sops.yaml` → one rendered `Secret` per service | single source, GitOps-friendly, no extra operator |
| **Pre-created** | `existingSecret: <name>` per chart → the chart references it and creates nothing | secrets provisioned by another process entirely |

The charts emit no `ExternalSecret`. A deployment that keeps its values in an external store
(Vault, a cloud secret manager) has that store produce the Secret, and sets `existingSecret`
to its name; the keys it must carry are the ones the chart's `templates/secret.yaml` renders.

## The SOPS path — in your own repository

**ds is a public repository: a deployment's secrets file lives in the deployment's
own repository, encrypted with that repository's sops setup**, and its helmfile
passes the decrypted values down to ds's (see `helm/README.md`, *Install — from your
own repository*). `helm/secrets.sops.yaml` is gitignored in ds so that a real
ciphertext cannot be committed here by accident.

```bash
# in the deployment repository
cp ds/helm/secrets.example.yaml overlay/staging/secrets.sops.yaml
$EDITOR overlay/staging/secrets.sops.yaml   # fill every CHANGE_ME
$EDITOR .sops.yaml                          # your age or KMS recipient
sops --encrypt --in-place overlay/staging/secrets.sops.yaml
```

With `encrypted_regex: ^(secrets)$` keys stay readable and only values are
encrypted, so diffs remain reviewable.

```bash
age-keygen -o ~/.config/sops/age/keys.txt
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

!!! danger "The plaintext form must never be committed"
    Decrypt only to a gitignored path (`secrets.dec.yaml` is ignored in ds's `helm/`), run
    the preflight on it, delete it.

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
| `participants.<name>.organisationClientSecret` | ds-connector | the organisation client `svc-ds-connector-<alias>`, which the connector presents to its EDC's management API (v5, OAuth2) and to every ds service. EDC does not check a token's audience, so a leak → create and delete this participant's assets, policies and transfers **from any network that reaches the management port**, which is why that port stays ClusterIP-only. Must equal the secret the realm holds: `ir-cli keycloak org-sync` creates the client with `SVC_DS_CONNECTOR_<ALIAS>_SECRET`, read from the Secret named by the identity-registry chart's `keycloak.sync.organisationClientSecrets` |
| `participants.<name>.edcCallbackKey` | ds-edc (vault `ds-connector-callback-key`) + ds-connector | the header value EDC sends when it delivers an EDR to `POST /webhooks/edc-callback`. Leak → a forged EDR stored against a transfer of this connector |
| `participants.<name>.connectorClientSecret` | ds-edc | this EDC's own Keycloak client for the connector's internal API and webhooks. **The extension refuses to start without it** |
| `participants.<name>.edcVault.edrSigningPrivateJwk` | ds-edc | signs Endpoint Data References. Distinct from any DID key |
| `participants.<name>.stsSecret` | ds-edc | the participant's STS client secret, as registered in the identity registry |
| `participants.<name>.publisherSecret` *(optional)* | ds-connector's sync hook Job | `svc-ds-publisher`'s Keycloak secret, and only where `sync.clientId` names it. Blast radius **deliberately small**: that client holds `connector.provider.read` + `.write` and no `management-api:*`, so a leak publishes and unpublishes this participant's catalogue and reaches no EDC. That is the whole reason to prefer it over the organisation client for a credential that drives a deployment |

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
| `identityRegistryEncryptionKey`, `svcDsIdentityRegistrySecret` | the anchor's `ds-identity-registry` (the service client secret is read only there: a participant registry holds none) |
| `keycloakAdminUsername`, `keycloakAdminPassword`, `organisationClients.*` | the anchor, only with `global.keycloak.sync.enabled` (posture A) |
| `svcDsFederatedCatalogSecret` | `ds-federated-catalog` |
| `svcDsPortalSecret` | `ds-portal` |
| `oauth2ProxyCookieSecret`, `oauth2ProxyClientSecret` | `ds-oauth2-proxy` |
| `svcDsOnboardingSecret`, `svcDsDatasetApiSecret`, `svcDsConnectorSecret`, `svcEdcSecret` | no chart — the realm, and the process outside ds that authenticates as the client |
| `postgres.<db>` | the owning service |
| `participants.<name>.identityRegistryEncryptionKey`, `.stsSecret` | the participant's own `ds-identity-registry-<name>` (and `stsSecret` also its EDC vault) |
| `participants.<name>.edcCallbackKey` | its EDC vault **and** its connector — one value, two holders |
| `participants.<name>.edcControlApiKey`, `.connectorClientSecret`, `.edcVault.edrSigningPrivateJwk` | its `ds-edc` |
| `participants.<name>.edcVault.edrSigningPublicJwk` | its `ds-connector`, served at `/internal/edr-jwks` — the public half only |
| `participants.<name>.organisationClientSecret`, `.connectorAtRestKeys`, `.connectorKeyIndexSecret`, `.publisherSecret` | its `ds-connector` (`publisherSecret` only with `connector.sync.clientId`) |
| `participants.<name>.provenanceSubjectPseudonymKey` | its `ds-provenance` — set once, never rotated |

**Values that must agree**, and how the render holds them: `edcCallbackKey` and `stsSecret`
are fanned out from one key each. `connectorClientSecret` is the **same for every
participant** and equal to `svcEdcSecret` — every EDC logs in as the one realm client
`svc-edc` — and the render refuses two different values. Posture A's
`organisationClients.<alias>.connectorSecret` must equal that participant's
`organisationClientSecret`; the render refuses a difference. The EDR key's two halves are
supplied by the operator, kept side by side, and checked to agree.

`keycloakAdminUsername` / `keycloakAdminPassword` are needed **only** when Keycloak sync or
runtime mutation is enabled. Prefer provisioning the realm out-of-band and leaving both empty —
it keeps admin credentials out of the application namespace entirely.

## The committed dev material is public

Two categories of committed secret-looking files are **zero-config dev fixtures**, published on
purpose so the stack runs with no setup:

- `services/connector/config/{provider,consumer}-vault.properties` — EC P-256 private keys and a
  literal dev secret;
- `services/keycloak/realm-dataspaces-dev.json` — users whose password equals their username, a
  literal client secret, direct access grants enabled.

**A production deployment must not mount or import either.** The `ds-edc` chart renders its
vault from the deployment's secrets, never from the committed files. Three checks now refuse a
fixture key that was pasted in: the render policy, `task secrets:check`, and the EDC itself,
whose vault seeder refuses a fixture key, `insecure-dev-secret` or a placeholder unless
`DS_ENV=dev`.

## Rotation

| Secret | Rotatable | How |
|---|---|---|
| Keycloak client secrets | yes | **realm first** — the realm sync never changes an existing client's secret — then the secrets file, apply; the `checksum/secret` annotation rolls the pods |
| `edcCallbackKey` | yes | one key feeds the EDC vault and the connector, so one apply rolls both |
| `oauth2ProxyCookieSecret` | yes | invalidates every active browser session |
| `edrSigningPrivateJwk` + `edrSigningPublicJwk` | yes, together in one edit | in-flight EDRs signed with the old key stop verifying; the connector rolls on its own Secret and serves the new public key |
| Database passwords | yes | rotate the CNPG role first, then the values |
| `identityRegistryEncryptionKey` | **no automatic path** | requires re-encrypting the DID private-key table |

The identity registry additionally **rotates a participant's STS secret on every
provisioning-bundle call**, storing only a hash. It cannot re-show a secret, so rotation is the
only honest meaning of "send it again" — and it is what makes a leaked bundle invalidatable.

## Verifying

```bash
# in the deployment repository
sops -d overlay/staging/secrets.sops.yaml > secrets.dec.yaml
task -d ds secrets:check FILE=$PWD/secrets.dec.yaml; rm secrets.dec.yaml
helmfile -e staging template >/dev/null && echo "every required secret is wired"
```

`task secrets:check` on a decrypted helm secrets file reports placeholders and committed dev
defaults at any depth (the dev cookie secret and the EDR fixture keys included), a client
secret equal to its client id (the mapping is derived from `services/keycloak/clients*.yaml`),
a custody key shared between two holders, and a participant whose public EDR JWK is not the
public half of its private one. It never prints a value. On an `.env` file it keeps its
original checks (`CHANGE_ME`, dev defaults, a service secret equal to its client id, the
demo-identity flag, `DS_ENV=dev`).

The render itself enforces the same policy on the merged values (`helm/README.md`,
*Secrets*), so a placeholder or a shared custody key fails `helmfile template` in every
environment but `example`.
