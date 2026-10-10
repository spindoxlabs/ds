# ADR-0029 — The dataspace's own hosts may resolve to a private address, only when listed

**Date:** 2026-10-10
**Status:** accepted, implemented 2026-10-10
**Refines:** the identity registry's outbound boundary (`P-8d`: only admissible addresses are
dialled for a counterparty-chosen URL)
**Amended:** 2026-10-10, scope extended to every did:web fetch in ds (see *Amendment*)

## Context

The identity registry fetches did:web documents (enrolment, presentation verification) and
delivers credentials to a holder's credential service. Both URLs come from a DID that a
counterparty chose, so under `DS_ENV=production` the outbound transport dials **only globally
routable addresses**, checked on the address actually dialled: a did:web host that resolves
to an internal address is an SSRF vector into the cluster and its metadata endpoint.

A deployment can resolve its **own** hosts privately from inside the cluster while they are
public from outside: split-horizon DNS answering `*.<baseDomain>` with the address of the node
that runs the ingress (no hairpin to the public address), or an in-cluster resolver answering
with the ingress controller's service address. Under the rule above every enrolment is then
refused (`resolves to a non-public address`), and nothing short of a code change admits it.

## Decision

An explicit allowance, **empty by default**, in two settings that only make sense together:

- `IDENTITY_REGISTRY_DID_WEB_INTERNAL_HOSTS`: the dataspace's own host suffixes, a list
  (`.ds.example.org`; a leading dot is implied); each must have at least two DNS labels;
- `IDENTITY_REGISTRY_DID_WEB_INTERNAL_NETWORKS`: the private networks those hosts may resolve
  to, a list of IPv4 or IPv6 CIDRs of any prefix length (a single address is a `/32` or
  `/128`).

A private address is admitted **only** for a host under a listed suffix **and** inside a listed
network. Everything else is as before:

- link-local (and so the cloud metadata endpoint), multicast, reserved and unspecified
  addresses are refused for every host, in every posture;
- a host outside the suffixes gets exactly today's rule;
- every address a name resolves to must be admissible, not only the first.

Refused at load (the service and the chart render both fail, naming the setting): one setting
without the other; a suffix of one label (`.org`), `.`, a wildcard or a malformed name; a
network that is a default route (`0.0.0.0/0`, `::/0`), public, link-local, loopback or
multicast. An active allowance is logged at every start.

The chart exposes it as `didWeb.{internalHosts,internalNetworks}`; a deployment sets it once
under `authority.identityRegistry.didWeb` and the helmfile forwards that block to the anchor
and every participant registry: the hosts are the dataspace's, not one release's.

## Consequences

- A cluster with private resolution of its own hosts can enrol under `DS_ENV=production`
  without weakening the rule for any other host.
- The allowance is a widened boundary that a reviewer must see: it is two values in the
  deployment's values file and a warning line in every registry's log.
- ~~Not covered: the services that verify a person's credential (`ds_auth.did_web`, connector,
  provenance) and the EDC's did:web resolution have no address guard at all.~~ Covered since the
  amendment below.

## Amendment (2026-10-10): one guard for every did:web fetch

**Decision (the maintainer):** the behaviour is the same wherever ds fetches a did:web
document. Three fetchers existed and only the identity registry's was guarded:

| Fetcher | Fetches | Guard |
|---|---|---|
| identity registry (`identity_registry.services.did_resolver`, async httpx) | enrolment, presentation verification, credential delivery | the rules, now from `ds_auth.address_guard`; its own transport |
| connector and provenance (`ds_auth.did_web`, sync) | the issuer of a person's credential (`X-User-VC`) | `ds_auth.address_guard.guarded_sync_transport`: httpx over an httpcore backend that resolves, checks and dials the checked address; no redirect, no environment proxy (both would move the request past the check) |
| EDC (upstream `WebDidResolver`) | the counterparty's DID during DCP | ds's `DidWebGuardExtension`: the same upstream resolver class, re-registered for `web` over a copy of the runtime's `OkHttpClient` whose `Dns` checks every answer |

The same refusal rules everywhere: public only under `DS_ENV=production`; private and loopback
too under `DS_ENV=dev`; link-local, multicast, reserved and unspecified never; every resolved
address checked, on the address dialled. The same optional allowance, **configured per
service** (`IDENTITY_REGISTRY_`, `CONNECTOR_`, `PROVENANCE_DID_WEB_INTERNAL_HOSTS`/`_NETWORKS`;
the EDC's `ds.did.web.internal.hosts`/`.networks`), validated the same way at load, logged the
same way at start. The charts expose `didWeb.{internalHosts,internalNetworks}` on
`ds-connector`, `ds-provenance` and `ds-edc`; the helmfile forwards the dataspace's one block
(`authority.identityRegistry.didWeb`) to them as the default, and a participant's block may set
its own.

**One implementation where the dependency graph allows it.** The rules and the allowance's
validation live in `ds_auth.address_guard`, which the identity registry, the connector and
provenance all depend on; the registry keeps only its async transport. The EDC is Java and
cannot share it: `DidWebAddressGuard` restates the rules, tested against the same vectors
(it is stricter than Python's `ipaddress` on a few special-purpose ranges).

**EDC 0.18.0, read at the tag.** `WebDidExtension` builds `WebDidResolver` over the shared
`EdcHttpClient` in `initialize` and registers it in `DidResolverRegistry`, whose
`DidResolverRegistryImpl` keeps one resolver per method (last `register` wins). Neither the
`OkHttpClient` nor the `EdcHttpClient` provider is `isDefault`, and both are injected by DSP,
DCP, OAuth2, the data plane and more, so overriding them would guard far more than did:web and
depend on extension order. `ExtensionLifecycleManager` runs every `initialize` before any
`prepare`, so ds registers its resolver in `prepare` and replaces EDC's regardless of order.
`edc.webdid.doh.url` (EDC's only per-resolver option) is refused at start rather than dropped.

**Not covered, deliberately:** URLs that are configuration rather than a counterparty's choice
(the trust list, the status registers, the identity registry's own URL, JWKS), and in the EDC
the other URLs a DID document or credential names (the DCP credential service, status lists,
DSP addresses), which go through EDC's shared client. A proxy configured on a client would be
the address checked, not the target; ds configures none.

## Alternatives considered

- **A hosts-only list.** Admits any private address for those hosts, including another
  service's if DNS is ever wrong. Requiring the networks keeps the exception to the addresses
  the operator expects.
- **Admitting private addresses under a flag.** Reopens the SSRF boundary for every
  counterparty-chosen host.
- **Pinning the hosts to addresses in the registry (a hosts file).** Duplicates DNS, and goes
  stale when the ingress moves.
