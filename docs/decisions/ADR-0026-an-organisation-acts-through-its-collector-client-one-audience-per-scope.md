# ADR-0026 — An organisation acts through its collector client, one audience per scope

**Date:** 2026-10-05
**Status:** accepted, implemented 2026-10-05; amended the same day (below)
**Rules affected:** `D-20` (a consent writer is an organisation, never a plain service),
`D-21` (membership is checked against the organisation that speaks)

## Context

Four problems share one cause: the organisation-attributable acts of onboarding were
held by the wrong identities.

- **Membership writes had no working caller.** Since identity-registry bounds a
  membership write to the caller's own organisation, only an organisation's client may
  write one. The organisation client (`svc-ds-connector-<alias>`) did not hold
  `identity-registry.memberships.write`, and the plain `svc-ds-onboarding` client, which
  held it, names no organisation and is refused.
- **The organisation client's default token was replayable.** It carried
  `connector.consent.provision` and `connector.provider.write` as **default** scopes. The
  connector sends that token to identity-registry, to provenance and to every
  counterparty's connector (`GET /consent/pending`). A counterparty that received it could
  register consent at any connector that accepts the organisation as a collector, and the
  token named the generic audience `svc-ds-connector`.
- **One onboarding instance serves several organisations**, and several onboarding
  operators may serve one dataspace. Handing onboarding each organisation's connector
  secret would hand it that organisation's EDC management power: any holder of the secret
  can request `EDC_TOKEN_SCOPE`. The plain `svc-ds-onboarding` client is one secret
  shared by every operator, and it held cross-organisation grants: credential issuance,
  the offer-audience read (`connector.consent.audience`), disclosure records and
  `provenance.write`.
- **A suspended organisation kept acting.** Suspension changes the owner's status, its
  credential and its participant row, but not the Keycloak client. Membership writes did not
  read the status, `/memberships/check` counted the suspended organisation's rows, and a
  holder was accepted as "collecting for itself" whatever its status.

## Decision

1. **A collector client per organisation that collects consent.** It is called
   `svc-ds-collector-<alias>`, and identity-registry provisions it only for an organisation
   declared `collects_consent` (`organizations.yaml` for `org-sync`, `owners.yaml` →
   `Owner.collects_consent` for the promotion bundle, migration `0019`). The flag is
   declared by the anchor operator and is never inferred from consent-collector rows,
   because a holder that collects for itself has none. The client has:
   - `sub` set to the organisation's DID, through the same mapper as the organisation
     client, so every receiver sees the same organisation;
   - **no default scope and no client-level audience**, so a token that asks for nothing
     carries no ds audience and every ds service refuses it;
   - **no `management-api:*` and no `edc.management`**, so whoever holds its secret has no
     EDC power;
   - its own secret, `SVC_DS_COLLECTOR_<ALIAS>_SECRET` (the client id under `DS_ENV=dev`,
     required otherwise), rotated independently of the connector's secret.

   `ds_auth.Principal.organisation_context` accepts the prefix, so the collector client
   is that organisation. `organisation_client_kind` tells the two clients apart. The
   connector refuses the collector client on publishing, on the holder key list and on
   `/consumer/*`, as defence in depth: it holds none of those grants. Turning the flag off
   disables the client; it does not delete it.
2. **One audience per scope, checked by the receiver.** Each organisation-attributable
   scope is declared in `services/keycloak/clients.yaml` with exactly one `audience`
   (`ds_auth.SCOPE_AUDIENCES`):

   | scope | audience | routes |
   |---|---|---|
   | `identity-registry.memberships.write` | `svc-ds-identity-registry` | `POST /admin/memberships`, `DELETE /admin/memberships/{did}/{org}` |
   | `identity-registry.credentials.write` | `svc-ds-identity-registry` | `POST /admin/credentials/data-subject[/transition]`, `DELETE /admin/credentials/{id}` |
   | `connector.consent.provision` | `svc-ds-connector` | `POST /consent/admin/shares`, `POST /consent/request` |
   | `connector.consent.collector.read` | `svc-ds-connector` | `GET /consent/admin/subject-shares`, `GET /consent/admin/decisions` |
   | `connector.consent.audience` | `svc-ds-connector` | `GET /consent/admin/shares` |
   | `connector.disclosure.record` | `svc-ds-connector` | `POST /admin/disclosure` |
   | `connector.provider.write` | `svc-ds-connector` | `POST /provider/sync`, provider deletes |
   | `provenance.write` | `svc-ds-provenance` | provenance writes |

   On these routes the receiver requires its own audience in a service token's `aud`
   (`ds_auth.audience.check_audience_bound`). It does so on the route itself, not only
   through `verify_token`, which skips `aud` when no issuer is configured. It also refuses
   a **collector** token whose `aud` names another ds service. Such a token was asked for
   two acts at once and would be accepted at the other receiver as well. The rule is one
   scope per token.
