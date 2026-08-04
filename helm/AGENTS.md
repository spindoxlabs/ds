# helm

Eight charts plus a helmfile composing one authority and any number of participants:
`ds-common` (library), `ds-namespaces`, `ds-identity-registry`, and the participant tier
`ds-edc` / `ds-connector` / `ds-provenance` / `ds-federated-catalog` / `ds-oauth2-proxy` /
`ds-portal`.

**The chart's first responsibility is not to deploy the platform — it is to make an insecure
deployment impossible to produce by omission.** Dev is zero-config by design; this folder is
the boundary where that stops being safe.

## References

| | |
|---|---|
| Requirements | [DSSC · Service Definitions](../docs/blueprints/dssc/service-definitions.md) — the eleven deployable-component definitions this chart set realises · [DSSC · Trust Framework](../docs/blueprints/dssc/data-sovereignty-and-trust/trust-framework.md) |
| Rules | [Rulebook · Participation and trust](../docs/rulebook/participation.md) · [Rulebook · Provenance and logging](../docs/rulebook/provenance-and-logging.md) (observability obligations) |
| Operator docs | [docs/deployment/](../docs/deployment/index.md) — prerequisites, the Keycloak realm contract, the `values.yaml` reference, secrets, exposure, day-2 operations. **Keep it in sync when you change a chart's values contract or its public surface**; it is the only operator-facing description of either. This file is agent- and security-facing and is not a substitute |

## `DS_ENV=production` is the mechanism

Every Python service builds a `ProductionGuard` at startup and registers its dangerous dev
defaults. Under `DS_ENV=production` it collects **all** violations, logs them together and
refuses to start — so a chart author gets the complete list from one failed deploy.

**The chart MUST set `DS_ENV=production` on every service container.** It is not a per-service
opt-in and must not be exposed as a values toggle. The guard also rejects universally weak
values (`admin`, `postgres`, `password`, `changeme`, empty) for any registered setting.

## Surfaces the guard cannot reach

Three components are not Python, so their protection is expressed in the chart itself.

**EDC (Java)**

- **`DS_DEMO_IDENTITY_ENABLED` must never be set.** It accepts self-issued DCP tokens without
  verifying signatures — a complete DSP authentication bypass. Do not add it to `values.yaml`
  at all: an absent key cannot be accidentally set to `true`.
- `EDC_API_KEY` from a Secret, no chart default; prefer the `_FILE` form. It is EDC's
  Management API key **and nothing else**.
- `web.http.management.auth.type=tokenbased` must be set, not just the key.
- `secrets.connectorClientSecret` — the EDC's own Keycloak client. The extension refuses to
  start without it, deliberately.
- `edc.iam.did.web.use.https` must be `true`. DID documents carry the keys trust decisions
  are made on; over HTTP an on-path attacker controls participant identity verification.
- Management (`:19193`) and control (`:19192`) are ClusterIP only, never an Ingress.

**Portal** — it is not an OIDC client and does not verify the token it builds a session from.
That is only safe because something in front authenticates and makes a client-supplied
`X-Auth-Request-*` unable to reach the pod. In-cluster that is the `ds-oauth2-proxy` release
plus three Ingress annotations, of which `auth-response-headers` **is the strip**. See
`services/oauth2-proxy/AGENTS.md`. `auth.proxy.enabled: false` does not fall back to a portal
login — there is none.

**Keycloak** — externally managed. **There is no Keycloak chart and no chart imports any
realm**, so nothing here selects a realm file at all; an earlier version of this line claimed
the chart selects `realm-production.example.json`, and there is no chart to do it. The dev
realm (`realm-dataspaces-dev.json`: nine users whose password is their username,
`registrationAllowed: true`, a literal `oauth2_proxy` secret) is mounted only by
`docker-compose.yml`. `task secrets:check` fails if a production env file names it. The realm
is provisioned from
`clients.effective.yaml`, **not** `clients.yaml`: the syncer recomputes each client's grants
from the single file it is handed, so pointing it at the core file *strips* whatever an
overlay granted, silently. Layer B lives in `global.keycloak.aliases` — one block feeding
every service, because a partial map means authority depends on which service answered.

## Exposure

**One public host per trust boundary, path-allowlisted, default 404.** A chart gets an
Ingress only if it appears here:

| Host | Owner | Serves |
|---|---|---|
| `portal.<baseDomain>` | `ds-portal` | `/` — the only human-facing host, behind `auth-url` |
| `portal.<baseDomain>` | `ds-oauth2-proxy` | `/oauth2/*` — same host on purpose: one cookie domain, one redirect URI. **Must not** carry the portal's auth annotations (a user arrives there precisely because they have no session) and no `cluster-issuer` |
| `<participant>.<baseDomain>` | `ds-edc` | `/.well-known/did.json`, `/protocol/*`, `/public/*`, `/credentials`, `/sts`, and `/users/<id>/did.json` — the DID documents of the people this participant onboarded (`DID-11` step 2). Nothing else |
| `trust-anchor.<baseDomain>` | `ds-identity-registry` | `/.well-known/did.json`, `/status/*` — StatusList must be publicly fetchable or revocation cannot be checked — plus `/trust` (the accredited-issuer list) and `/issuer` (CIP's Credential Request API, which is how anyone enrols) |

There is no `users.<baseDomain>` host. It existed until `DID-11` step 2 and put every person in
the dataspace under the **trust anchor's** domain; a person now lives in the namespace of the
organisation that onboarded them, so their DID resolves on that organisation's host — one host,
one Ingress owner, the same rule as `/credentials`.

The participant host **is** the participant's `did:web` identity, which is why DID resolution
and the DSP endpoints share it.

**Never exposed:** EDC management and control, the connector (including `/internal/*` and
`/webhooks/*`), provenance, federated catalog, the registry's `/admin`, `/sts`,
`/credentials`, `/memberships`, `/owners`, and every `/metrics`.

`ds-edc` denies management and control **twice** — at routing and at the network layer
(`fromIngressController` lists only `protocol` and `public`). **Keep both denials.**

## Conventions that will bite you

- **`helmfile.yaml.gotmpl`, not `.yaml`.** Helmfile v1 templates the release list only with
  that extension; plain `.yaml` fails with a cryptic map-key error.
- **All boilerplate lives in `ds-common/templates/*.tpl`** — naming, labels, images, security
  contexts, `DS_ENV` injection, secret-mode switching, DB URLs, ingress TLS, probes,
  NetworkPolicy builders. A chart hand-rolling any of these is doing it wrong; extend a helper.
- **`ds-common` is a `file://` dependency.** After editing it run `helm dependency update`
  or you test a stale vendored copy.
- **Go-template comments cannot contain `*/`** — a glob like `services/*/Dockerfile` inside
  `{{/* … */}}` closes the comment early.
- **One cert-manager Certificate per host.** Several Ingresses share a host because
  `rewrite-target` is per-object; exactly one may carry the `cluster-issuer` annotation.
- **Numeric UID is mandatory.** `runAsNonRoot` cannot be verified against a named `USER`;
  kubelet refuses the pod. All service Dockerfiles pin uid/gid **10001**.
- **Derive a sibling Service from `.Values.participant.name`, never `.Release.Name`.**
  Releases are `ds-<service>-<participant>`; the helpers `conn.edcService` and friends do this.
- **Egress allows are opt-in.** `defaultDeny` permits only DNS and Postgres. Broad-CIDR rules
  always exclude `169.254.169.254/32` — a pod reaching the metadata endpoint can often mint
  cloud IAM credentials.

## Deliberately not charted

A missing component is a decision. Adding one reopens it, it does not fill a gap.

| Component | Why |
|---|---|
| `dataset-api-mock` | Dev fixture. The real dataset API is participant-operated and **external**; the charts carry its URL and credentials, nothing more |
| `dataset-api-fiware-adapter` | A plugin loaded through entry points, not a deployable unit |
| `edc-extensions` | A Java library, already shaded into the fat JAR |
| `caddy` | Dev-only. Its did:web rewrite and API fan-in are native Ingress rules here |
| `keycloak` | Externally managed — the charts consume an issuer URL and secrets |
| PostgreSQL | Externally managed via CloudNativePG; a reference `Cluster` ships under `helm/docs/` |

`ds-oauth2-proxy` is charted despite being upstream software, and is **not optional wherever
`ds-portal` runs**.

## Validate before committing

```bash
helm dependency update ./charts/ds-identity-registry
helm lint ./charts/ds-identity-registry --set secrets.dbPassword=z …
helmfile -e example template             # the whole set, no key needed — run this
helmfile -e production template          # the real thing; needs SOPS_AGE_KEY_FILE
```

Secret templates use `required`, so a render that succeeds proves every mandatory secret is
wired, and a render that fails names the missing key.

**Render with `-e example` before committing.** `production` reads `secrets.sops.yaml`, which is
gitignored — so in a clean checkout that command cannot run at all, and for a long time nothing
rendered these charts. The `example` environment substitutes the committed
`secrets.example.yaml` as plain values; it deploys nothing (every value is `CHANGE_ME`) and
exists so the composition stays checkable. Its first run found two supply paths wired for one
participant out of three.

**A new participant-scoped value must be added to `secrets.example.yaml` in the same change.**
The helmfile reads `$psec.<key>` for *every* participant, and per-participant `postgres` roles
are keyed `<service>_<name>` with `-` replaced by `_`. `grid-operator` ships `enabled: false`,
so a gap there renders nothing and stays invisible — flip it on and render if you touch that
tier.

## Adding a service chart

1. `charts/ds-<svc>/` depending on `ds-common` (`file://../ds-common`)
2. `templates/_env.tpl` mapping the service's `pydantic-settings` prefix (grep `env_prefix=`)
3. deployment, service, serviceaccount, secret, externalsecret, networkpolicy, pdb — and an
   ingress **only if** it appears in Exposure above
4. a `global:` fallback block so it renders standalone under `helm lint`
5. a release entry in `helmfile.yaml.gotmpl`, participant-scoped, with `needs:` the authority
6. `.env.example` is the authoritative variable catalogue — **the chart's values and Secret
   templates should map 1:1 onto it.** A variable documented there and absent here is a gap
