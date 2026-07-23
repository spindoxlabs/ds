# Exposure and network policy

The design rule: **one public host per trust boundary, path-allowlisted,
everything else 404.** Anything not listed on this page is ClusterIP plus
NetworkPolicy, reachable only from named in-cluster callers.

## Public surface — three host shapes

### `portal.<baseDomain>` — the only human-facing host

| Path | Backend |
|------|---------|
| `/` (all) | `ds-portal-<participant>:30004` |

The portal is server-side rendered, so the browser never calls the connector,
provenance or catalog directly. The dev Caddy fan-in (`/api/connector/*`,
`/api/provenance/*`, `/api/catalog/*`, `/api/datasets/*`) exists only because the
dev portal runs on the host, and is **not reproduced** in the charts.

The chart sets `ORIGIN=https://portal.<baseDomain>`. It must match the Keycloak
redirect URI of the public `ds-portal` client, or the login flow fails.

### `<participant>.<baseDomain>` — the DSP and data-plane boundary

One host per participant. This host **is** the participant's `did:web` identity,
which is why DID resolution and the DSP endpoints share it.

| Path | Backend | Purpose |
|------|---------|---------|
| `/.well-known/did.json` | `ds-identity-registry` in the authority namespace, rewritten to `/dids/did:web:<participant>.<baseDomain>/did.json` | did:web resolution |
| `/protocol/*` | `ds-edc-<participant>:19194` | DSP protocol — federation |
| `/public/*` | `ds-edc-<participant>:19291` | data-plane EDR pulls by remote consumers |

Everything else on this host 404s.

An Ingress can only target a Service in its own namespace, so the DID path
reaches the authority-namespace registry through an `ExternalName` Service
(`<edc-release>-identity-registry`), with `upstream-vhost` set so the registry
sees its own hostname.

### `trust-anchor.<baseDomain>` and `users.<baseDomain>`

| Host | Path | Behaviour |
|------|------|-----------|
| `trust-anchor.<baseDomain>` | `/.well-known/did.json` | rewritten to `/dids/did:web:<trust-anchor>/did.json` |
| `trust-anchor.<baseDomain>` | `/status/*` | passthrough — StatusList2021 revocation lists **must** be publicly fetchable, or a verifier cannot determine whether a credential was revoked |
| `trust-anchor.<baseDomain>` | `/credentials/*` | only when `credentialService.expose` is true |
| `users.<baseDomain>` | `/<id>/did.json` | regex-captured to `/dids/did:web:users.<baseDomain>:<id>/did.json`; only when `exposeUserDids` is true |

