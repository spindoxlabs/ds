# 01 — Trust Framework

> **Building block type**: Facilitating (federation-level) + Participant Agent  
> **Depends on**: 00-foundational-standards  
> **Required by**: All other building blocks — this is the root of trust

---

## Purpose

The Trust Framework is the foundational layer that answers one core question before any data exchange can happen: **how does a participant know that the party it is about to share data with is who they claim to be, and that they are legitimately admitted to this data space?**

Without a trust framework, no policy or data exchange mechanism can function — you cannot enforce rules on an unknown or unverified identity. Trust enables participants to make informed decisions about how, when, and with whom to share data.

---

## Position in the Rulebook

The trust framework is not a standalone product. It is a specification **embedded in the data space's rulebook** by the governance authority. The rulebook specifies:

- Which trust anchors are accepted (which CAs and QTSPs are recognised)
- Which credential formats are valid
- Which verification services are mandatory vs optional
- Which certification schemes are required for specific participant roles
- What the onboarding process entails and what evidence must be provided

---

## Core Components

### 1. Trust Anchor

The root of the trust chain. Can be:

| Type | Description | Regulatory basis |
|---|---|---|
| **Certificate Authority (CA)** | Issues X.509 certificates to verified participants | Standard PKI |
| **eIDAS Qualified Trust Service Provider (QTSP)** | EU-regulated issuer of qualified certificates and signatures | eIDAS 2.0 |
| **Data space credential issuer** | The governance authority's own VC issuance service | Defined in rulebook |

A data space may accept multiple trust anchors (e.g., multiple QTSPs operating in different EU member states) as long as all are listed in the rulebook's trust anchor registry.

### 2. Participant Onboarding

The process through which a new organisation is verified and issued credentials:

```
Applicant submits:
  → Legal registration documents (business register extract)
  → Regulatory compliance evidence (sector certifications, DPO appointment)
  → Technical capability proof (connector endpoint, self-description)
  → Signed acceptance of rulebook terms

Trust anchor verifies:
  → Legal entity identity (against authoritative registry)
  → Compliance status (against certification scheme)
  → Technical readiness (connector health check)

Trust anchor issues:
  → Membership VC ("this DID is an admitted participant of data space X")
  → Role VC ("this participant is a data provider / consumer / service provider")
  → Compliance VC ("this participant has achieved certification Y")
```

### 3. Verifiable Credentials (Trust Assertions)

Following issuance, participants hold credentials in a VC wallet. These credentials assert:

- **Membership**: confirmed participant in the data space
- **Role**: data provider, data consumer, service provider
- **Compliance**: GDPR compliance, sector certification, ISO 27001
- **Capability**: supported protocols, data formats, processing categories

All credentials follow W3C VC Data Model 2.0 and are signed with the trust anchor's private key.

### 4. Credential Presentation and Verification

At the moment of a data transaction, the consuming party presents credentials to the providing party:

```
Consumer connector → presents Verifiable Presentation (VP) via OIDC4VP
Provider connector → resolves issuer DID → fetches DID Document → verifies signature
                  → checks revocation status (W3C Status List 2021)
                  → confirms membership and role
                  → passes verified identity to Policy Decision Point
```

This verification is **peer-to-peer** — no central broker needs to be online during the exchange.

### 5. Revocation Management

Active credential management is as important as issuance:

| Event | Required action |
|---|---|
| Participant offboarding | Revoke all membership and role credentials immediately |
| Compliance certification lapse | Revoke compliance VC; restrict data access accordingly |
| Credential expiry | Participant must renew before expiry; connector should warn in advance |
| Security incident | Emergency revocation procedure defined in rulebook |

**Recommended revocation mechanism**: W3C Status List 2021 — a bitfield published by the issuer at a known URL. Verifiers check the relevant bit at presentation time. This is more scalable than OCSP for high-volume data space environments.

---

## Relationship to eIDAS 2.0

For data spaces operating in the EU, trust services should be provided by or interoperable with eIDAS-recognised QTSPs. Key implications:

- **Legal entity identity**: can be anchored to eIDAS qualified certificates for legal persons
- **EU Digital Identity Wallet (EUDIW)**: the eIDAS 2.0 EUDIW provides a standardised VC wallet for natural persons and legal entities — data spaces should plan for EUDIW compatibility
- **Cross-border recognition**: QTSPs are recognised across all EU member states, eliminating the need for bilateral trust agreements between national data spaces

---

## iSHARE as a Reference Implementation

iSHARE is the most mature open trust framework implementation aligned with the DSSC Blueprint. Key features relevant to implementation:

- Federated and decentralised: parties join via trusted onboarding without pre-exchanging authentication keys
- Uses REST, OAuth 2.0, OpenID Connect 1.0, PKI, and digital certificates
- Defines roles: Service Consumer, Service Provider, Identity Provider, Identity Broker, Authorisation Registry
- Publicly available specification and open-source reference implementations

---

## Implementation Checklist

- [ ] Select and register accepted trust anchors in rulebook
- [ ] Implement CA or QTSP integration for initial credential issuance
- [ ] Deploy W3C VC issuance service (supports VC Data Model 2.0, JSON-LD)
- [ ] Implement VC wallet for each participant's connector
- [ ] Implement OIDC4VP presentation endpoint on each connector
- [ ] Implement signature verification against trust anchor DID Documents
- [ ] Implement W3C Status List 2021 revocation check on every credential presentation
- [ ] Define credential schema registry (what fields each VC type must contain)
- [ ] Define onboarding workflow and required evidence per participant role
- [ ] Define offboarding procedure with automatic revocation trigger
- [ ] Test credential issuance, presentation, and revocation end-to-end before go-live

---

## Common Pitfalls

**Skipping revocation checks**: Verifying a credential signature without checking its revocation status is a security gap. Always check the status list on every presentation, not just at issuance time.

**Single trust anchor lock-in**: If the data space has only one trust anchor and it becomes unavailable, no new participants can onboard. Design for trust anchor redundancy from the start.

**No VC schema governance**: Without a defined schema for each credential type, different issuers produce incompatible credentials. Publish and version-control credential schemas in the vocabulary hub.

**Ignoring eIDAS QTSP for regulated domains**: For health, energy, and financial data spaces, using non-eIDAS-qualified trust services may create regulatory gaps. Assess early.

---

## References

- [W3C Verifiable Credentials 2.0](https://www.w3.org/TR/vc-data-model-2.0/)
- [W3C DID Core 1.0](https://www.w3.org/TR/did-core/)
- [W3C Status List 2021](https://www.w3.org/community/reports/credentials/CG-FINAL-vc-status-list-2021-20230102/)
- [OIDC for Verifiable Presentations](https://openid.net/specs/openid-4-verifiable-presentations-1_0.html)
- [eIDAS 2.0 Regulation](https://digital-strategy.ec.europa.eu/en/policies/eidas-regulation)
- [iSHARE Trust Framework](https://ishareworks.atlassian.net/wiki/spaces/IS/overview)
- [DSSC Toolbox — Trust Services](https://blueprint.dssc.eu/?pane=tools)
