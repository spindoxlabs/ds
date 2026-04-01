# 03 — Access and Usage Policies

> **Building block type**: Participant Agent + Facilitating  
> **Depends on**: 01-trust-framework, 02-identity-attestation  
> **Required by**: 06-data-exchange, 07-provenance-traceability, 09-data-sovereignty

---

## Purpose

This building block is the core mechanism for **data sovereignty** in a data space. It provides the standardised language, negotiation protocol, and enforcement architecture to make data provider policies machine-readable, interoperable, and actually enforceable — not just contractual declarations.

Individual data providers or consumers are increasingly determining their own access and usage policies, indicating who can access which data and under what conditions. This building block ensures those policies can be expressed in a common language that every connector in the data space understands.

---

## Access Policy vs Usage Policy — A Critical Distinction

These two layers operate at different moments in a data transaction and serve fundamentally different purposes.

| | **Access Policy** | **Usage Policy** |
|---|---|---|
| **Question answered** | Who may receive the data? | What may the receiver do with it? |
| **When enforced** | Before transfer (at provider's connector) | After transfer (at consumer's connector) |
| **Result** | ALLOW or DENY | Permitted / Prohibited / Obligation |
| **Example** | Only GDPR-certified organisations in sector X | Use for analytics only; delete after 30 days; attribute the source |
| **Travels with data?** | No — gate at source | Yes — obligations are attached to the data product |

Both are expressed in ODRL but enforced at different points in the data flow.

---

## ODRL — The Policy Language

### Core Model

The W3C Open Digital Rights Language (ODRL) is the Blueprint's recommended standard for expressing both policy types. An ODRL policy is a JSON-LD document with the following structure:

```json
{
  "@context": "http://www.w3.org/ns/odrl.jsonld",
  "@type": "odrl:Offer",
  "@id": "https://provider.eu/policies/energy-data-v1",
  "odrl:permission": [{
    "odrl:target": "https://provider.eu/datasets/grid-measurements-2025",
    "odrl:action": { "@id": "odrl:use" },
    "odrl:assignee": { "@id": "odrl:Group", "odrl:source": "https://dataspace.eu/members/certified-analytics" },
    "odrl:constraint": [{
      "odrl:leftOperand": { "@id": "odrl:dateTime" },
      "odrl:operator": { "@id": "odrl:lt" },
      "odrl:rightOperand": { "@value": "2026-12-31T23:59:59Z", "@type": "xsd:dateTime" }
    }]
  }],
  "odrl:prohibition": [{
    "odrl:target": "https://provider.eu/datasets/grid-measurements-2025",
    "odrl:action": { "@id": "odrl:distribute" }
  }],
  "odrl:obligation": [{
    "odrl:action": { "@id": "odrl:delete" },
    "odrl:constraint": [{
      "odrl:leftOperand": { "@id": "odrl:elapsedTime" },
      "odrl:operator": { "@id": "odrl:eq" },
      "odrl:rightOperand": { "@value": "P30D", "@type": "xsd:duration" }
    }]
  }]
}
```

### ODRL Rule Types

| Rule type | ODRL class | Description |
|---|---|---|
| **Permission** | `odrl:Permission` | Explicitly allowed actions for the assignee |
| **Prohibition** | `odrl:Prohibition` | Explicitly forbidden actions |
| **Duty / Obligation** | `odrl:Duty` | Required actions the consumer must perform |

### ODRL Actions (most relevant for data spaces)

| Action | URI | Meaning |
|---|---|---|
| use | `odrl:use` | General use of the data |
| read | `odrl:read` | Read-only access |
| distribute | `odrl:distribute` | Share with third parties |
| modify | `odrl:modify` | Transform or derive from the data |
| aggregate | `odrl:aggregate` | Combine with other data |
| attribute | `odrl:attribute` | Must credit the source |
| delete | `odrl:delete` | Must delete after use period |

### ODRL Constraint Operators

Constraints limit when or how a permission applies:

```
odrl:eq        — equals
odrl:gt / lt   — greater/less than (for dates, counts)
odrl:isA       — type membership check
odrl:isAllOf   — all conditions must hold
odrl:isAnyOf   — any condition holds
odrl:isNoneOf  — none of the listed values
```

---

## GDPR and DPV — The Privacy Policy Extension

For data spaces handling personal data, ODRL alone is insufficient. The **W3C Data Privacy Vocabulary (DPV)** extends ODRL to express GDPR-specific concepts:

```json
{
  "@context": [
    "http://www.w3.org/ns/odrl.jsonld",
    "https://w3id.org/dpv#"
  ],
  "odrl:permission": [{
    "odrl:action": { "@id": "odrl:use" },
    "odrl:constraint": [{
      "odrl:leftOperand": { "@id": "dpv:Purpose" },
      "odrl:operator": { "@id": "odrl:isA" },
      "odrl:rightOperand": { "@id": "dpv:ResearchAndDevelopment" }
    }]
  }],
  "dpv:hasLegalBasis": { "@id": "dpv:Consent" },
  "dpv:hasDataSubjectRight": [
    { "@id": "dpv:RightToErasure" },
    { "@id": "dpv:RightToAccess" }
  ]
}
```

### Key DPV concepts for data space policies:

| DPV concept | Role |
|---|---|
| `dpv:Purpose` | Why the data is being processed (must be specified) |
| `dpv:LegalBasis` | GDPR Art. 6 legal basis (consent, contract, legitimate interest, etc.) |
| `dpv:DataCategory` | Type of personal data involved |
| `dpv:hasRight` | Data subject rights that the consumer must support |
| `dpv:Consent` | Consent record linked to the data subject |

