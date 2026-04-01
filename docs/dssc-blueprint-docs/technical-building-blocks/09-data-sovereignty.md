# 09 — Data Sovereignty and Access Control

> **Building block type**: Participant Agent  
> **Depends on**: 01-trust-framework, 02-identity-attestation, 03-access-usage-policies  
> **Required by**: 06-data-exchange, 07-provenance-traceability

---

## Purpose

Data sovereignty is the defining property that distinguishes a data space from a centralised data platform. In a data space, **data never leaves the control of its owner** unless the owner explicitly authorises it under defined conditions. The data sovereignty building block defines the technical implementation of that control — specifically the connector architecture and the enforcement mechanisms that translate policies into actual access decisions.

This building block operationalises the principle that data owners maintain full control over who accesses their data, under what conditions, and for what purposes — even after the data has been transferred.

---

## What Data Sovereignty Means Technically

| Principle | Technical implementation |
|---|---|
| No central data copy | Data stays at source; only accessed/transferred on explicit authorisation |
| Provider-controlled access | Every access request passes through provider's Policy Enforcement Point |
| Usage control | Obligations travel with data; consumer-side PEP enforces them |
| Auditability | Every access event logged with authenticated identities |
| Revocability | Access can be withdrawn by revoking credentials or terminating agreements |
| Portability | Data is accessible without being locked into a specific platform |

---

## The Connector as Sovereignty Enforcer

The connector is the technical unit that enforces data sovereignty. It is the **only legitimate gateway** through which data leaves a participant's environment.

### Provider connector responsibilities:

```
Incoming transfer request
        ↓
1. Authenticate the requesting connector (mTLS / DPoP)
        ↓
2. Verify consumer's Verifiable Credentials (membership, role, compliance)
        ↓
3. Check agreement exists and is valid (not expired, not terminated)
        ↓
4. Call PDP with: request + consumer attributes + current context
        ↓
5. If ALLOW: initiate data transfer on data plane
   If DENY: return 403 with denial reason
   If OBLIGATIONS: permit transfer + record obligations in PROV-O
        ↓
6. Log transfer event (timestamp, consumer DID, data product, bytes, agreement ID)
```

### Consumer connector responsibilities:

```
Received data
        ↓
1. Record receipt event in provenance store
        ↓
2. Extract usage obligations from ODRL Agreement
        ↓
3. Schedule obligation fulfilment (deletion timers, attribution requirements)
        ↓
4. Enforce obligations via consumer-side PEP
        ↓
5. Log obligation fulfilment events
```

---

## Attribute-Based Access Control (ABAC)

The Blueprint's policy model is inherently attribute-based. Access decisions are based on **attributes of the requester**, not a static list of permitted entities.

### ABAC policy example

```
ALLOW access to dataset:grid-frequency
  IF  consumer.membership == "data-space-energy.eu"
  AND consumer.role == "DataConsumer"
  AND consumer.compliance contains "GDPR-DPO"
  AND request.purpose == "analytics"
  AND request.timestamp < 2026-01-01
```

This is more powerful than role-based or identity-based access control because:
- New participants automatically gain access if they satisfy the attribute conditions (no manual allowlist management)
- Policies are composable and maintainable without modifying infrastructure
- Conditions can reference real-time context (time, location, consent status)

### Attribute sources for ABAC:

| Attribute | Source |
|---|---|
| Membership | Verifiable Credential from governance authority |
| Role | Verifiable Credential from governance authority |
| Compliance certifications | Verifiable Credential from certification body |
| Consent | Consent VC from consent management service |
| Request purpose | Declared in ContractRequest (ODRL constraint) |
| Timestamp | System clock (verified by TLS certificate timestamp) |
| IP / network | Optional — network-level constraint |

---

## Data Plane Sovereignty Mechanisms

Beyond the control plane (DSP negotiation), the data plane must also enforce sovereignty:

### Token-based data plane access

```
1. Control plane (DSP) completes contract agreement
2. Control plane issues a short-lived transfer token (JWT)
   Token claims: { consumer_did, agreement_id, data_product_id, expiry, allowed_operations }
3. Consumer presents token to data plane endpoint
4. Data plane validates token, checks expiry and scope
5. Data plane serves data within token bounds
```

