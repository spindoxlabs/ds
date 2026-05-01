# Data Exchange Flow

This document describes the end-to-end consumer-pull data exchange flow: from catalog discovery through contract negotiation to EDR-gated data transfer with consent filtering.

---

## Overview

The dataspace implements the IDSA Dataspace Protocol (DSP) consumer-pull pattern:

1. **Discover** — consumer browses the federated catalog
2. **Negotiate** — consumer and provider agree on a contract under ODRL terms
3. **Transfer** — provider issues an Endpoint Data Reference (EDR) to the consumer
4. **Query** — consumer uses the EDR token to access data, with consent filtering applied at query time

---

## Step 1: Catalog discovery

```
Portal                    ds-connector              EDC Consumer        EDC Provider
  │                            │                         │                    │
  │  GET /consumer/catalog     │                         │                    │
  ├───────────────────────────→│                         │                    │
  │                            │  POST /management/v3/   │                    │
  │                            │  catalog/request         │                    │
  │                            ├────────────────────────→│                    │
  │                            │                         │  DSP Catalog Req   │
  │                            │                         ├───────────────────→│
  │                            │                         │  DCAT-AP response  │
  │                            │                         │←───────────────────┤
  │                            │  DCAT catalog           │                    │
  │                            │←────────────────────────┤                    │
  │  DCAT datasets + policies  │                         │                    │
  │←───────────────────────────┤                         │                    │
```

The catalog includes ODRL offers attached to each dataset. The portal renders these as human-readable policy summaries via `odrl.ts`.

Alternatively, `ds-federated-catalog` provides a pre-aggregated view that crawls all participant catalogs periodically.

---

## Step 2: Contract negotiation

```
Portal                    ds-connector              EDC Consumer        EDC Provider
  │                            │                         │                    │
  │  POST /consumer/negotiate  │                         │                    │
  │  { asset_id, provider_id } │                         │                    │
  ├───────────────────────────→│                         │                    │
  │                            │  POST /management/v3/   │                    │
  │                            │  contractnegotiations   │                    │
  │  { negotiation_id }        │                         │                    │
  │←───────────────────────────┤                         │                    │
  │                            │                         │  DSP ContractReq   │
  │                            │                         ├───────────────────→│
  │                            │                         │                    │
  │                            │                    DCP identity verification │
  │                            │                    (STS token + VP + VC)     │
  │                            │                    ODRL constraint eval      │
  │                            │                    (AccessScope, Consent)    │
  │                            │                         │                    │
  │                            │                         │  Agreement         │
  │                            │                         │←───────────────────┤
  │                            │                         │                    │
  │  GET /consumer/            │                         │                    │
  │  negotiations/{id}         │                         │                    │
  ├───────────────────────────→│                         │                    │
  │  { state: "FINALIZED" }    │  poll negotiation state │                    │
  │←───────────────────────────┤                         │                    │
```

Negotiation is asynchronous. The portal polls the negotiation state via `StatusPoller.svelte` until it reaches `FINALIZED` (success) or `TERMINATED` (failure).

---

## Step 3: Data transfer

```
Portal                    ds-connector              EDC Consumer        EDC Provider
  │                            │                         │                    │
  │  POST /consumer/transfer   │                         │                    │
  │  { agreement_id }          │                         │                    │
  ├───────────────────────────→│                         │                    │
  │                            │  POST /management/v3/   │                    │
  │                            │  transferprocesses      │                    │
  │  { transfer_id }           │                         │                    │
  │←───────────────────────────┤                         │                    │
  │                            │                         │  DSP TransferReq   │
  │                            │                         ├───────────────────→│
  │                            │                         │  EDR issued        │
  │                            │                         │←───────────────────┤
  │                            │                         │                    │
  │  GET /consumer/            │                         │                    │
  │  transfers/{id}            │                         │                    │
  ├───────────────────────────→│                         │                    │
  │  { state: "STARTED" }      │                         │                    │
  │←───────────────────────────┤                         │                    │
  │                            │                         │                    │
  │  GET /consumer/edr/{id}    │                         │                    │
  ├───────────────────────────→│                         │                    │
  │  { endpoint, token }       │  GET /management/v3/    │                    │
  │←───────────────────────────┤  edrs/{id}/dataaddress  │                    │
```

The EDR contains an `endpoint` URL and a JWT `token`. The consumer uses these to query the actual data.

---

## Step 4: Data query with consent filtering

```
Consumer App              dataset-api (30002)       ds-connector
  │                            │                         │
  │  POST /query               │                         │
  │  Headers:                  │                         │
  │    Edc-Contract-Agreement  │                         │
  │    Edc-Bpn                 │                         │
  │  Body: { dataset, ... }    │                         │
  ├───────────────────────────→│                         │
  │                            │  GET /internal/          │
  │                            │  agreements/{id}/status  │
  │                            ├────────────────────────→│
  │                            │  { valid: true }        │
  │                            │←────────────────────────┤
  │                            │                         │
  │                            │  GET /internal/          │
  │                            │  consent/check           │
  │                            ├────────────────────────→│
  │                            │  { subject_ids: [...] } │
  │                            │←────────────────────────┤
  │                            │                         │
  │                            │  SQL: SELECT ... WHERE  │
  │                            │  user_id IN (subject_ids)│
  │  Query results             │                         │
  │←───────────────────────────┤                         │
```

When a dataset has `user_filter_column` set:
1. The dataset API calls ds-connector to get the list of consented subject IDs
2. A `WHERE user_id IN (...)` predicate is added to the SQL query
3. Only rows belonging to subjects who have actively consented are returned

---

## End-to-end flow shortcut

ds-connector provides `POST /consumer/flow` — a blocking endpoint that chains negotiate → poll → transfer → poll → EDR into a single request. Useful for testing and scripted access.

---

## Provenance events

At each stage, ds-connector emits provenance events to ds-provenance:

| Stage | Event type | PROV-O node |
|-------|-----------|-------------|
| Provider sync | `CataloguePublished` | Entity (dataset) + Activity (publish) |
| Negotiation finalized | `ContractAgreementSigned` | Activity (agreement) |
| Transfer started | `DataTransferCompleted` | Activity (transfer) |
| Obligation met | `UsageObligationFulfilled` | Activity (obligation) |

These events create a linked-data graph that can be traversed via `GET /prov/lineage/{iri}`.

---

## Consent revocation and transfer termination

When a data subject revokes consent:

1. `POST /consent/my/{id}/revoke` on ds-connector
2. `ConsentService` marks the consent record as `revoked`
3. Finds all active transfers linked to this consent
4. Calls EDC Management API to terminate each linked transfer process
5. Future data queries for this subject return no rows

---

## DSSC Blueprint alignment

| Building Block | Implementation |
|---------------|---------------|
| BB06 (Data Exchange) | EDC-based consumer-pull with EDR tokens and HTTP data plane |
| BB05 (Publication & Discovery) | DSP catalog requests + federated catalog crawler |
| BB09 (Data Sovereignty) | Consent-gated row filtering with revocation-triggered transfer termination |