3. **The organisation client asks for its acts.** `connector.consent.provision`,
   `connector.provider.write` and the new `connector.consent.collector.read` are
   **optional** on `svc-ds-connector-<alias>` (`ds_auth.ORGANISATION_ACTION_SCOPES`). The
   default token, the one the connector sends to counterparties, carries none of them.
   `EDC_TOKEN_SCOPE` is now stated explicitly as the 7 management scopes plus
   `edc.management`, byte for byte as before. It used to join every optional scope.
   Existing clients migrate on the next `org-sync` or promotion: `ensure_service_client`
   moves a listed optional scope out of the defaults.
4. **The read-backs have their own scope.** `GET /consent/admin/subject-shares` and
   `/decisions` require `connector.consent.collector.read`, so reading back no longer
   needs a token that can write. The name follows `connector.consent.holder.read`.
5. **The plain onboarding grants move to the collector client**, and the request gives
   the organisation where it names none:

   | grant | organisation |
   |---|---|
   | credential issue / transition | the request's `linked_participant_did` (the custodian) must be the token's DID |
   | credential revoke | the credential's `credentialSubject.linkedParticipant` must be the token's DID. An unknown id gets the same 403 |
   | offer audience read, disclosure record | the token's `sub`: this connector's own organisation, or a collector **accepted here** (the same admission as the consent write) |
   | provenance write | the token's `sub`, unchanged from what organisation clients already do |

   `svc-ds-onboarding` keeps working for these four grants **under `DS_ENV=dev` only**, as
   a logged transition (`ds_auth.audience.plain_service_transition`). Outside dev it gets
   a 403. Membership writes stay refused to it. Its grants are removed from
   `clients.yaml` **last**, after the onboarding service calls as the collector client.
   `organizations.read`, `resolve` and `keycloak.sync` stay on it for now.
6. **A suspended organisation** (`Owner.status != verified`) writes no membership and
   issues or revokes no credential through its own token. `/memberships/check` answers
   `member: false` for its rows, which stay for reinstatement. It is not accepted as
   collecting for itself. An administrator is not bound by these rules, so suspended
   rows can still be cleaned up.

## Why not EDC

Checked from source at `v0.18.0` (DCP `v1.0`), following the playbook
`checking-edc-at-the-pinned-version`:

- **Person → organisation membership has no EDC equivalent.** DCP excludes human holders
  (`specifications/trust.model.md@v1.0:46-48`). EDC's credential validation requires
  every subject to equal the presentation's holder
  (`extensions/common/iam/decentralized-claims/lib/verifiable-credentials-lib/src/main/java/org/eclipse/edc/iam/verifiablecredentials/rules/HasValidSubjectIds.java@v0.18.0`).
  So the anchor's membership rows stay, and so does the authority over who may write them.
- **The per-audience pattern is copied from DCP's self-issued token.** The token names the
  counterparty as `aud`
  (`extensions/common/iam/decentralized-claims/decentralized-claims-service/src/main/java/org/eclipse/edc/iam/decentralizedclaims/service/DcpIdentityService.java@v0.18.0:113-116`),
  and the receiver refuses any other value
  (`extensions/common/iam/decentralized-claims/decentralized-claims-core/src/main/java/org/eclipse/edc/iam/decentralizedclaims/core/validation/SelfIssueIdTokenValidationAction.java@v0.18.0:57`).
  ds cannot reuse that code: it is Java, and it runs on the DSP leg, whereas consent
  registration is a ds HTTP call.
- **EDC's management API binds no audience**
  (`extensions/common/api/management-api-oauth2-authentication/src/main/java/org/eclipse/edc/connector/api/management/authn/ManagementApiOauth2AuthenticationExtension.java@v0.18.0:77-79`)
  and checks scopes per route
  (`extensions/common/auth/auth-authorization-oauth2-lib/src/main/java/org/eclipse/edc/api/authorization/filter/ScopeBasedAccessFilter.java@v0.18.0`).
  That is why the collector client holds no `management-api:*` scope, and why R12's
  `ManagementAudienceFilter` exists.

## Residual

- **The audience is per service, not per counterparty.** A token asked for
  `connector.consent.provision` names `svc-ds-connector`, so it is accepted by every
  connector that accepts this collector. Binding it to the one holder it was sent to would
  need the holder's identity in `aud`. Keycloak 26 offers no request-time audience for
  `client_credentials` and implements no RFC 8707 `resource` parameter. Two routes
  remain:
  - a client scope per counterparty, which was excluded;
  - standard token exchange with an `audience` parameter. This still needs one audience
    mapper per counterparty on the collector client, synchronised from the
    consent-collector relations, the exchange enabled per client, and each connector
    verifying its own organisation id as audience.

  Its cost is not worth paying now. The exposure is bounded: a holder that replays such a
  token reaches only connectors that accept that collector, and writes only for that
  collector's members (`D-21`).
