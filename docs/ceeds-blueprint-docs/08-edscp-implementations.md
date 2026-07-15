# 08 — EDSCP Implementations

## Overview

The Energy Data Space Cluster Projects (EDSCP) — Data Cellar, SYNERGIES, OMEGA-X, ENERSHARE, and others — have implemented pilot solutions providing practical lessons for the CEEDS.

## Access Control and Security

### Common Approaches Across Projects
- All projects use certificates or similar mechanisms for secure communication
- Decentralised Identifiers (DID) and Verifiable Credentials (VC) are commonly used
- Implementation based on established standards: W3C, OpenID, SAML, OAuth

### Identity Management Implementations

| Project | Approach | Details |
|---|---|---|
| **OMEGA-X** | IDSA + Gaia-X trust frameworks | CA + DAPS (Dynamic Attribute Provisioning Service); Marketplace Federator manages registrations |
| **ENERSHARE** | IDSA + Gaia-X, evolving to DSP | Keycloak for user identities (OpenID, SAML, OAuth); moving to DSP for connector interoperability; participant wallet using DID, OID4VP, OID4VCI |
| **Data Cellar** | Gaia-X framework + SSI | W3C VC + DID; dedicated server for organisational identities; Gaia-X trust anchors for credential signing |
| **SYNERGIES** | Centralised IAM service | Security, authentication & authorisation service across data space and marketplaces; SSO functionality |

### Key Observations
- OMEGA-X and ENERSHARE focus on IDSA/Gaia-X compatibility for decentralised identity
- Both implement CA + DAPS combination for the CEEDS onboarding system use case
- Data Cellar uses Self-Sovereign Identity (SSI) principles
- ENERSHARE is transitioning from Keycloak/OIDC to DSP-based participant wallets

## Governance Rules Implementation

### Common Principles
- Fully preserving data owner rights
- Facilitating assurances for both consumer and producer
- Legal and ethical considerations in governance design
- Ethics-by-design methodology

### Two Guiding Principles
1. Enable data use/access while ensuring ethical, legal, and financial compliance for all stakeholders; protect data autonomy, sovereignty, human dignity, and fundamental rights
2. Legal agreements safeguarding governance model; compensation mechanisms for data rights violations

### Governance Authority
- Proposed approach: general assembly of members supported by management board
- Federated model for cross-data space governance
- Role and functions still under development across projects

## Data Sharing Agreements

### Onboarding Process
1. Application and evaluation by governance authority
2. Applicant declares intended use
3. Authority checks: legal/ethical standards compliance, technical capabilities
4. Penalties and consequences for non-compliance outlined
5. Secret, unique API key generated for participant
6. Terms and conditions define: admissible stakeholder types, roles, licensing processes, data sharing agreement mechanisms

### Offboarding Process
1. Notice of termination (by participant or governance authority)
2. Data retrieval and secure deletion (GDPR compliance)
3. Revocation of access + system audit

## Data Value Creation

### Publication and Discovery
- Implemented via dedicated marketplaces
- Gaia-X specifications as reference (OMEGA-X, ENERSHARE, Data Cellar)
- **Marketplace Federator**: manages user registrations, approvals, offering descriptions
- Federated catalogue syncs with multiple provider catalogues across data spaces
- SHACL checks for syntactic/semantic verification of self-descriptions against Gaia-X schemas
- DID and VC/VP cryptographic verification

### Marketplace Functionality
1. Data search
2. Data request (with duration and expected use specifications)
3. Data contracting (predefined terms + free-text terms + reimbursement details)
4. Data contracting payment

### Value-Added Services

| Project | Services |
|---|---|
| **SYNERGIES** | Data services (monitoring, certification, observability), generic services (privacy preservation, encryption, access policy, auth), AI services, application services |
| **ENERSHARE** | Barter monetisation/incentives module, data transformation service (syntactic → semantic), federated learning platform, multi-energy flexibility assessment |
| **Data Cellar** | Comprehensive suite: participation management, user training, engagement maximisation |

### Compensation Mechanisms

| Model | Description | Projects |
|---|---|---|
| **Data by tokens** | Cryptographic token payment (data-space-specific) | Data Cellar, SYNERGIES |
| **Data by data** | Barter exchange based on intrinsic data value | ENERSHARE, SYNERGIES |
| **Data by currency** | FIAT currency payment via marketplace | ENERSHARE only |

### Smart Contract Implementations

**SYNERGIES**: Contract Settlement Engine (NodeJS/NestJS backend, Ethereum blockchain, VueJS/TailwindCSS frontend)
- Settlement of barter agreements
- Settlement of monetary transactions
- Active contract monitoring and compliance alerts
- Automatic termination for breached terms

**Data Cellar**: Blockchain-based with Solidity smart contracts
- ERC721 (non-fungible tokens) for data asset digitisation
- ERC20 (fungible tokens) for platform currency
- License types: "period" (unlimited use within timeframe) or "usage" (consumed per use)
- Balancer component for token-license exchange

## Key Lessons for Our Implementation

1. Identity management is converging on DID + VC + OIDC4VP, but intermediate solutions (Keycloak, DAPS) are still in use
2. Gaia-X trust framework and IDSA specifications are the practical reference implementations
3. Marketplace functionality is essential for value creation (not just technical data exchange)
4. Compensation mechanisms vary significantly — token-based and barter models are energy-specific innovations
5. Smart contract integration for contract settlement is emerging but not yet standardised
6. Federated catalogue with Gaia-X Marketplace Federator pattern enables cross-data-space discovery
