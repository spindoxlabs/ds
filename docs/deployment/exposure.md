# Exposure and network policy

The design rule: **one public host per trust boundary, path-allowlisted, everything else 404.**
Anything not listed on this page is ClusterIP plus NetworkPolicy, reachable only from named
in-cluster callers.

## The public surface — three host shapes

### `portal.<baseDomain>` — the only human-facing host

| Path | Backend |
|---|---|
| `/oauth2/*` | `ds-oauth2-proxy-<participant>:4180` |
| everything else | `ds-portal-<participant>:30004`, behind the ingress controller's `auth-url` |

The portal is server-side rendered, so the browser never calls the connector, provenance or the
catalogue directly. The dev Caddy `/api/*` fan-in exists only because the dev portal can run on
the host, and is **not reproduced** in the charts.

The chart sets `ORIGIN=https://portal.<baseDomain>`. It must match oauth2-proxy's `redirect_url`
and the redirect URI registered on the realm's login client, or the login flow fails.

!!! warning "`auth-response-headers` is part of the authentication boundary"
    The portal does not verify the forwarded token's signature — it reads the token the proxy
    gives it. The annotation that overwrites client-supplied `X-Auth-Request-*` headers with the
    ones from the auth response is what makes that safe. It is not a hardening extra.

    The Ingress puts `auth-url` on a single `path: /` rule, so it has none of the compose
    carve-outs. Reproducing them — `/join` in particular, whose visitor has no account by
    definition — needs additional Ingress objects with narrower path rules and no auth
    annotations.

### `<participant>.<baseDomain>` — the DSP and data-plane boundary

One host per participant. This host **is** the participant's `did:web` identity, which is why
DID resolution and the DSP endpoints share it.

| Path | Backend | Purpose |
|---|---|---|
| `/.well-known/did.json` | the authority's identity registry, rewritten to its `/dids/…` route | `did:web` resolution |
| `/protocol/*` | `ds-edc-<participant>` protocol port | DSP — federation |
| `/public/*` | `ds-edc-<participant>` data-plane port | EDR pulls by remote consumers |

Everything else on this host 404s.

An Ingress can only target a Service in its own namespace, so the DID path reaches the
authority-namespace registry through an `ExternalName` Service, with `upstream-vhost` set so the
registry sees its own hostname.

### `trust-anchor.<baseDomain>` and `users.<baseDomain>`

| Host | Path | Behaviour |
|---|---|---|
| `trust-anchor.<baseDomain>` | `/.well-known/did.json` | the trust anchor's DID document |
| `trust-anchor.<baseDomain>` | `/status/*` | passthrough — the revocation list **must** be publicly fetchable, or a verifier cannot determine whether a credential was revoked |
| `trust-anchor.<baseDomain>` | `/credentials/*` | only when `credentialService.expose` is true |
| `<participant>.<baseDomain>` | `/users/<id>/did.json` | the DID documents of the people that participant onboarded (`DID-11`). Served by its own registry, on the host their DID names |

`/users/<id>/did.json` is **not** optional and has no flag: a person's DID is an identifier that
consent records, provenance events and `credentialSubject.id` all point at, and one that does not
resolve is a dangling reference. It carries no verification method — a natural person holds no
key — so what it publishes is the fact that they exist and who is custodian for them.

The trust anchor has no `users.` host. It did until `DID-11` step 2, behind an `exposeUserDids`
flag that was off by default, which made the production answer to *"where does a person's DID
resolve"* "nowhere, unless you turned on a flag".

