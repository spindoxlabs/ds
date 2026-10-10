# ADR-0029 — The dataspace's own hosts may resolve to a private address, only when listed

**Date:** 2026-10-10
**Status:** accepted, implemented 2026-10-10
**Refines:** the identity registry's outbound boundary (`P-8d`: only admissible addresses are
dialled for a counterparty-chosen URL)

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
- Not covered: the services that verify a person's credential (`ds_auth.did_web`, connector,
  provenance) and the EDC's did:web resolution have no address guard at all; they resolve the
  dataspace's hosts privately today. Whether they should gain the same boundary is a separate
  decision.

## Alternatives considered

- **A hosts-only list.** Admits any private address for those hosts, including another
  service's if DNS is ever wrong. Requiring the networks keeps the exception to the addresses
  the operator expects.
- **Admitting private addresses under a flag.** Reopens the SSRF boundary for every
  counterparty-chosen host.
- **Pinning the hosts to addresses in the registry (a hosts file).** Duplicates DNS, and goes
  stale when the ingress moves.