---

## Policy Negotiation via the Dataspace Protocol (DSP)

Policies are not static — they are **negotiated at runtime** between provider and consumer connectors:

### Negotiation sequence:

```
1. CATALOGUE QUERY
   Consumer → GET /catalogue
   Provider → returns DCAT dataset descriptions with ODRL Offers embedded

2. CONTRACT REQUEST
   Consumer → POST /negotiations
   Body: { "offer": "<ODRL offer ID>", "agreement": "accepted" }
         or counter-offer with modified terms

3. NEGOTIATION (optional)
   Provider evaluates counter-offer
   Provider → POST /negotiations/{id}/events (ODRL counter-offer or acceptance)

4. CONTRACT AGREEMENT
   Both sides sign the ODRL Agreement
   Agreement stored by both connectors
   Data transfer now authorised

5. DATA TRANSFER
   Consumer → POST /transfers
   Transfer starts under the terms of the agreement
```

### ODRL Policy Types in DSP context:

| Type | Purpose |
|---|---|
| `odrl:Set` | Generic policy set (used in catalogues) |
| `odrl:Offer` | Provider's offer to any eligible consumer |
| `odrl:Agreement` | Binding agreement between specific provider and consumer |

---

## Policy Enforcement Architecture (XACML Pattern)

The enforcement infrastructure follows the standard XACML four-component architecture:

```
┌──────────────────────────────────────────────────────┐
│  PAP — Policy Administration Point                   │
│  Where provider authors and stores policies          │
│  (ODRL policies stored as JSON-LD in catalogue)      │
└────────────────────┬─────────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │  PIP — Policy           │
        │  Information Point      │
        │  Provides runtime       │
        │  context:               │
        │  - Consumer's VCs       │
        │  - Consent status       │
        │  - Current timestamp    │
        │  - Geographic location  │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │  PDP — Policy Decision  │
        │  Point                  │
        │  Evaluates ODRL rule    │
        │  against PIP context    │
        │  Returns:               │
        │  ALLOW / DENY /         │
        │  OBLIGATIONS            │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │  PEP — Policy           │
        │  Enforcement Point      │
        │  (the connector)        │
        │  Acts on PDP decision:  │
        │  - Permits/blocks data  │
        │  - Records the event    │
        │  - Triggers obligations │
        └─────────────────────────┘
```

**Important**: The PEP exists on **both sides**:
- Provider-side PEP: gates the data transfer before it leaves the source
- Consumer-side PEP: enforces post-transfer usage obligations (deletion, attribution, etc.)

---

## Consent Management

When personal data is involved, the data space must accommodate a **cross-organisational consent management capability**:

```
Data subject grants consent
        ↓
Consent service issues Consent VC (linked to data subject DID and purpose)
        ↓
Consumer's access request includes Consent VC reference
        ↓
PIP retrieves consent status from consent service
        ↓
PDP evaluates: consent valid? purpose matches? legal basis documented?
        ↓
PEP allows/denies data transfer
```

### Consent management requirements:

- Consent must be **purpose-specific** (GDPR Art. 5(b) purpose limitation)
- Consent must be **freely given, specific, informed, and unambiguous** (GDPR Art. 7)
- Consent withdrawal must propagate to all active data sharing agreements
- Cross-organisational consent (data shared between multiple providers) requires a shared consent registry

---

## Implementation Checklist

- [ ] Define ODRL policy templates for your data space's common use cases
- [ ] Implement ODRL Offer authoring tool for data providers (low-code interface recommended)
- [ ] Embed ODRL Offers in DCAT catalogue entries as JSON-LD
- [ ] Implement DSP contract negotiation endpoint (`/negotiations`)
- [ ] Implement ODRL Agreement signing and storage (both provider and consumer side)
- [ ] Implement PAP (policy storage and management)
- [ ] Implement PIP (context provider: VC attributes, consent status, timestamp)
- [ ] Implement PDP (ODRL evaluation engine — reference: ODRL Evaluator)
- [ ] Implement provider-side PEP in connector (gates data transfer)
- [ ] Implement consumer-side PEP in connector (enforces usage obligations)
- [ ] For personal data: integrate DPV-annotated policies
- [ ] For personal data: implement consent management service with VC issuance
- [ ] Log every policy decision to provenance store (see 07-provenance-traceability.md)

---

## Common Pitfalls

**No consumer-side enforcement**: Access policies are widely implemented; usage obligation enforcement on the consumer side is often skipped. This is a data sovereignty gap — usage obligations like deletion and attribution have no technical guarantee.

**ODRL without DPV for personal data**: An ODRL policy without DPV annotations cannot express GDPR legal bases. In regulated domains this creates compliance risk.

**Hardcoded policies**: Policies should be authored and managed in a PAP, not hardcoded in connector configuration. Policies need to be updatable without redeployment.

**Policy version mismatch**: When a provider updates a policy, existing agreements must remain valid under their original terms. Implement policy versioning and reference immutable policy URLs in agreements.

---

## References

- [W3C ODRL Information Model](https://www.w3.org/TR/odrl-model/)
- [W3C ODRL Vocabulary](https://www.w3.org/TR/odrl-vocab/)
- [W3C Data Privacy Vocabulary (DPV)](https://w3id.org/dpv)
- [IDSA Dataspace Protocol](https://docs.internationaldataspaces.org/ids-knowledgebase/dataspace-protocol)
- [XACML 3.0 Standard](https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.html)
- [ODRL Evaluator (reference implementation)](https://github.com/nicokratky/odrl-evaluator)