Enable `credentialService.expose` only
if remote verifiers query the presentation endpoint directly instead of the holder
self-presenting — the endpoint is not anonymous (callers authenticate with a self-issued token
signed by the requested DID's registered key), but it is attack surface with no default
consumer.

## Never exposed

| Surface | Why |
|---|---|
| EDC management API | creates and deletes assets, policies and transfers |
| EDC control API | the internal data-plane control plane |
| EDC api/health | |
| `ds-connector` | including `/internal/*` and `/webhooks/*` |
| `ds-provenance` | |
| `ds-federated-catalog` | |
| identity registry `/admin`, `/sts`, `/memberships`, `/owners`, `/users`, `/agreements` | mutate the trust anchor and read consent-relevant data |
| every `/metrics` | unauthenticated; NetworkPolicy restricts them to the Prometheus namespace |

The `ds-edc` Service publishes management and control **in-cluster**, but the NetworkPolicy that
admits the ingress controller lists only the protocol and public ports. So even a misconfigured
Ingress path cannot reach them — the exposure is denied twice, at routing and at the network
layer.

## `did:web` over HTTPS

The dev stack resolves `did:web` over plaintext `:80` through a Caddy rewrite. **The charts do
not carry that.** The participant host and the trust-anchor host serve
`/.well-known/did.json` over TLS on 443, and `edc.iam.did.web.use.https` is `true`.

DID documents carry the public keys every trust decision rests on. Fetching them over HTTP hands
participant identity verification to any on-path attacker. That is why `didWebUseHttps` exists
as a value at all — to make the invariant visible, not to make it negotiable.

## One certificate per host

Several Ingress objects can share a host: nginx's `rewrite-target` is a per-object annotation,
so each rewrite behaviour needs its own object. Only **one** of them may carry the
`cert-manager.io/cluster-issuer` annotation, or cert-manager issues competing Certificates that
fight over the same secret.

The charts pass "issue a certificate" to exactly one Ingress per host and derive the TLS secret
name from the **host** rather than from the object, so they share the certificate.

Setting `global.ingress.tls.secretName` overrides this entirely and suppresses the issuer
annotation — the pre-created-certificate path.

## The NetworkPolicy model

Kubernetes has no deny rule: a policy that selects a pod and lists no matching peer denies
everything else for that direction. So every service gets one default-deny policy plus
narrowly-scoped allows.

**Default deny** on ingress *and* egress is rendered for every service when
`global.networkPolicy.enabled` is true, and always permits:

- DNS to `kube-dns` — without it every other egress rule fails to resolve;
- PostgreSQL on the configured port, to `0.0.0.0/0` **except** the cloud metadata endpoint
  `169.254.169.254/32`.

Every broad-CIDR egress rule carries that metadata exclusion: a pod that can reach
`169.254.169.254` can often mint cloud IAM credentials.

### Allows, per service

| Service | Ingress from | Egress beyond the baseline |
|---|---|---|
| `ds-identity-registry` | the ingress controller namespace; any namespace labelled as a participant | 443 — Keycloak JWKS, and the admin API when a sync runs |
| `ds-edc` | the ingress controller → **only** protocol + public; its own `ds-connector` → management, api, control; peer EDCs in participant-labelled namespaces → protocol + public | the authority namespace (STS, presentation queries); its own connector; 443 |
| `ds-connector` | `ds-portal` and `ds-edc`, same namespace | the authority namespace; its own EDC management and provenance; 443 (Keycloak, the external dataset API) |
| `ds-provenance` | `ds-connector`, same namespace | 443 (Keycloak JWKS) |
| `ds-federated-catalog` | `ds-portal`, same namespace | its own connector; the authority namespace; 443 |
| `ds-portal` | the ingress controller namespace | the connector, provenance and catalogue in its namespace; the authority namespace; 443 |
| `ds-oauth2-proxy` | the ingress controller namespace | 443 (Keycloak) |

Every service that verifies JWTs needs egress to Keycloak's JWKS endpoint on 443 — without it
the baseline (DNS plus Postgres only) fails every authenticated request.

### Opening a path the chart does not know about

`.Values.networkPolicy.egress` is appended verbatim to the default-deny policy, so a release can
open an extra path without touching a template:

```yaml
networkPolicy:
  egress:
    - to:
        - ipBlock:
            cidr: 10.0.0.0/8
      ports:
        - {protocol: TCP, port: 8080}
```

Prefer a namespace or pod selector over a CIDR where the peer is in-cluster. Any broad-CIDR rule
should exclude `169.254.169.254/32`, as the chart-supplied ones do.

Two extra policies are conditional:

- `<service>-metrics` permits scraping from the configured Prometheus namespace, rendered only
  when `serviceMonitor` is enabled;
- peer-EDC ingress matches the **namespace label** `dataspace.spindoxlabs.io/participant`, set by
  the `ds-namespaces` release.

### Verifying

```bash
# the management API must be unreachable from another namespace
kubectl -n ds-consumer run probe --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sS --max-time 5 http://ds-edc-rec.ds-provider:19193/api/v3/assets
# expect: timeout / connection refused

# DSP protocol from a peer namespace must work
kubectl -n ds-consumer run probe --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sS --max-time 5 http://ds-edc-rec.ds-provider:19194/api/dsp
```

The probe pod must itself satisfy Pod Security Admission `restricted`; if it is rejected
outright, that is the namespace policy working as intended.

## Pod Security Admission

Every namespace created by `ds-namespaces` is labelled
`pod-security.kubernetes.io/enforce: restricted`. That makes the hardened pod spec an
admission-time requirement rather than a chart convention: non-root, no privilege escalation,
all capabilities dropped, seccomp `RuntimeDefault`.

`runAsUser` is a **numeric** uid (10001) for a concrete reason: kubelet cannot verify
`runAsNonRoot` against an image whose `USER` is a name, and refuses to start the container. All
service Dockerfiles pin uid/gid 10001 to match. **If you add a service, pin its uid the same
way.**

`automountServiceAccountToken: false` everywhere — none of these services call the Kubernetes
API, so a mounted token would be a credential with no purpose and a real blast radius.
