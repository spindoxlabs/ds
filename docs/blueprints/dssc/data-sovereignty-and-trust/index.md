# Data Sovereignty and Trust

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Sovereignty and Trust

One of the three categories of technical building blocks. Its three building blocks
address *who* a participant is, *why* they should be believed, and *what* they are then
permitted to do — the chain a data space depends on before any exchange is authorised.

| Building block | Requirement IDs | What it covers |
|---|---|---|
| **[Identity & Attestation Management](identity-and-attestation-management.md)** | `DSSC-IAM-01`–`33` | Identities of organisations, individuals and services; attestations; credential exchange protocols. |
| **[Trust Framework](trust-framework.md)** | `DSSC-TRF-01`–`47` | Compliance criteria, trust services, accredited sources of trust, and the reuse or extension of existing frameworks. |
| **[Access & Usage Policies Enforcement](access-and-usage-policies-enforcement.md)** | `DSSC-AUP-01`–`91` | Policy expression in ODRL, and the PAP / PIP / PDP / PEP administration, decision and enforcement chain. |

Requirement IDs are a local index for benchmarking. The source does not number its
requirements.

## Notes on this category

**Credential-exchange protocol naming is unstable upstream.** Four spellings appear for
what is apparently one protocol family — `OIDC4VC`, `OID4VC`, `OID4VCi` and
`OpenID4VCI` — and the source never states that they are the same thing. Each page
preserves the spelling used at each occurrence rather than normalising.

**The Trust Framework is defined twice, incompatibly**, within its own page: once in the
body and once in that page's glossary, with different constituents. Both are recorded.

**Access & Usage Policies Enforcement describes its enforcement components without
obliging them.** The source names PEP, PDP, PAP, PIP, Context Handler and Data
Sink-Source but never says a participant must or should deploy them, so those rows are
`informative`. That is the single largest force judgement in this category.
