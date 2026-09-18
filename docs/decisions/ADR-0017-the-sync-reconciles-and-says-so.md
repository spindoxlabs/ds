# ADR-0017 — The provider sync reconciles, and its answer agrees with what happened

**Date:** 2026-09-18
**Status:** accepted
**Amends:** ADR-0014 (decision 2 — what an organisation actor may do)
**Rules affected:** none new; `ENV-09` and `X-10`/`X-11` apply unchanged

## Context

A deployment published for the first time on 2026-09-18 and found the whole
provider-sync path broken in five independent ways at once. Every finding was measured
over the wire against EDC 0.18.0.

1. **The default asset id was unpublishable.** With `dataspace.asset.id` unset, the id was
   derived as `{base_url}/datasets/{key-with-slashes}`. The sync deletes before it creates
   and addresses an asset **by path**, percent-encoded, so the request carried `%2F` inside
   a path segment. The servlet container refuses that and answers **400 with an empty
   body**, before EDC routes the request. Measured at a running EDC: `simple-id` → 404
   `ObjectNotFound`, `a:b` → 404, `http://…/a/b` → **400, empty**.
2. **The failure was unreadable.** `EDC delete_asset 400:` — a sentence ending in a colon,
   because the message interpolated an empty body.
3. **The route answered `200` regardless.** All eight datasets were in `errors` and the
   deployment's publishing step, which checked the status code, reported success against
   two empty catalogues.
4. **The sync never withdrew anything.** A dataset removed from governance kept its asset,
   both policies and its contract definition, and went on being offered over DSP — while
   the next run reported a *higher* published count, because the count is of what published
   rather than of what is on offer.
5. **Nobody could publish, and anybody could.** No production identity existed for
   `POST /provider/sync` (the Taskfile used the e2e harness client, which is declared in a
   file a host realm never mounts), and the permission carried **no owner perimeter** — any
   holder could sync any connector it could reach.

ds's own e2e suite met none of them, and each miss is a hole in what the suite could
observe: its dev governance pins every `asset.id`; every flow read the route's `200` and
none read `errors`; no flow ever removed a dataset; and one harness client held every grant,
so no flow could be refused.

## Decision

### 1. An unset `asset.id` is the dataset key, and an unaddressable id is refused

The key is already the dataspace-wide name governance, the consent vocabulary and
`/internal/dataplane/authorize` use for a dataset. Deriving the id from the data plane's
address was wrong twice: it is unaddressable, and it writes a deployment's own address into
the identifier a counterparty negotiates against, so the id changes whenever the plane
moves.

An id containing a slash — declared or derived — raises `UnaddressableAssetId` at mapping
time, naming the dataset. The failure moves from an unattributable empty-bodied 400 to a
message a producer can act on.

**Breaking** for a deployment that published under the derived form and pins no id: its
assets are republished under the key, and decision 3 removes the old ones in the same sync.

### 2. Assets stay path-addressed; `POST …/assets/request` was considered and rejected

`AssetApiV5Controller` at `v0.18.0` exposes create, **query** (`POST /request`, returning a
list), `GET {id}`, `DELETE {assetId}` and update. Three things follow, and together they
settle it:

- it cannot fix the failure — there is no body-addressed **delete** for an asset, a policy
  definition or a contract definition, and the delete is what failed;
- it is less consistent — every single-resource call on this client is path-addressed
  across six resource families, and `policydefinitions` and `contractdefinitions` have the
  same id shape and could not follow;
- it reports worse — a path `GET` answers `404 ObjectNotFound`; a query answers `200 []`,
  which cannot distinguish *absent* from *filtered out*.

What that option was really asking for — a legible error — is decision 4 instead.

### 3. The sync reconciles

`POST /provider/sync` makes EDC match the governance it was given. What EDC holds and that
governance does not declare is removed: contract definition, then policies, then asset,
which is the only order EDC accepts. Removed asset ids come back in `SyncResult.withdrawn`.

Three bounds, each of which is the decision rather than the implementation:

- **only assets ds published**, identified by a `{profile-prefix}:datasetKey` property the
  mapper now writes. An EDC runtime may legitimately hold objects ds did not create, and
  *governance does not declare it* is not evidence that ds did. An asset published by an
  older ds is left alone until one sync under this version labels it;
- **only datasets governance no longer declares.** A declared dataset that was *refused* —
  an unresolvable purpose, a dangling offer, an exposure conflict — keeps what it had: that
  refusal deliberately leaves a published version standing rather than tearing it down over
  a bad edit, and a reconcile must not undo that decision by another route;
- **plus the asset a still-declared dataset has just moved away from**, when its id changed
  in this run — otherwise a rename leaves the old asset on offer for ever.

A 409 (the asset has agreements) is reported, never swallowed.

**An asset under agreement is updated in place, not kept.** Found on the first live sync
after this change and included here because it is the same defect one level down: EDC refuses
to delete an asset referenced by an agreement or an ongoing negotiation, and the sync logged
*"already exists (has agreements) — keeping"* and moved on — so a governance edit to such an
asset published **nothing at all**, silently, for as long as the agreement stood. Measured:
three of a dev stack's four assets, none of which received the property the same run had just
written for the fourth, which also made them permanently invisible to the reconcile above.

