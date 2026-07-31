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
- **A failure must reach the caller as a failure.** Several methods currently swallow 404,
  405 and 409, and both polls synthesise a `"TIMEOUT"` state that callers then compare against
  real EDC state names. Treat that as the pattern to fix, not to copy — see
  `.agents/defect-per-service.md`.

Pure Pydantic + httpx. No FastAPI, no SQLAlchemy. All calls async.

## Depending on it

```toml
[project]
dependencies = ["ds-edc"]

[tool.uv.sources]
ds-edc = { path = "../../libs/ds-edc", editable = true }
```

Plus `COPY libs/ds-edc/ /build/ds-edc/` in the service Dockerfile.
