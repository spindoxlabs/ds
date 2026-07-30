# Integrating an external application

This page is for a team building an application **outside** this dataspace whose
users manage their own data sharing — a member portal, a utility's app, a
community front end. It describes the contract for recording those decisions so
they hold up later.

Nothing here requires code in this repository. The surfaces below are the whole
integration.

---

## Two ways to ask, and why the choice matters

A person's consent is only defensible if you can show **what they were shown**. So
the question is who renders the consent text.

| | Who renders the text | Who proves it |
|---|---|---|
| **(a) Subject-present** | this portal (`/my-data`) | the portal |
| **(b) External** | your application | **you** |

Mode (a) needs no integration: link your users to the portal and they decide
there. Choose it if you can.

Mode (b) is what the rest of this page documents. It gives you full control of the
experience and, with it, the obligation to prove what you displayed. That
obligation is not a formality — it is the difference between a consent record and
an assertion.

---

## What you need

1. **A service client** in the dataspace realm holding `connector.consent.provision`
   — plus, if you also provision identities, `identity-registry.credentials.write`,
   `identity-registry.memberships.write`, `identity-registry.keycloak.sync` and
   `identity-registry.organizations.read`. **Do not ask for `identity-registry.admin`**:
   it is a superset reaching DID and key management, and an operator should refuse it
   to a long-lived process. Ask the operator; it is a Keycloak client-credentials grant.
2. **The subject's dataspace DID.** If your application creates users, the identity
   registry issues a DID and a credential per person — see
   `docs/identity-and-dcp.md`. The DID is what the connector keys consent on; your
   own user id never leaves your system.
3. **The offers you intend to ask about**, read from this dataspace.

---

## Render from the published vocabulary

```
GET /ns/sharing-offers        # public, no credential required
```

Deliberately public: an onboarding flow has to render offers before anyone has an
identity. Each offer carries codes plus an English fallback — purpose, recipients,
retention, coverage, whether it is consent-based, and a `user_visible_hash` over
the facts a person is shown.

**Render from this, not from your own copy of the text.** Translation is yours to
do — the fallback exists so an unmapped code degrades to readable text rather than
disappearing — but the *facts* must come from here. Two independent copies of an
offer is how the thing you displayed and the thing you recorded drift apart, and
the drift is invisible until someone asks what a person actually agreed to.

Only offers with `requires_consent: true` get a control. A contract-based offer is
**disclosed, not toggled**: presenting a choice that does not exist is what
invalidates consent, and the connector answers `409` if you try.

---

## Record the decision

```
POST /consent/admin/shares
Authorization: Bearer <your service token>

{
  "subject_id": "did:web:…",          # the person's dataspace DID
  "offer_id": "…",                     # from /ns/sharing-offers
  "enabled": true,
  "legal_basis": {
    "source": "my-application",        # required — which system asked
    "consent_text_version": "1.0",     # required — which revision
    "rendered_text_sha256": "…",       # required — the exact bytes displayed
    "locale": "it",                    # strongly recommended
    "accepted_at": "2026-01-01T10:00:00Z",
    "submission_ref": "20260101-abc123"
  }
}
```

Name the **offer**, never a dataset. The connector expands it into per-dataset rows
and stamps the purpose and controller from the offer itself, so your record cannot
drift from the copy the person read.

### Which fields are yours, and which are not

| Field | Set by |
|---|---|
| `source`, `consent_text_version`, `rendered_text_sha256`, `locale`, `accepted_at`, `submission_ref` | **you** — evidence only you hold |
| `offer_id`, `controller`, `controller_role`, `user_visible_hash`, `basis_iri` | **the connector**, from the resolved offer |

You cannot set the second group — the connector derives it from the offer, so a
caller cannot record consent to something other than what the offer describes.

**Send only the fields in the first group.** Anything else in `legal_basis` —
a field from the second group, a typo, or an extra of your own — is a `422`,
naming the key. It is deliberately not ignored: accepting an unknown evidence
field and dropping it would answer `200` and leave you holding written proof the
connector never stored, which is the one failure an evidence record must not
have. If you need to attach something the model has no field for, that is a
change to this contract, not a key to add to the payload.

### The three required fields

Granting is refused (`422`) without `source`, `consent_text_version` and
`rendered_text_sha256`. Each carries part of the proof — which system asked, which
revision, and the exact bytes displayed. With any one missing, the record cannot
tie a decision to a rendering, and **decorative evidence is worse than none,
because it looks like proof**.

`rendered_text_sha256` is the hash of the text *you* displayed, in the locale you
displayed it. Compute it over the final rendered string, after translation and
interpolation. It is the one thing nobody else can reconstruct for you.

**Withdrawal needs no evidence.** `"enabled": false` is accepted without a
`legal_basis`: a person may always stop, and requiring proof to stop would make
withdrawal harder than consent.

---

## Codes and hashes only — never personal data

The connector's database is not a personal-data store, and this is enforced, not
merely requested. `source`, `rec_slug` and `submission_ref` are **opaque
references**; an email address in any of them is rejected.

That check catches the obvious case, not every case. Send an internal reference you
can resolve on your side, and keep names, addresses, fiscal identifiers and meter
identifiers out of the payload entirely.

---

## What happens next

- The connector writes one consent row per dataset in the offer, with your evidence
  attached, and emits a `ConsentGranted` (or `ConsentRevoked`) provenance event.
- The decision takes effect at query time: a provider's policy enforcement point
  reads it before returning rows.
- The person can see and change it themselves in this portal at `/my-data`,
  including the evidence record you supplied — **link them there rather than
  rebuilding it**. That view is authenticated by their own credential, which your
  application does not hold.
- A `409` means the offer is not consent-based; a `422` means the purpose or
  evidence failed validation. Both name the reason.

## What you do not need to build

- **A cross-participant consent API.** A consumer asks by negotiating; DSP already
  carries the requester's identity, cryptographically.
- **Your own consent history view.** `GET /prov/my/events` serves the person's own
  record, authenticated by their credential.
- **Your own offer catalogue.** `GET /ns/sharing-offers` is the published one.

---

## Related

| Topic | Where |
|---|---|
| Consent model and enforcement matrix | `docs/consent-and-sovereignty.md` |
| Identity, DIDs and credentials | `docs/identity-and-dcp.md` |
| Provenance events | `docs/provenance-and-lineage.md` |
| Purposes and the ODRL profile | `docs/governance-and-odrl.md` |