`PUT …/assets` is the call EDC provides for it, and it is the one **body-addressed** write in
the client — so the id-in-a-path-segment problem in decision 1 never touched it. EDC's own
annotation calls updating an asset a danger zone for offers already sent out. The trade is
taken deliberately: the alternative is publishing a governance change that does not apply.

**`governance_yaml_path` in the request body reconciles too.** One rule — *make EDC match
this file* — rather than two. An ad-hoc publish against a partial file therefore withdraws
what that file omits, and that is stated in the connector's documentation.

### 4. The answer agrees with the body

`200` when nothing failed, **`207 Multi-Status`** when some datasets published or were
withdrawn and some failed, **`502 Bad Gateway`** when nothing did. The body is the same
`SyncResult` in all three, so no caller loses information: a partial publish is a real
state and the list of what landed is what an operator fixes forward from.

An EDC failure with an empty body now names the request that was refused instead of
trailing off after a colon.

### 5. A participant publishes its own catalogue, and only its own

Organisation clients gain `connector.provider.write` and `connector.provider.read`. This
**amends ADR-0014 decision 2**: an organisation actor may publish, as well as discover and
negotiate. A registered participant that may negotiate for another's datasets may offer its
own.

It lands **only together with a perimeter**, because without one the grant would let every
organisation in a shared realm sync every connector it can reach. `require_provider_write`
now asks one question — *does this caller act for this participant?* — per caller class:

| Caller | Bound by |
|---|---|
| organisation client | `sub` must name this connector's participant context. The rule `_bind_organisation` already applies on `/consumer/*` |
| a person | an organisation claim resolving, in the owners registry, to this connector's participant DID. Exempt where the deployment models no organisations and `owner_scoping_strict` is off |
| `connector.admin` | nothing — the deployment operator's grant crosses participants by design |
| a plain service token | nothing — it names no participant |

This also tightens `ds-participant-admin`, which is a realm group and therefore bound to no
connector: a participant's operator could publish at every other participant's connector.

**The plain-service class is the one this perimeter does not narrow, and that is stated
rather than left implicit.** A token that names no participant has nothing to be bound to;
the control is decision 6 — the identity that publishes holds nothing else.

### 6. Two publisher identities, for two different callers

- **A participant's own organisation client is the publisher in production.** It exists per
  participant, it is bounded by decision 5, and self-service publishing is what decision 5
  approves.
- **`svc-ds-publisher` is the driver's identity** — dev, CI, a cluster bring-up. It holds
  `connector.provider.read` + `.write`, the `svc-ds-connector` audience, and **no**
  `management-api:*` and **no** `connector.admin`. It exists because the alternative is
  handing a bring-up script an organisation's secret, and that secret also opens that
  participant's **EDC management API** to anything with network reach to the port —
  ADR-0014 decision 3 makes port isolation the only control there, since EDC's OAuth2
  filter does not check `aud`.

It is declared in `clients.yaml`, the file that crosses into a host realm, which
`svc-ds-e2e` is not and never was. `svc-ds-e2e` loses `connector.provider.write` and keeps
the read: while one client held every grant, no e2e flow could be **refused**, so the
perimeter had nothing to prove itself against.

The `ds-connector` chart gains a `post-install`/`post-upgrade` hook Job, rendered for a
provider-role participant with governance mounted, using either identity.

## Consequences

- A deployment that relied on the derived asset id republishes under the dataset key and
  has its old assets withdrawn in the same run. One that pins ids is unaffected.
- A caller that read `POST /provider/sync`'s status code and ignored the body now sees
  failures it previously did not. That is the point; it may still be a change in behaviour
  for a script.
- Removing a dataset from governance now takes it off offer. A deployment that relied on
  the old behaviour to keep serving a dataset it had stopped declaring will stop serving it.
- An operator who holds `connector.provider.write` through a realm group, for an
  organisation that is not this connector's participant, is refused where they previously
  were not.
- **A withdrawal emits no provenance event.** `CataloguePublished` has no counterpart, and
  adding one is a change to the provenance service's PROV-O vocabulary (an entity
  invalidation, `prov:wasInvalidatedBy`, not another generation) with readers in the portal
  and the graph builder. It is a decision for that service, not a side effect of this one,
  and it is owed rather than done.
- `services/connector/e2e-governance-probe/` exists solely so `ds-e2e --flow
  provider-withdrawal` can change what governance declares without restarting a container.
  It is not a deployment fixture.
- **`ds-e2e clean` no longer re-syncs the providers**, and its removal is a consequence of
  decision 4 rather than a tidy-up. It dropped and recreated the three EDC databases and then
  synced — *before* `e2e:prepare` restarts the EDCs, and an EDC runs its schema migration at
  boot, so every write answered 500. It had never worked; it looked like it had because the
  route answered `200` with everything in `errors`. The publish that works is
  `task e2e:sync-providers`, after the restart and the readiness gate.
