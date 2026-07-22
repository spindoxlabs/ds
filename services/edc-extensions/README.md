# edc-extensions

Java EDC extensions that register custom ODRL constraint functions for the dataspace policy vocabulary. These functions are evaluated by the EDC policy engine during contract negotiation.

---

## Purpose

The ODRL policies pushed to EDC by `ds-connector` use custom left-operands under a configurable namespace (default: `https://w3id.org/dsp/policy/`). Standard EDC cannot evaluate these — this extension registers the evaluators. The `DataspacesExtension` reads the namespace from the `dataspaces.odrl.namespace` config property and binds `{namespace}Membership` and `{namespace}ConsentStatus` constraint functions.

At negotiation time, EDC calls each registered `AtomicConstraintFunction` to check whether the counterparty satisfies the constraint. If any constraint fails, negotiation is rejected.

---

## Constraint functions

### `{ns}Membership` — `AccessScopeFunction`

Checks that the counterparty participant satisfies the membership constraint. Makes an HTTP POST to `ds-connector POST /internal/participants/check`, which forwards the scope check to the identity-registry service. Results are cached with a configurable TTL.

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

The function calls `POST /internal/participants/check` on ds-connector (configured via `ds.connector.internal.url`), which forwards the check to the identity-registry service. Results are cached with a TTL to avoid per-request HTTP overhead.

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
- `ds.participants.yaml.path` — (legacy) path to participants YAML file; only used in file-based fallback mode when identity-registry is not configured

---

## Known gaps

- `ConsentStatusFunction` has no retry or circuit-breaker on the HTTP call to `ds-connector`
- No JUnit 5 unit tests for the constraint functions
