# Schema cache — not a source

**The only source of truth is celine-utils**, published at its canonical URI:

    https://celine-eu.github.io/schema/governance.schema.json

`governance.schema.json` here is a **cache** of that document, not a fork and not
a second definition. Nothing in this repo may edit it; changing the schema means
changing it in celine-utils and refreshing this copy.

## Why a copy exists at all

The conformance test (`tests/tests/test_schema_conformance.py`) has to run in CI
and offline. A test that fetches over the network either fails when the network
is unavailable — noise — or skips, which enforces nothing at exactly the moment
it matters.

## Refreshing

    task -d libs/governance schema:refresh

which re-fetches the canonical URI and overwrites this copy. Run it whenever the
upstream schema changes; the conformance test then tells you whether this repo's
governance files still satisfy it.