This prevents token reuse, scope creep, and ensures data plane access is always tied to a valid control plane agreement.

### Data minimisation enforcement

```python
# Example: field-level access control based on policy
class DataMinimisationFilter:
    def __init__(self, agreement: OdrlAgreement):
        self.allowed_fields = agreement.get_permitted_fields()
    
    def filter(self, record: dict) -> dict:
        return {k: v for k, v in record.items() 
                if k in self.allowed_fields}
```

The ODRL policy can specify which fields of a dataset the consumer may receive, not just whether they may access the dataset at all.

### Algorithm-to-data (A2D) for maximum sovereignty

When raw data transfer is prohibited by the usage policy, the provider runs the consumer's algorithm locally:

```
Consumer sends: algorithm container (Docker image) + parameters
Provider: 
  1. Validates algorithm (sandboxed execution environment)
  2. Runs algorithm against local data
  3. Returns only the computation result
  4. Data never leaves the provider's environment
```

This pattern is used in privacy-sensitive scenarios (health data, financial data, personal data) where even anonymised data may carry re-identification risk.

---

## Connector Deployment Patterns

### Pattern 1: Edge connector (standard)

```
Participant infrastructure
├── Business systems (ERP, SCADA, database)
├── Data adapter (extracts and formats data)
└── Connector (enforces sovereignty)
        ↓ DSP
Remote participant's connector
```

Best for: organisations with stable data sources and IT infrastructure.

### Pattern 2: Cloud-hosted connector

```
Participant's cloud tenant
├── Data lake / object storage
└── Managed connector service
        ↓ DSP
Remote participant's connector
```

Best for: cloud-native organisations; allows leveraging managed connector services.

### Pattern 3: Connector as a Service (CaaS)

```
Participant (data owner)
└── Data stored at participant
        ↓ Authorisation only
Third-party CaaS provider
└── Hosts connector on behalf of participant
└── Data flows through CaaS connector
        ↓ DSP
Remote participant's connector
```

Note: in this pattern the participant must fully trust the CaaS provider, since data flows through it. CaaS providers operating under the EU Data Governance Act must register as data intermediation service providers.

---

## Key Sovereignty Features to Validate

Before going live, verify these sovereignty properties:

| Test | Pass condition |
|---|---|
| Unauthorised access attempt | Connector returns 403 without data leakage |
| Expired agreement access | Connector refuses transfer, returns 401 |
| Revoked credential access | Connector refuses transfer after revocation check |
| Policy condition not met | PDP returns DENY; PEP blocks transfer |
| Usage obligation enforcement | Consumer connector deletes data after obligation period |
| Data minimisation | Consumer receives only permitted fields, not full record |
| Token scope enforcement | Token scoped to one dataset cannot access another |

---

## Implementation Checklist

- [ ] Deploy connector with TLS 1.3 and mTLS on all endpoints
- [ ] Implement ABAC policy evaluation (PDP) with VC attribute resolution
- [ ] Implement short-lived transfer token issuance (JWT, signed by connector)
- [ ] Implement token validation on data plane endpoints
- [ ] Implement field-level access control / data minimisation filter
- [ ] Implement consumer-side PEP with obligation scheduler
- [ ] Implement usage obligation fulfilment logging
- [ ] Implement algorithm-to-data execution environment (if required by use case)
- [ ] Run sovereignty validation test suite before go-live
- [ ] Implement connector self-description with supported protocols and security profile
- [ ] Publish connector endpoint in DCAT catalogue and participant registry

---

## References

- [IDSA Reference Architecture — Data Sovereignty](https://docs.internationaldataspaces.org/ids-ram-4/)
- [Eclipse EDC — Connector implementation](https://github.com/eclipse-edc/Connector)
- [EU Data Governance Act — Data Intermediaries](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R0868)
- [XACML ABAC Profile](https://docs.oasis-open.org/xacml/xacml-abac/v1.0/xacml-abac-v1.0.html)
- [W3C ODRL — Usage Control](https://www.w3.org/TR/odrl-model/#usage-control)
