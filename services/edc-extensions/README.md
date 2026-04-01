# edc-extensions

Java EDC extensions that register custom ODRL constraint functions for the `ds:` vocabulary. These functions are evaluated by the EDC policy engine during contract negotiation.

---

## Purpose

The ODRL policies pushed to EDC by `ds-connector` use three custom left-operands in the `ds:` namespace. Standard EDC cannot evaluate these — this extension registers the evaluators.

At negotiation time, EDC calls each registered `AtomicConstraintFunction` to check whether the counterparty satisfies the constraint. If any constraint fails, negotiation is rejected.

---

## Constraint functions

### `ds:accessScope` — `AccessScopeFunction`

Checks that the counterparty participant is registered in `participants.yaml` with the required scope.

The constraint in ODRL:
```json
{
  "odrl:leftOperand": {"@id": "ds:accessScope"},
  "odrl:operator": {"@id": "odrl:eq"},
  "odrl:rightOperand": "dataspaces.query"
}
```

Supported right-operand values:
- `dataspaces.query` — participant must be in the `allowed_scopes` list
- `dataspaces.admin` — participant must have admin scope

Participant identity is read from `ParticipantAgent.getIdentity()` in the EDC policy context. With DID-based identifiers (Iteration 4+), this is the full `did:web:` URI, which must match the `id:` value in `participants.yaml`.

The function loads and parses `participants.yaml` at startup. Re-reading on every call is a known limitation — tracked in Iteration 2d.

### `ds:consentStatus` — `ConsentStatusFunction`

Checks that an active consent record exists for the (consumer, dataset) pair by calling `ds-connector`'s internal API.

The constraint in ODRL:
```json
{
  "odrl:leftOperand": {"@id": "ds:consentStatus"},
  "odrl:operator": {"@id": "odrl:eq"},
  "odrl:rightOperand": "active"
}
```

Makes an HTTP call to `GET /internal/consent/check` on `ds-connector`. Returns `true` if the response indicates an active consent. Returns `false` on any error (fail-closed).

No retry or circuit-breaker on the HTTP call — tracked in Iteration 2d.

### `ds:contractRequired` — `ContractRequiredFunction`

Enforces a bilateral contract pre-condition for `access_level: restricted` datasets. Currently implemented as a pass-through that returns `true` — the actual bilateral contract gate is enforced at the EDC contract definition level.

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

The extension reads two settings from the EDC properties file:

- `ds.connector.internal.url` — base URL of `ds-connector` for consent checks (default `http://ds-connector:30001`)
- `ds.participants.yaml.path` — path to `participants.yaml` (default `/governance/participants.yaml`)

---

## Known gaps (Iteration 2d)

- `AccessScopeFunction` re-reads and re-parses `participants.yaml` at construction time only; no TTL cache yet
- `ConsentStatusFunction` has no retry or circuit-breaker on the HTTP call to `ds-connector`
- No JUnit 5 unit tests for any of the three functions
