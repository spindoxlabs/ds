# Participation and trust

Who may take part, how they prove it, and what happens when that proof is withdrawn.

Covers `DSSC-TRF-01`–`14`, `-38`, `-41` and `DSSC-IAM-04`–`08`, `-13`, `-14`, `-26`–`-30`.

## 1. Kinds of participant

| Kind | Identified by | Held where |
|---|---|---|
| **Organisation** (participant) | a `did:web:` DID with a registered P-256 key, plus a `MembershipCredential` | identity-registry participant registry |
| **Owner** | a named alias resolving to a canonical URI (DID preferred over URL) | identity-registry `Owner` table |
| **Natural person** | a subject DID, plus a `DataSubjectCredential` and/or `ConsumerUser` credential | identity-registry, mapped from a Keycloak user |
| **Service** | a Keycloak client with `client_credentials` and a declared scope set | `services/keycloak/clients.yaml` |

An organisation and an owner are not the same thing and the distinction is load-bearing: a
participant is a party that speaks DSP, an owner is a party that datasets are attributed
to. One organisation may be the owner of several dataset collections, and a dataset's owner
may be a party that operates no connector at all. `governance.yaml` `ownership[].name`
resolves through the owners registry to the ODRL assigner.

**Deployment decision.** The set of admissible participant kinds is fixed by the code. Who
may hold each is a deployment decision, expressed through the onboarding criteria below and
the Keycloak realm.

## 2. Joining

An organisation joins through the onboarding lifecycle in the identity-registry:

```
application → verification → owner created → agreement accepted
  → OrganizationCredential issued → promoted to participant → provisioning bundle
```

Each step is a distinct API call and a distinct state; `ir-cli org apply --file owners.yaml`
walks the whole chain per entry and is idempotent. The public application form is
deliberately outside the authentication wall — an applicant has no account by definition.

**Rules:**

| # | Rule | Status |
|---|---|---|
| P-1 | An organisation is not a participant until it has been promoted. Promotion requires a verified application, a resolved owner, and an accepted agreement | **Enforced** |
| P-2 | Promotion issues an `OrganizationCredential` signed by the trust anchor | **Enforced** |
| P-3 | Every participant holds at minimum a data space membership credential (`DSSC-IAM-08`) | **Enforced** |
| P-4 | Onboarding is idempotent — re-running it must not duplicate a participant, an owner, a credential or an agreement acceptance | **Enforced, untested** at the task level; the `identity:bootstrap` task does not fail on a partially applied seed (defect P2-1) |
| P-5 | Assurance levels for verification are the deployment's responsibility (`DSSC-IAM-14`, KYC/KYB). For an **organisation** the platform records *that* verification happened (`verified_by`, `evidence_ref`); for a **natural person** the credential additionally records *who attested and by what method* (`verifiedBy`, `verificationMethod`) | **Declared, and now carried by the credential.** ds does not perform KYC — whoever runs onboarding does — so the attestation travels with the credential rather than being implied by its existence |

## 3. Identity and attestation

**Decision: DIDs are `did:web:`, keys are EC P-256 (ES256), credentials are W3C
Verifiable Credentials, and exchange follows DCP.**

| Mechanism | Choice |
|---|---|
| Identifier | `did:web:<host>`, resolved over HTTP in dev and HTTPS in production (`edc.iam.did.web.use.https`) |
| Key type | EC P-256, `ES256` |
| Credential format | W3C VC, JWT-serialised, signed by the trust anchor key |
| Credential exchange | Decentralized Claims Protocol — self-issued token to `/sts/{did}/token`, presentation query to `/credentials/{did}/presentations/query` |
| Revocation | StatusList2021, published at `GET /status/{list_id}` |