Both optional hosts are off by default. Enable `exposeUserDids` only when
**remote** verifiers resolve your user DIDs; if all VC verification is local, the
`users` host can be dropped entirely. Enable `credentialService.expose` only if
remote verifiers query the DCP presentation endpoint directly instead of the
holder self-presenting — the endpoint is not anonymous (callers authenticate with
a self-issued DCP token signed by the requested DID's registered key), but it is
attack surface with no default consumer.

## Never exposed

| Surface | Port | Why |
|---------|------|-----|
| EDC management API | `19193` | creates and deletes assets, policies, transfers |
| EDC control API | `19192` | internal control plane |
| EDC api/health | `19191` | |
| ds-connector | `30001` | including `/internal/*` and `/webhooks/*` |
| ds-provenance | `30000` | |
| ds-federated-catalog | `30003` | |
| identity-registry `/admin`, `/sts`, `/memberships`, `/owners` | `30005` | mutate the trust anchor and read consent-relevant data |
| all `/metrics` | — | unauthenticated; NetworkPolicy restricts them to the Prometheus namespace |

The `ds-edc` Service publishes management and control **in-cluster**, but the
NetworkPolicy that admits the ingress controller lists only `protocol` and
`public`. So even a misconfigured Ingress path cannot reach them — the exposure
is denied twice, at routing and at the network layer.

## did:web over HTTPS

The dev stack resolves `did:web` over plaintext `:80` through a Caddy rewrite.
The charts do not carry that. The participant host and the trust-anchor host
serve `/.well-known/did.json` over TLS on 443, and `edc.iam.did.web.use.https` is
`true`.

DID documents carry the public keys every trust decision rests on. Fetching them
over HTTP hands participant identity verification to any on-path attacker. This
is why `didWebUseHttps` exists as a value at all — to make the invariant visible,
not to make it negotiable.

## One certificate per host

Several Ingress objects can share a host: nginx's `rewrite-target` is a
per-object annotation, so each rewrite behaviour needs its own object. Only
**one** of them may carry the `cert-manager.io/cluster-issuer` annotation, or
cert-manager issues competing Certificates that fight over the same secret.

The charts pass `issueCert: true` to exactly one Ingress per host and `false` to
the rest, and derive the TLS secret name from the host (`tls-<host-with-dashes>`)
rather than from the object, so they share the certificate.

Setting `global.ingress.tls.secretName` overrides this entirely and suppresses
the issuer annotation — the pre-created-certificate path.

## NetworkPolicy model

Kubernetes has no deny rule: a policy that selects a pod and lists no matching
peer denies everything else for that direction. So every service gets one
default-deny policy plus narrowly-scoped allows.

**Default deny** (ingress + egress) is rendered for every service when
`global.networkPolicy.enabled` is true, and always permits:

- DNS to `kube-dns` (UDP/TCP 53) — without it every other egress rule fails to
  resolve
- PostgreSQL on `global.postgres.port`, to `0.0.0.0/0` **except** the cloud
  metadata endpoint `169.254.169.254/32`

Broad-CIDR egress rules all carry that metadata exclusion: a pod that can reach
`169.254.169.254` can often mint cloud IAM credentials.

### Allows, per service

| Service | Ingress from | Egress beyond the default-deny baseline |
|---------|--------------|------------------------------------------|
| `ds-identity-registry` | ingress controller ns; any namespace labeled `dataspace.spindoxlabs.io/participant` | 443 (Keycloak JWKS, and the admin API when `keycloak-org-sync` runs) |
| `ds-edc` | ingress controller ns → **only** `protocol` + `public`; `ds-connector` in the same ns → management, api, control; peer EDCs in participant-labeled namespaces → `protocol` + `public` | authority ns `:30005` (STS, VP queries); own connector; 443 |
| `ds-connector` | `ds-portal` and `ds-edc`, same namespace | authority ns `:30005`; own EDC management and provenance `:30000`; 443 (Keycloak, external dataset API) |
| `ds-provenance` | `ds-connector`, same namespace | 443 (Keycloak JWKS) |
| `ds-federated-catalog` | `ds-portal`, same namespace | own connector; authority ns `:30005`; 443 (Keycloak) |
| `ds-portal` | ingress controller ns | same namespace `:30001`, `:30000`, `:30003`; authority ns `:30005`; 443 (Keycloak) |

Every service that verifies JWTs needs egress to Keycloak's JWKS endpoint on
443 — without it the baseline (DNS + Postgres only) fails every authenticated
request. All six service charts carry that rule.

### Adding an egress allow without touching a template

`.Values.networkPolicy.egress` is appended verbatim to the default-deny policy by
`ds.networkPolicy.defaultDeny`, so a release can open a path the chart does not
know about:

```yaml
networkPolicy:
  egress:
    - to:
        - ipBlock:
            cidr: 10.0.0.0/8
      ports:
        - {protocol: TCP, port: 8080}
```

Prefer a namespace or pod selector over a CIDR where the peer is in-cluster. Any
broad-CIDR rule should exclude `169.254.169.254/32`, as the chart-supplied ones
do.

Two extra policies are conditional:

- `<service>-metrics` — permits scraping from
  `global.monitoring.prometheusNamespace`, rendered only when
  `global.monitoring.serviceMonitor` is enabled.
- Peer-EDC ingress matches the **namespace label**
  `dataspace.spindoxlabs.io/participant: "true"`, set by the `ds-namespaces`
  release. A participant namespace created by hand without that label cannot
  reach anyone else's DSP endpoint.

### Verifying

```bash
# Management API must be unreachable from another namespace
kubectl -n ds-consumer run probe --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sS --max-time 5 http://ds-edc-provider.ds-provider:19193/api/v3/assets
# expect: timeout / connection refused

# DSP protocol from a peer namespace must work
kubectl -n ds-consumer run probe --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sS --max-time 5 http://ds-edc-provider.ds-provider:19194/api/dsp
```

The first probe pod must itself satisfy Pod Security Admission `restricted`; if
it is rejected outright, that is the namespace policy working as intended.

## Pod Security Admission

Every namespace created by `ds-namespaces` is labeled
`pod-security.kubernetes.io/enforce: restricted`. That makes the hardened pod
spec an admission-time requirement rather than a chart convention: non-root,
`allowPrivilegeEscalation: false`, all capabilities dropped, seccomp
`RuntimeDefault`.

`runAsUser` is set to a **numeric** uid (10001) for a concrete reason: kubelet
cannot verify `runAsNonRoot` against an image whose `USER` is a name, and refuses
to start the container. All service Dockerfiles pin uid/gid 10001 to match. If
you add a service, pin its uid the same way.

`automountServiceAccountToken: false` everywhere — none of these services call
the Kubernetes API, so a mounted token would be a credential with no purpose and
a real blast radius.
