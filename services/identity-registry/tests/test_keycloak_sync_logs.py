"""The organisation sync logs no member email (R21).

A log line is copied to every sink the deployment ships logs to, so it is not
where personal data goes. The sync names a member by its Keycloak user id, and
a member missing from Keycloak by a count; the email addresses stay in the
`SyncReport` the operator reads.
"""

from __future__ import annotations

import logging

import pytest
from test_keycloak_admin import CONFIG, USERS, FakeKeycloak, make_client

from identity_registry.services.keycloak_admin import sync_organizations

LOGGER = "identity_registry.services.keycloak_admin"


def _messages(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        r.getMessage() for r in caplog.records if r.name.startswith(LOGGER)
    )


@pytest.mark.asyncio
async def test_member_lines_name_the_user_id_not_the_email(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    kc = await make_client(FakeKeycloak(USERS))
    await sync_organizations(CONFIG, kc)
    await kc.aclose()

    text = _messages(caplog)
    assert "@" not in text
    assert "Added user user-provider to organization example-org" in text
    assert "to user user-consumer in org example-org" in text


@pytest.mark.asyncio
async def test_a_missing_member_is_logged_as_a_count(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    kc = await make_client(FakeKeycloak({"provider@example.test": "user-provider"}))
    report = await sync_organizations(CONFIG, kc)
    await kc.aclose()

    text = _messages(caplog)
    assert "@" not in text
    assert "1 missing so far" in text
    # The operator still learns who: the report keeps the address.
    assert report.missing_users == ["consumer@example.test"]