Three credential types exist: `MembershipCredential` (an organisation is in the data
space), `DataSubjectCredential` (a natural person may exercise subject rights),
`OrganizationCredential` (an organisation's onboarding outcome). `ConsumerUser` is a VC
role for a person acting on an organisation's behalf.

**VC roles are additive.** The same human may be a data subject about their own consumption
and a consumer user acting for an organisation. Nothing may assume one role per person.

| # | Rule | Status |
|---|---|---|
| P-6 | A DID document is served only by the instance that holds that DID's key. A **subject** DID has no key and its document carries no verification method — it resolves so that consent records and provenance can point at it, and asserts nothing it cannot back | **Enforced** — a keyless *participant* DID is a 404, which is how a registry says "I recorded that this party exists; I am not the one who publishes their document" |
| P-7 | A DID's private key never leaves the instance that generated it, and is encrypted at rest. **The trust anchor holds no private key but its own, and a natural person has none** | **Enforced** — Fernet, one `IDENTITY_REGISTRY_ENCRYPTION_KEY` per instance; checked at every startup and by `ir-cli key custody-check`, which exits non-zero on a private key for a DID this instance does not publish |
| P-8 | A presentation query is answered only to a **verifier** that proves control of its own DID *and* presents an access token this participant's STS granted it. The grant's scope bounds what the presentation may contain (`DSSC-IAM-13`, proof of control) | **Enforced** |
| P-8a | The verifier's signature is checked against the key in **its own DID document**, resolved over did:web — never against a key this registry happens to hold | **Enforced** |
| P-8b | The revocation list is served signed, by the trust anchor, GZIP-encoded as StatusList2021 requires | **Enforced** |
| P-9 | Every issued credential is allocated a distinct StatusList index | **Enforced** — a database allocator, not a scan of the register (migration `0011`, `tests/test_status_list_allocation.py`). Measured on the dev registry: 16 credentials, 16 distinct indices |
| P-10 | A credential's status bit is set **only** on revocation, never at issuance | **Enforced** — measured on the dev registry: the only set bits are the indices of the credentials whose status is `revoked` |
| P-11 | Signature verification is never skipped, in any environment | **Enforced.** The EDC's demo identity fallback — which accepted a self-issued token without checking its signature and minted a `MembershipCredential` for the signer — **is deleted**, so there is no longer a switch to get wrong. `task secrets:check` fails on `DS_DEMO_IDENTITY_ENABLED` to stop it returning. Python services keep their `ProductionGuard` checks |

## 4. The trust anchor

**Decision: one trust anchor per dataspace — issuer, participant registry and StatusList — and
one identity-registry instance per participant, holding that participant's own key.**

The same image in two roles (`IDENTITY_REGISTRY_ROLE`). A `participant` instance serves only
what a holder serves: its own DID documents, its own Secure Token Service, its own Credential
Service. Registry questions — who is a participant, what was issued, what was agreed — stay
with the anchor, which is why a participant's connector still points at it for those.

**This used to be one instance holding every participant's private key**, and the consequence a
deployment had to accept was that *the trust anchor can impersonate any participant*. That is no
longer true, and it is **checked rather than asserted**: an organisation generates its own
keypair, proves control of it at enrolment (`P-20`), the anchor records the public half only,
and every instance audits its own custody at startup (`P-7`).

Satisfies `DSSC-IAM-06`, `-07`, `-29` and `DSSC-TRF-41`. See
[Scope and deviations](scope-and-deviations.md) §3.1 for what remains — the custody of natural
persons' credentials (§3.1.2), not participants'. Issuance message shapes (§3.1.1) are closed:
they are checked against DCP's own JSON schemas.

What a deployment must still accept: each instance's encryption key is a single point of
unrecoverable loss **for that instance**. The blast radius is one participant, not the dataspace.

| # | Rule | Status |
|---|---|---|
| P-12 | The list of participants, including inactive ones, is published to participants (`DSSC-TRF-05`) | **Enforced** — `GET /admin/participants`; note the federated catalogue does not filter on `active` (defect P1-3) |
| P-12a | The list of **accredited entities** — trust anchors and trust service providers, **including revoked ones** — is published machine-readably and unauthenticated (`DSSC-TRF-05`, `-07`, `-17`, `DSSC-BIZ-143`) | **Enforced** — `GET /trust`. Public for the same reason as `P-13`: a counterparty decides whether to accept a credential before it has any relationship with this dataspace, and a federation partner reads this before anything else |
| P-12b | Every entry names its **scope of attestation** (`DSSC-TRF-19`), and a trust service provider names the anchor it derives authority from (`DSSC-TRF-21`) | **Enforced** — both are required with no default. An empty scope is not a wildcard: defaulting it would make the most permissive possible entry the easiest one to create |
| P-12c | Withdrawing accreditation **marks an entry revoked with a reason; it never deletes it** | **Enforced** — a list that forgets what it used to trust cannot answer whether a credential already in circulation was legitimate when it was issued |
| P-13 | The revocation list is public and unauthenticated | **Enforced** — `GET /status/{list_id}` |
| P-14 | Trust services validate attestations submitted by participants against the criteria (`DSSC-TRF-38`) | **Enforced** for DCP presentation queries; **not enforced** as a rulebook-conformity check — see the gap below |
| P-15 | Every instance's encryption key must be backed up outside the cluster; losing one makes that instance's DID keys unrecoverable | **Declared** — the blast radius is now one participant, not the whole dataspace |
| P-20 | A participant's identity is **proved, never issued**: the organisation generates its own keypair, publishes its own DID document, and presents a self-issued token signed by that key to enrol (`DSSC-IAM-13`, proof of control). The anchor mints no participant key and no STS secret | **Enforced** — `POST /issuer/credentials`, DCP's Credential Request API. The operator's chain ends at an enrolment code; `ir-cli participant add` is a refusal |
| P-22 | **Where to enrol is discoverable from the anchor's DID alone**: its DID document publishes an `IssuerService` entry, and that URL is routed and serves issuer metadata | **Enforced** — the entry is written by `ir-cli bootstrap` and the e2e `dcp-trust` flow *follows* it rather than reading it. It was published pointing at a URL neither the dev proxy nor the production Ingress routed: a document advertising an endpoint that 404s is the failure that looks most like success |
| P-21 | A credential is issued only to a DID whose control has been proved, and is **delivered to the holder's own credential store** — the issuer keeps the issuance record, the holder keeps what it can present | **Enforced** — DCP Storage API, `POST /credentials/{did}/credentials`, authenticated by the issuer's own self-issued token and refused from any issuer this participant does not trust |

## 5. Compliance verification — the open gap

`DSSC-TRF-02`, `-03` and `-04` require that the rulebook support **automated conformity
assessment**, and that compliance verification services validate participants and services
against it.

**This does not exist.** `task compliance:validate` validates a *governance file* against
the ODRL profile and the registries — it does not validate a *participant* against this
rulebook. The name is misleading and should not be read as conformity assessment.

What would close it, in rough order of cost:

1. A machine-readable projection of the rules on this page (participant must hold
   credential types X, must have accepted agreement version Y, must publish a catalogue
   reachable at Z).
2. A periodic check run by the trust anchor against every registered participant.
3. Suspension as a state distinct from deactivation, with the StatusList bit as the
   enforcement point — which requires **P0-3** fixed first.

Until then, conformity is asserted at onboarding and never re-checked.

## 6. Leaving, suspension and revocation

| # | Rule | Status |
|---|---|---|
| P-16 | Revoking a participant's membership credential removes their ability to negotiate — the DCP presentation query stops satisfying the membership constraint | **Enforced** in design; blocked in fact by **P0-3** |
| P-17 | Revocation does not retroactively invalidate completed transfers. What was lawfully transferred stays transferred; the obligations attached to it (retention, deletion) survive | **Declared** |
| P-18 | Revocation of a *consent* is different from revocation of a *credential* and terminates a running transfer | **Enforced** — `AgreementConsentFunction` on EDC's `policy.monitor` scope. See [Personal data](personal-data.md) §5 |
| P-19 | A departing participant's provenance records are retained; they are evidence about the data space, not the participant's property | **Declared** |

## Blueprint rows

**Closed by this page:** `DSSC-TRF-01`, `-05`, `-08`, `-12`, `-13`, `-14`; `DSSC-IAM-08`,
`-13`, `-14`, `-26`, `-27`, `-28`, `-30`.

**Stated but blocked by a defect:** `DSSC-IAM-05` (validation — P0-3), `DSSC-TRF-05`
(revoked listing — P0-3), `DSSC-IAM-04` (issuance is implemented but produces
revoked-at-birth organisation credentials — P0-3).

**Open:** `DSSC-TRF-02`, `-03`, `-04` (§5). `DSSC-IAM-06`, `-07`, `-29`, `DSSC-TRF-41`,
`DSSC-SVD-30` — participant-controlled credential stores; deviation recorded in
[Scope and deviations](scope-and-deviations.md) §3.