- An accepted collector reads the **whole** audience of an offer at a holder, including
  subjects that another collector registered. That is narrower than the plain client it
  replaces, which read it at every connector. Filtering the read by `collector` is a
  change to the route body.
- `identity-registry.keycloak.sync` (binding a login to a DID, which ADR-0024 relies on)
  stays on the shared `svc-ds-onboarding` client and is cross-organisation. It is an
  open question for the requester. *Answered: see the amendment below.*
- A suspended organisation's clients stay **enabled** in Keycloak. The receivers refuse
  their acts, but a token can still be minted.

## Consequences

- Callers request the scopes. The helm connector sync job asks for
  `connector.provider.write` when it runs as the organisation client. The ds-e2e flows
  ask for the consent write and its read-back. Keycloak accepts a requested scope that is
  a default assignment, so callers can ship before the realm moves. An unassigned scope is
  an `invalid_scope` error, so the realm must move before callers request a scope only
  the new shape grants. Both were verified on a local Keycloak.
- The onboarding service needs one collector secret per organisation alias, and requests
  one scope per token.
- A host realm (posture B) declares the collector client in its own client file:
  `hardcoded_claims.sub`, no `default_scopes`, the optional scopes above. It also needs
  celine-policies with scope-level audiences, which R12 already requires.

## Amendment, 2026-10-05: the login binding, suspended clean-up, a 404 on a delete

The requester answered the open question in the residual above, and two more.

1. **`identity-registry.keycloak.sync` moves to the collector client**, bounded to the
   organisation's own members. `POST /admin/keycloak/sync` writes the
   (realm, Keycloak user id) → DID mapping that ADR-0024's person binding reads, so whoever
   held the shared grant could bind any login to any DID. Now:
   - the scope is declared with the audience `svc-ds-identity-registry`
     (`ds_auth.KEYCLOAK_SYNC_SCOPE`, `SCOPE_AUDIENCES`), is one of
     `COLLECTOR_CLIENT_OPTIONAL_SCOPES`, and the route is audience-bound like the other
     writes;
   - an organisation token may write a mapping only for a DID that holds a data-subject
     credential, **not revoked**, whose `credentialSubject.linkedParticipant` is the
     token's DID, while the organisation is verified
     (`identity_registry.dependencies.authorize_keycloak_sync`). The credential is the
     registry's own record that this organisation onboarded this person: it is signed by the
     anchor and issued to an organisation only for its own DID (decision 5). The DID's
     namespace was not chosen, because one human keeps one DID across organisations, so a
     second organisation's member can live in the first one's namespace. A **membership** was
     not chosen either: an organisation writes its own memberships, and that write bounds the
     organisation, not the DID, so the rule would let an organisation make anybody its member
     and then bind its own login to them;
   - an organisation does **not rebind** a DID already bound to another login. The same
     (realm, user id) re-syncs, which is how an email or username correction arrives.
     Anything else is the operator's act, as the existing `409` for the reverse case says;
   - an unknown DID gets the same `403` as another organisation's, before any lookup;
   - the plain `svc-ds-onboarding` is accepted only under `DS_ENV=dev`, with a warning
     (`ONBOARDING_TRANSITION_SCOPES`), and gets a `403` elsewhere. `identity-registry.admin`
     keeps the cross-organisation reach.

   The onboarding service asks for the scope alone as the community's collector client, at
   approval (before anything is issued) and on an email correction's re-sync.
2. **Cleaning up a suspended organisation is an operator duty.** Its own tokens cannot delete
   its memberships, as decision 6 says. The rows stay for reinstatement, uncounted. When the
   organisation is not coming back, the operator removes them with
   `DELETE /admin/memberships/{did}/{alias}` under `identity-registry.admin` (a service token or
   a `platform-admin` login), or with `ir-cli membership remove`, which resolves an alias to the owner
   id as the admin API does. Both are tested against a suspended organisation.
3. **A `404` on a membership delete or a credential revocation** is still the state a delete
   wants, so onboarding treats it as success. It now logs it as a **misalignment**: onboarding
   recorded something the registry does not hold, which is what an operator's clean-up looks
   like from that side.

Residual of this amendment: a person holds one credential per role (ds#30), so a second
organisation's issuance for the **same role** is refused with `409`, as is its transition of
that credential. Until 2026-10-05 it re-delivered the first organisation's credential, whole,
to the second organisation's custodian and answered with its id, and a transition suspended
it and re-linked the successor. So when two organisations onboard one person in the same
role, the second holds no record of that person and its Keycloak sync is refused. The mapping
the first one wrote already binds the same login, so nothing is lost, but the second
onboarding's approval now fails at issuance. The open question on several onboarding
instances serving one dataspace covers it.

No EDC mechanism applies: binding a Keycloak login to a natural person's DID is outside DCP,
which excludes human holders (see "Why not EDC" above).
