# edc-extensions

Java EDC extensions that register custom ODRL constraint functions for the dataspace policy vocabulary. These functions are evaluated by the EDC policy engine during contract negotiation.

---

## Purpose

The ODRL policies pushed to EDC by `ds-connector` use custom left-operands under a configurable namespace (default: `https://w3id.org/dsp/policy/`). Standard EDC cannot evaluate these — this extension registers the evaluators. The `DataspacesExtension` reads the namespace from the `dataspaces.odrl.namespace` config property and binds `{namespace}Membership` and `{namespace}ConsentStatus` constraint functions.

At negotiation time, EDC calls each registered `AtomicConstraintFunction` to check whether the counterparty satisfies the constraint. If any constraint fails, negotiation is rejected.

---

## Constraint functions

### `{ns}Membership` — `AccessScopeFunction`

Checks that the counterparty participant satisfies the membership constraint. When `CONNECTOR_IDENTITY_REGISTRY_URL` is set, scope checks are forwarded to the HTTP-backed identity-registry (with TTL cache). Otherwise falls back to file-based `participants.yaml`.

The constraint in ODRL:
```json
{
  "odrl:leftOperand": {"@id": "{ns}Membership"},
  "odrl:operator": {"@id": "odrl:eq"},
  "odrl:rightOperand": {"@id": "active"}
}
```

Where `{ns}` is the configured namespace (default `https://w3id.org/dsp/policy/`).

Participant identity is read from `ParticipantAgent.getIdentity()` in the EDC policy context. With DID-based identifiers, this is the full `did:web:` URI.

In file-based mode, the function loads and parses `participants.yaml` at startup. With identity-registry integration, lookups are performed via HTTP with a TTL cache.

### `{ns}ConsentStatus` — `ConsentStatusFunction`

Checks that an active consent record exists for the (consumer, dataset) pair by calling `ds-connector`'s internal API.

The constraint in ODRL:
```json
{
  "odrl:leftOperand": {"@id": "{ns}ConsentStatus"},
  "odrl:operator": {"@id": "odrl:eq"},
  "odrl:rightOperand": "active"
}
```

Makes an HTTP call to `GET /internal/consent/check` on `ds-connector`. Returns `true` if the response indicates an active consent. Returns `false` on any error (fail-closed).

No retry or circuit-breaker on the HTTP call — tracked as a known gap.

---

## Building

The extensions are compiled as part of the `edc-connector` fat JAR:

```bash
./gradlew :edc-connector:shadowJar
```

Or standalone (produces a library JAR, not a runnable connector):

```bash
./gradlew :edc-extensions:build
```

---

## Configuration (EDC properties)

The extension reads the following settings from the EDC properties file:

- `dataspaces.odrl.namespace` — base namespace URI for ODRL terms (default `https://w3id.org/dsp/policy/`)
- `ds.connector.internal.url` — base URL of `ds-connector` for consent checks (default `http://ds-connector:30001`)
- `ds.participants.yaml.path` — path to `participants.yaml` (default `/governance/participants.yaml`)

---

## Known gaps

- `ConsentStatusFunction` has no retry or circuit-breaker on the HTTP call to `ds-connector`
- No JUnit 5 unit tests for the constraint functions
