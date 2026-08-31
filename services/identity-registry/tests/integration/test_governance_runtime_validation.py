"""Governance validated against a **live** registry — `DSSC-AUP-45`, `-46`, `A-4`.

One check exists only on this path and ran in no automated pipeline:
**`owner-participant`** — every owner with a DID is a registered participant. It
is unrunnable offline, because it joins an owner to a participant *through the
owner's DID*, and only enrolment binds that. `compliance.yml` validates what an
offline run can and says so; this is the other half.

## Why here, and not a new CI job

Standing up a seeded registry is the whole cost, and this suite already pays it:
it boots a real anchor, runs migrations, and enrols participants through the
actual handshake. A second workflow doing the same thing worse is how a repo ends
up with two half-right ways to start the same service.

## What is deliberately *not* here

`controller_role`. It was, when this file was written, because the check compared
an offer's `controller_role` against the roles the identity-registry held for
that participant. That comparison was impossible — participant roles are DSP
capacities pinned to `{provider, consumer}`, and a `controller_role` is a
controller function — so the vocabulary moved beside the offers that use it and
the check became fully offline (`GOV-20`). Its tests went with it, to
`libs/governance/tests/tests/test_consent_checks.py`. Asserting it here would be
paying for a registry to answer a question the file already answers.

## The failure this is written against

`task compliance:validate:runtime` named a registry and brought no credential, so
both routes answered 401, both fetches returned `None`, and the check read `None`
as *nothing to compare* and passed — against every registry, for as long as the
flag has existed. `test_an_unreadable_registry_is_refused_not_skipped` is the
negative case; without one, none of this proves the check runs.
"""

from __future__ import annotations

import subprocess
import time

import jwt as pyjwt
import pytest
from conftest import REPO_ROOT


#: `/admin/participants` and `/owners/resolve` both require
#: `identity-registry.admin` or a read scope, so the runtime path needs a token —
#: which is the second half of why this check had never run: the CLI asked for
#: `/participants`, and `task compliance:validate:runtime` passed no credential.
#: The harness runs with `DS_ENV=dev`, where `ds_auth` verifies expiry and issuer
#: but not the signature, so a locally minted token is accepted exactly as the
#: unit suite's `make_headers` is.
def _admin_token() -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "scope": "identity-registry.admin",
            "sub": "governance-runtime-validation",
            "preferred_username": "service-account-svc-ds-identity-registry",
            "iat": now,
            "exp": now + 600,
        },
        "integration-secret",
        algorithm="HS256",
    )


GOVERNANCE_FILES = sorted(
    REPO_ROOT.glob("services/connector/governance-*/governance.yaml")
)


def _validate(governance, registry_url: str, *, extra: list[str] | None = None):
    """Run the real CLI, the way `task compliance:validate:runtime` does."""
    return subprocess.run(
        [
            "uv",
            "run",
            "ds-governance",
            "validate",
            "--file",
            str(governance),
            "--identity-registry-url",
            registry_url,
            "--token",
            _admin_token(),
            *(extra or []),
        ],
        cwd=REPO_ROOT / "libs" / "governance",
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_there_are_producers_to_validate():
    """Guard the guard — a glob that matched nothing would validate nothing and
    exit 0, which is the defect this whole row is about."""
    assert len(GOVERNANCE_FILES) >= 2, (
        f"only {len(GOVERNANCE_FILES)} producer governance files found — the glob "
        "is probably broken, not the repository"
    )


@pytest.mark.parametrize("governance", GOVERNANCE_FILES, ids=lambda p: p.parent.name)
def test_shipped_governance_validates_against_a_live_registry(
    governance, dataspace_registry
):
    """Every producer, not the first one.

    `compliance:validate:runtime` named `governance-rec` by hand until
    2026-08-08, so the grid-operator's governance was checked by nothing on the
    one path that could check it.
    """
    result = _validate(governance, dataspace_registry.url)

    assert result.returncode == 0, (
        f"{governance.parent.name} failed live validation:\n"
        f"{result.stdout}\n{result.stderr}"
    )


@pytest.mark.rule("A-4")
def test_the_owner_participant_check_has_something_to_compare(dataspace_registry):
    """Asserted against the registry, because a silent pass and a real pass look
    identical from outside the validator.

    If `/admin/participants` reports nobody with a DID, `owner-participant`
    compares every owner against an empty set — which is now a finding rather
    than a skip, but a fixture that produced it would be testing the negative
    case while claiming to test the positive one.
    """
    import httpx

    participants = httpx.get(
        f"{dataspace_registry.url}/admin/participants",
        headers={"Authorization": f"Bearer {_admin_token()}"},
        timeout=10,
    ).json()

    assert [p for p in participants if p.get("did")], (
        f"no participant carries a DID, so owner-participant compares against an "
        f"empty set: {participants}"
    )


@pytest.mark.rule("A-4")
def test_an_unreadable_registry_is_refused_not_skipped(dataspace_registry):
    """The negative case, and the reason to trust the positive ones.

    This is the exact invocation `task compliance:validate:runtime` made until
    2026-08-08 — a registry named on the command line and no credential to read
    it with. It exited **0**, having run neither check. The run must now fail:
    a caller naming a registry asked for the live check, and a quieter pass is
    what hid this for as long as the flag has existed.

    Run without `--token` rather than against a dead port, because an unreachable
    host is the easy half. A *reachable* registry answering 401 is what actually
    happened, and it is the one that looked like success.
    """
    governance = REPO_ROOT / "services/connector/governance-rec/governance.yaml"
    result = subprocess.run(
        [
            "uv",
            "run",
            "ds-governance",
            "validate",
            "--file",
            str(governance),
            "--identity-registry-url",
            dataspace_registry.url,
        ],
        cwd=REPO_ROOT / "libs" / "governance",
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode != 0, (
        "validation passed against a registry it could not read:\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "Cannot read participants" in (result.stdout + result.stderr)
