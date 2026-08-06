# ds-edc

`import ds_edc`. Wraps the EDC Management API v3 in a typed async client plus Pydantic
request/response models, and owns the JSON-LD shapes the platform sends to an EDC control
plane — the `@context`, `@type`, camelCase names and the DSP protocol identifier — along with
the polling loops that turn EDC's asynchronous state machines into one awaited result.

Holds no state, reads no configuration; constructed per control plane with a base URL and an
API key. Consumed by `services/connector` and `libs/ds-e2e`.

## References

| | |
|---|---|
| Requirements | [DSSC · Data Exchange](../../docs/blueprints/dssc/data-interoperability/data-exchange.md) |
| Rules | [Rulebook · Data exchange](../../docs/rulebook/data-exchange.md) — the protocol version pin and the quality-of-service rules |
| Code as committed | [docs/services/libs/ds-edc.md](../../docs/services/libs/ds-edc.md) |

## Rules that are not visible from the code

- **This library owns the protocol pin.** `DATASPACE_PROTOCOL = "dataspace-protocol-http:2025-1"`
  occurs once in the repository, and changing it is a dataspace-wide breaking change — see
  the rulebook's governance-of-the-protocol section before touching it.
- **`X-Api-Key` here is EDC's own Management API key** (`web.http.management.auth.key`), and
  it is correct in this one place. Not to be confused with the `X-Api-Key` that once fronted
  ds-connector's `/internal/*`: that was the *same value* spanning two trust boundaries and
  was replaced by per-caller Keycloak credentials. **Do not reuse this one anywhere else.**
- **EDC installs an authentication filter only for contexts declaring a type**, so
  `web.http.management.auth.type=tokenbased` is required — the key alone protects nothing.
- **`resume_negotiation` targets a path upstream EDC does not serve.** It is implemented by
  this repository's `services/edc-extensions`; the two must agree on the outcome vocabulary.
- **A failure must reach the caller as a failure**, and the two rules it splits into are
  rulebook `X-10` and `X-11`. A timeout raises `EdcPollTimeout`, never a synthesised state;
  a termination that did not happen raises, and the one tolerated case — a 409 on something
  already `TERMINATED` — is settled by reading the state back rather than by assuming it.
  **A 404 on `delete_*` is tolerated and a 404 on `terminate_*` is not**: absence is the goal
  of one and the failure of the other. `tests/test_termination.py` holds both sides.
- **There are two agreement ids.** `agreement_id` is local to one runtime; `dsp_agreement_id`
  is the shared one. Correlate on the shared one — see the module docstring in `webhooks.py`.

Pure Pydantic + httpx. No FastAPI, no SQLAlchemy. All calls async.

## Tests

`task -d libs/ds-edc test` — 108 unit tests against an `httpx.MockTransport` stand-in for the
control plane. `lint` and `mypy --strict` are both clean and both gate in CI; keep them that
way, because this unit is the only one with no accumulated lint debt to ratchet down.

Two of them guard invariants rather than behaviour, and they are the reason this suite exists
rather than a nicety:

- **`test_protocol_pin.py`** derives `/protocol/<version>` from `DATASPACE_PROTOCOL` and
  checks every DSP address in the repository against it, in both directions. That is the
  rulebook's *"the pin lives in exactly one place"* made mechanical.
- **`test_client_errors.py::test_every_request_issuing_method_is_covered_by_this_file`** fails
  when a method is added without a row, so a new call cannot be exempt from the error-body
  check by omission.

## Depending on it

```toml
[project]
dependencies = ["ds-edc"]

[tool.uv.sources]
ds-edc = { path = "../../libs/ds-edc", editable = true }
```

Plus `COPY libs/ds-edc/ /build/ds-edc/` in the service Dockerfile.
