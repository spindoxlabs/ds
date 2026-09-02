"""A health failure with a known cause must name the cause.

`task docker:restart` recreates the ds Postgres and takes celine's `datasets` and
`rec_registry` databases with it — `docker-compose.dataset-api.yml` is a separate
compose project that `task build` deliberately skips, and `e2e:prepare` does not
re-seed it. So `docker:restart` followed by `e2e:all` is an **incomplete
sequence**, and it fails five flows at once.

Measured 2026-09-02: `api-contract`, `semantic-model`, `smoke`,
`consent-withdrawal` and `fail-closed` all failed on
`InvalidCatalogNameError: database "datasets" does not exist`, reported as
`dataset-api unreachable: HTTP 404`. That message sends a reader to the wrong
stack — the container is up and its `/docs` answers; it is the *database* that is
gone, and a missing database is why `/health` 404s rather than 500s. All five
passed after re-seeding, which is idempotent.

This pins the hint rather than the incident, because the next person to hit it
will read the failure, not this file.
"""

from __future__ import annotations

from ds_e2e.flows.base import _remedy


def test_the_dataset_api_hint_names_the_seed_script():
    hint = _remedy("dataset-api")
    assert "seed.sh" in hint, "the hint must name the command that fixes it"
    assert "services/dataset-api-mock/fixtures/seed.sh" in hint, (
        "a bare script name is not runnable — give the path from the repo root"
    )
    assert "docker:restart" in hint, "say what took the database away"


def test_services_without_a_known_cause_get_no_hint():
    """Silence is correct where there is nothing specific to say.

    A generic remedy appended to every health failure would train readers to skip
    the line that occasionally matters.
    """
    assert _remedy("provider connector") == ""
    assert _remedy("consumer provenance") == ""
