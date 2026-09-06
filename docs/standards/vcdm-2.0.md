# VCDM 2.0 and Bitstring Status List — the credential model ds has not moved to yet

ds issues Verifiable Credentials and publishes their status. Both of those rest on W3C
Recommendations that reached that state on **15 May 2025**, and **ds implements the
generation before each**: the 1.1 data model, and a Community Group draft called
StatusList2021 whose specification text is no longer published anywhere.

This page records **what the current documents say, where the code sits against them,
what a migration would actually cost, and which of those costs are measured rather than
assumed** — so the decision in
[`a-role-change-is-a-reissue`](#8-why-this-page-exists-now) rests on checkable facts.

!!! note "Nothing here is broken today"
    The pairing ds emits is internally consistent and its verifier accepts it — the
    revocation and suspension paths are proved end to end by the `dcp-trust` and
    `org-onboarding` flows. This is a page about a **standards position**, not a defect.
    What the position costs is that ds cannot express any credential lifecycle beyond
    "valid / suspended / revoked", and that the older document is unciteable.

---

## 1. The two documents

| | Verifiable Credentials Data Model | Status list |
|---|---|---|
| **Current** | [VCDM 2.0](https://www.w3.org/TR/vc-data-model-2.0/) — **W3C Recommendation, 15 May 2025** | [Bitstring Status List v1.0](https://www.w3.org/TR/vc-bitstring-status-list/) — **W3C Recommendation, 15 May 2025** |
| **ds emits** | VCDM 1.1 — `@context: https://www.w3.org/2018/credentials/v1` | StatusList2021 — `type: StatusList2021Entry` |
| **Context IRI** | `https://www.w3.org/ns/credentials/v2` | in the v2 context; no second context needed |
| **In force since** | 2025-05-15 | 2025-05-15 |

**The status list document ds cites has been withdrawn.** Checked on 2026-09-06:
`https://w3c-ccg.github.io/vc-status-list-2021/` redirects to
`https://w3c.github.io/vc-status-list-2021/`, which returns **404**. The only artefact
that survives is its JSON-LD context, and even that is now served out of the *Bitstring
Status List* repository:

```
https://w3id.org/vc/status-list/2021/v1
  → https://w3c.github.io/vc-bitstring-status-list/contexts/2021/v1.jsonld   (200)
```

So `build_status_list_credential` publishes a credential against a context that
resolves, describing a format whose normative text a counterparty cannot read. That is
a weaker position than "we are on an old version": there is no version to point at.

---

## 2. The four `statusPurpose` values, verbatim

Bitstring Status List §2.1. The value "is arbitrary" but these four "MUST be used for
their intended purpose".

| Value | Definition (verbatim) | ds |
|---|---|---|
| `revocation` | "Used to cancel the validity of a verifiable credential. This status is not reversible." | **used** — every credential |
| `suspension` | "Used to temporarily prevent the acceptance of a verifiable credential. This status is reversible." | **used for participants only** |
| `refresh` | "Used to signal that an updated verifiable credential is available via the credential's refresh service feature. This status does not invalidate the verifiable credential and is not reversible." | not implemented |
| `message` | "Used to indicate a status message associated with a verifiable credential. The status message descriptions MUST be defined in `credentialSubject.statusMessages`. `credentialSubject.statusSize` MUST be specified when this `statusPurpose` value is used." | not implemented — **and the verifier refuses it**, see §4 |

Two details worth carrying forward:

- **`refresh` does not invalidate anything.** It is a flag saying a newer credential
  exists; the old one stays valid and the flag cannot be cleared. It is not a way to
  retire a superseded credential — that is still `revocation` or `suspension`.
- **The spec names the property two ways.** The entry carries `statusMessage`
  (11 occurrences, and the only one of the two in the v2 JSON-LD context); the
  `message` purpose definition above says `credentialSubject.statusMessages`
  (2 occurrences, defined nowhere in the context). Treat `statusMessage` as the term
  and this as an editorial inconsistency to re-check before relying on it.

---

## 3. Where ds sits, measured

| Property | ds emits | VCDM 2.0 wants |
|---|---|---|
| `@context[0]` | `https://www.w3.org/2018/credentials/v1` (`services/vc.py:9`) | `https://www.w3.org/ns/credentials/v2`, and it MUST be first |
| issuance time | `issuanceDate` (`services/vc.py:70`, `:140`, `:216`) | `validFrom` |
| expiry | `expirationDate` (`services/vc.py:71`, `:141`, `:217`) | `validUntil` |
| status entry type | `StatusList2021Entry` (`services/vc.py:16`) | `BitstringStatusListEntry` |
| status credential type | `StatusList2021Credential` + `credentialSubject.type: StatusList2021` (`services/status_list.py:332`) | `BitstringStatusListCredential` + `credentialSubject.type: BitstringStatusList` |
| second `@context` on the list | `https://w3id.org/vc/status-list/2021/v1` (`services/status_list.py:342`) | none — the v2 context defines the terms |
| `encodedList` | GZIP + **standard base64, padded** (`services/status_list.py:93`) | "Multibase-encoded base64url (with no padding) … of the GZIP-compressed bitstring" — i.e. a leading `u` and the URL alphabet |
| bit order | MSB-first, `7 - (index % 8)` (`services/status_list.py:71`) | ✅ "the first index … is located at the left-most bit" |
| list size | 16 KB, `BITSTRING_SIZE = 16384` (`services/status_list.py:17`) | ✅ "MUST be at least 16KB" |
| entries per credential | participants: two, `revocation` + `suspension`, **mirrored on one index** | ✅ multiple entries are explicitly supported; the spec's own examples use distinct indices, which is a choice not a requirement |
| people's credentials | **`revocation` only**, one entry (`services/vc.py::build_data_subject_credential`) | — |
| `refreshService` | absent | optional |
| presentations | `@context: [2018/credentials/v1]` (`services/presentation.py:160`) | same migration applies |

**Two of the mechanical properties are already right** — bit order and list size — and
they are the two that would be silent if they were wrong. The encoding is the one that
is wrong and would *not* be silent to a strict verifier; see §4 for why ours does not
notice.

---

## 4. What the verifier actually supports — measured from the pinned jar

`gradle.properties` pins `edcVersion=0.16.0`. These facts come from reading
`services/edc-connector/build/libs/connector.jar`, not from release notes:

**Both status types are registered.** `RevocationServiceRegistryExtension` registers
`StatusList2021Entry` *and* `BitstringStatusListEntry`, each with its own service
(`revocation/statuslist2021/StatusList2021RevocationService`,
`revocation/bitstring/BitstringStatusListRevocationService`). The migration target is
supported by the verifier ds already runs, and both types can be in circulation at once.

**An unknown type is a pass, not a failure.** `RevocationServiceRegistryImpl` logs
*"No revocation service registered for type '%s', will not check revocation."* — so a
typo in the entry `type` disables revocation checking silently. This is the single most
important thing to get right in a migration, and the reason a migration must be proved
by *observing a revoked credential get rejected*, not by observing a green suite.

**`statusSize > 1` is refused.** `BitstringStatusListRevocationService` fails with
*"Unsupported statusSize: currently only statusSize = 1 is supported. The VC contained
statusSize = %d"*. The `message` purpose therefore **cannot be verified by EDC 0.16.0**
at all — multi-state-on-one-index is unavailable to this dataspace regardless of what
the Recommendation permits.

**Purpose matching survives the move.** The bitstring service enforces
*"Credential's statusPurpose value must match the statusPurpose of the Bitstring
Credential: '%s' != '%s'"*, the same check the 2021 service states as *"…must match the
status list's purpose"*. `BaseRevocationListService` still fails with *"Credential
status is '%s', status at index %d is '1'"*, so a rejection still names which of
suspended/revoked it found — the property `services/status_list.py` documents as
load-bearing is preserved.

**Our non-conformant encoding would still parse — which is the trap.**
`BitString$Parser` decodes with the standard `Base64.getDecoder()`, and branches on a
multibase header only when it sees one: `'u'` switches to the URL-safe decoder and
strips the prefix; `'z'` is rejected outright with *"The encoded list is using the
Base58-BTC alphabet ('z' multibase header), which is not supported."* So EDC accepts
both the conformant multibase form and ds's plain-base64 form. **Migrating the type
without migrating the encoding would therefore pass every test we can run and still be
non-conformant to any verifier that is not EDC.**

Also present and unexamined: `edc.iam.credential.revocation.mimetype`, defaulting to
`application/json`, which governs how the fetched status-list credential is parsed.
ds serves `application/ld+json`. Nothing suggests a problem — the flows pass — but it
is a knob a format migration should confirm rather than inherit.

---

## 5. `refreshService` — what it is, and what it is not for

VCDM 2.0 §5.4 defines `refreshService`, and the wording bounds it more tightly than the
name suggests:

> "The refresh service is only expected to be used when either the credential has
> expired or the issuer does not publish credential status information."

ds publishes credential status information. So a role change is **not** the case
§5.4 describes, and the `refresh` status purpose is not the mechanism for retiring a
superseded credential — it announces that a newer one exists while leaving the old one
valid and unrevoked (§2).

The spec also warns against the shape that looks most convenient:

> "Placing a `refreshService` property in a verifiable credential so that it is
> available to verifiers can remove control and consent from the holder and allow the
> verifiable credential to be issued directly to the verifier, thereby bypassing the
> holder."

And there is nothing to adopt underneath it. The only type the Recommendation names is
in a non-normative example, `"type": "VerifiableCredentialRefreshService2021"`, and no
specification for it resolves — `w3c-ccg.github.io/vc-refresh-2021/`,
`w3c-ccg.github.io/vc-refresh-service-2021/` and `w3id.org/vc-refresh-service` all
return 404 (checked 2026-09-06). The nearest published protocol is
[1EdTech's VC Refresh Service](https://www.imsglobal.org/spec/vccr/v1p0), which is
1EdTech's, not W3C's.

**Conclusion for planning: `refreshService` is an extension point, not a feature to
turn on.** Adopting it means specifying a ds refresh type. That may still be worth
doing — but it is a design, and it is not what makes a role change expressible.

---

## 6. Is a credential immutable? What the specification actually says

The plan this page supports asserts that a verifiable credential is immutable. The
Recommendation does not use that word, and the honest form of the claim is narrower:

- VCDM 2.0 defines a verifiable credential as "a tamper-evident credential whose
  authorship can be cryptographically verified". Tamper-evident is a property of the
  securing mechanism: an altered credential fails verification.
- **No property, algorithm or section anywhere in VCDM 2.0 updates a credential in
  place.** The only mechanisms for a changed fact are issuing a new credential and
  marking the old one through `credentialStatus`, and §5.4 is explicit that refreshing
  means obtaining a new credential.

So the inference holds — *there is no in-place update, therefore a changed claim is a
reissue* — but it is an inference from the absence of a mechanism plus the presence of
tamper-evidence, not a normative sentence to quote. Anywhere the argument needs to be
airtight, cite the absence and §5.4, not "the spec says credentials are immutable".

---

## 7. The migration, and what it would cost

Everything below is one change, because **the v2 context is `@protected` and does not
define the 1.1 terms.** `issuanceDate`, `expirationDate` and `StatusList2021Entry` are
absent from `https://www.w3.org/ns/credentials/v2` (verified by fetching it). There is
no half-migrated credential that is valid JSON-LD: a document cannot carry the v2
context and 1.1 property names.

Target shape, from the Recommendation's own examples:

```json
{
  "@context": ["https://www.w3.org/ns/credentials/v2", "<ds credentials context>"],
  "type": ["VerifiableCredential", "MembershipCredential"],
  "issuer": "did:web:…",
  "validFrom": "2026-09-06T00:00:00Z",
  "validUntil": "2027-09-06T00:00:00Z",
  "credentialStatus": [
    { "type": "BitstringStatusListEntry", "statusPurpose": "revocation",
      "statusListIndex": "42", "statusListCredential": "…/status/1" },
    { "type": "BitstringStatusListEntry", "statusPurpose": "suspension",
      "statusListIndex": "42", "statusListCredential": "…/status/2" }
  ],
  "credentialSubject": { "id": "did:web:…" }
}
```

| Change | Where | Note |
|---|---|---|
| context IRI | `services/vc.py:9`, `services/status_list.py:341`, `services/presentation.py:160` | drop `https://w3id.org/vc/status-list/2021/v1`; the v2 context covers the entry terms |
| `issuanceDate`/`expirationDate` → `validFrom`/`validUntil` | `services/vc.py` ×3 builders, and the expiry read at `:247` | the read path is a rename too, and it is the one that fails quietly |
| entry and credential `type` | `services/vc.py:16`, `services/status_list.py:345`,`:349` | must match exactly — see the silent-pass finding in §4 |
| `encodedList` encoding | `services/status_list.py:93` | `"u" + base64url-nopad(gzip(bits))`; the decoder must keep accepting the old form for lists already published |
| ds credentials context | `IDENTITY_REGISTRY_CREDENTIALS_CONTEXT_URL` → `/ns/credentials/v1` | our own terms must not collide with `@protected` v2 terms |
| people get a suspension entry | `services/vc.py::build_data_subject_credential` | independent of the format move, and the prerequisite for any reissue flow |

**Credentials already in circulation are the real cost.** Every issued credential names
its status entry type and its list URL; changing the published list's format changes
what those existing credentials resolve to. The migration is either a reissue of the
whole population, or two formats served in parallel — and that decision has not been
taken.

**What must be re-proved rather than assumed**, and the reason §4 was measured: that a
revoked credential is still *rejected*, and that the rejection still distinguishes
suspended from revoked. A green unit suite proves neither, because both halves of the
encoding live in this repository and agree with each other — the failure mode that
already happened once here, when `encode_bitstring` emitted zlib and the tests
round-tripped it perfectly (`services/status_list.py:93`).

---

## 8. Why this page exists now

The plan `a-role-change-is-a-reissue` (agent store) proposes expressing a member's
role change as *suspend the old credential, issue its successor* rather than as a
`PATCH` on a database row, on the grounds that the credential model has carried the
mechanism since the 2025 Recommendations. This page is the reference behind that
argument, and it corrects it in three places: `refresh`/`refreshService` is not the
transition mechanism (§5), the `message` purpose is unavailable because EDC refuses
`statusSize > 1` (§4), and the immutability premise is an inference rather than a quote
(§6). What survives intact is the core of it: **suspension plus reissue is the model's
own answer, it is already implemented for organisations, and extending it to people
needs no format migration at all.**

---

## 9. What is coming

| | |
|---|---|
| **VCDM 2.1** | **W3C Working Draft, 05 September 2026** — <https://www.w3.org/TR/vc-data-model-2.1/> |
| Substantive changes since 2.0 | editorial clarifications, aligned error-condition fields between WG specifications, and clarified requirements around self-asserted credentials (per its own Revision History) |
| Effect on this analysis | **none.** No property ds uses changes, and the context IRI is unchanged. 2.1 is not a reason to delay a 2.0 move, nor a reason to make one |

---

## 10. Re-checking this page

```bash
# The two Recommendations, and whether either has been superseded
curl -sI https://www.w3.org/TR/vc-data-model-2.0/ | head -1
curl -s https://www.w3.org/TR/vc-bitstring-status-list/ | grep -o 'W3C Recommendation[^<]*' | head -1

# The v2 context — confirm the 1.1 terms are still absent and the BSL entry terms present
curl -s https://www.w3.org/ns/credentials/v2 | python3 -c "
import json,sys; c=json.load(sys.stdin)['@context']
print({k: k in c for k in ['BitstringStatusListEntry','issuanceDate','StatusList2021Entry']})"

# What our own pinned verifier supports — the authority for §4
unzip -l services/edc-connector/build/libs/connector.jar | grep -i bitstring
```

For the withdrawn StatusList2021 document, `curl -sIL https://w3c-ccg.github.io/vc-status-list-2021/`
should be re-run before quoting §1: a 404 becoming a 200 would mean the claim has
expired.

---

## 11. References

- VCDM 2.0 — <https://www.w3.org/TR/vc-data-model-2.0/> (Recommendation, 15 May 2025)
- VCDM 2.0 §5.4 Refreshing — <https://www.w3.org/TR/vc-data-model-2.0/#refreshing>
- VCDM 2.1 — <https://www.w3.org/TR/vc-data-model-2.1/> (Working Draft, 05 September 2026)
- Bitstring Status List v1.0 — <https://www.w3.org/TR/vc-bitstring-status-list/> (Recommendation, 15 May 2025)
- The v2 JSON-LD context — <https://www.w3.org/ns/credentials/v2>
- StatusList2021 context (all that remains) — <https://w3id.org/vc/status-list/2021/v1>
- 1EdTech VC Refresh Service — <https://www.imsglobal.org/spec/vccr/v1p0>
- The issuing code — `services/identity-registry/src/identity_registry/services/vc.py`,
  `…/services/status_list.py`, `…/services/presentation.py`
- What the rulebook claims — [Participation and trust](../rulebook/participation.md) §3,
  [Data exchange](../rulebook/data-exchange.md) §5
- The service — [identity-registry](../services/identity-registry.md)
