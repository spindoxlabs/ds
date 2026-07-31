# Data Interoperability

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › Data Interoperability

One of the three categories of technical building blocks. Its three building blocks
address what data *means*, how it *moves*, and what is *known about its history* — the
concerns that must agree before two participants can exchange anything usefully.

| Building block | Requirement IDs | What it covers |
|---|---|---|
| **[Data Models](data-models.md)** | `DSSC-DMO-01`–`43` | Semantic definition of shared data, abstraction levels, vocabulary services, model lifecycle and reuse. |
| **[Data Exchange](data-exchange.md)** | `DSSC-DEX-01`–`66` | The Dataspace Protocol, transfer patterns, transmission methods and protocol publication. |
| **[Provenance, Traceability & Observability](provenance-traceability-observability.md)** | `DSSC-PTO-01`–`86` | Where data came from, where it went, and what can be observed about transactions. |

Requirement IDs are a local index for benchmarking. The source does not number its
requirements.

## A note on normative force in this category

Two of these three building blocks state that certain capabilities are **required** while
also stating that **no specifications are mandatory** for implementing them. Data Models
goes further: its own nested best-practice sub-page uses bare `must` twice, in direct
tension with the parent page's statement that a common data model is not mandatory. Each
page records the force of a statement at the location where it appears, and flags the
tension rather than resolving it.

Neither Data Models nor Data Exchange pins a version for the specifications it names —
the Dataspace Protocol in particular carries no version anywhere in either page.
