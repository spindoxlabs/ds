"""Every `Settings` field is read by something, and the poll intervals are two.

The unit carried seven settings that nothing outside `config.py` ever read:
three scope names (checked against literals in `dependencies.py`), a dataset-API
URL (the dataset API calls the connector, not the reverse), two EDC protocol
URLs (a counter-party is resolved through the identity registry) and a transfer
poll interval (the negotiation one was used for both polls).

They are not equally harmless. A configuration surface that answers is worse
than one that is absent: `CONNECTOR_INTERNAL_SCOPE` read like it could rename
the scope a data plane must hold, and an operator setting
`CONNECTOR_TRANSFER_POLL_INTERVAL` got the negotiation value instead — with
nothing anywhere reporting that the value had been discarded.

The sweep here is what keeps that from coming back; it is the only test in the
unit that can fail because of something a change *did not* do.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from connector.config import Settings
from connector.services.consumer_service import ConsumerService

SRC = Path(__file__).resolve().parents[1] / "src" / "connector"

#: Fields whose reader is not a ``settings.<name>`` expression. Each needs a
#: reason — an entry here is an exemption from the rule above, not a parking
#: space for the next dead setting.
READ_ELSEWHERE = {
    # Consumed by the settings model itself: `load_file_secrets` folds it into
    # `edc_api_key`, and nothing reads the path again.
    "edc_api_key_file",
}

#: ``settings.name``, or the name quoted — `notifications/factory.py` reads
#: `notify_backends` through `getattr`, which is a read like any other.
_READ = r'\.{name}\b|["\']{name}["\']'

_COMMENT = re.compile(r"#.*$", re.MULTILINE)


def _sources() -> str:
    """Every module but `config.py`, with comments stripped.

    Comments are removed deliberately: this file's own prose names the settings
    that were deleted, and a setting mentioned in a comment is not a setting
    anybody reads.
    """
    return _COMMENT.sub(
        "",
        "\n".join(
            p.read_text(encoding="utf-8")
            for p in SRC.rglob("*.py")
            if p.name != "config.py"
        ),
    )


def test_no_setting_is_read_by_nothing():
    body = _sources()
    unread = [
        name
        for name in Settings.model_fields
        if name not in READ_ELSEWHERE
        and not re.search(_READ.format(name=re.escape(name)), body)
    ]
    assert unread == [], (
        "settings read by nothing outside config.py — delete them, or wire them: "
        f"{unread}"
    )


class _RecordingEdc:
    """Records the poll intervals the flow asks for."""

    def __init__(self):
        self.intervals: dict[str, float] = {}

    async def request_catalog(self, _req):
        return {"dataset": []}

    async def start_negotiation(self, _req):
        return "neg-1"

    async def poll_negotiation(self, _id, poll_interval, timeout):
        self.intervals["negotiation"] = poll_interval
        return _State("FINALIZED", contract_agreement_id="agr-1")

    async def start_transfer(self, _req):
        return "tx-1"

    async def poll_transfer(self, _id, poll_interval, timeout):
        self.intervals["transfer"] = poll_interval
        return _State("STARTED")

    async def get_edr(self, _id):
        from ds_edc.schemas import EdrResponse

        return EdrResponse(
            endpoint="http://172.17.0.1:30002/query", authorization="tok"
        )


class _State:
    def __init__(self, state, contract_agreement_id=None):
        self.state = state
        self.contract_agreement_id = contract_agreement_id
        self.error_detail = None


class _Registry:
    def validate(self, _address):
        return None


class _Prov:
    async def contract_agreement_signed(self, **_kwargs):
        return None

    async def data_transfer_completed(self, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_the_transfer_poll_uses_the_transfer_interval():
    """Distinct values, so a single shared interval cannot pass by coincidence."""
    from connector.schemas.edc import FlowRequest

    edc = _RecordingEdc()
    svc = ConsumerService(
        consumer_edc=edc,
        registry=_Registry(),
        prov=_Prov(),
        negotiation_poll_interval=3.0,
        transfer_poll_interval=7.0,
    )

    await svc.run_flow(
        FlowRequest(
            counter_party_address="http://172.17.0.1:19194/protocol/2025-1",
            asset_id="datasets.gold.test",
            assigner="did:web:rec.dataspaces.localhost",
        )
    )

    assert edc.intervals == {"negotiation": 3.0, "transfer": 7.0}


@pytest.mark.asyncio
async def test_the_app_passes_both_intervals_through():
    """A wired `ConsumerService` is worth nothing if `main.py` still passes one."""
    import connector.main as main

    settings = Settings(
        role="consumer", negotiation_poll_interval=3.0, transfer_poll_interval=7.0
    )
    captured: dict[str, float] = {}

    class _Capture(ConsumerService):
        def __init__(self, **kwargs):
            captured.update(
                negotiation=kwargs["negotiation_poll_interval"],
                transfer=kwargs["transfer_poll_interval"],
            )
            super().__init__(**kwargs)

    async def _no_schema_check():
        return None

    monkey = pytest.MonkeyPatch()
    monkey.setattr(main, "ConsumerService", _Capture)
    monkey.setattr(main, "get_settings", lambda: settings)
    # Consumer role: no sweeper, so the lifespan touches no database once the
    # schema check is out of the way.
    monkey.setattr(main, "verify_schema", _no_schema_check)
    try:
        app = main.create_app()
        async with app.router.lifespan_context(app):
            pass
    finally:
        monkey.undo()

    assert captured == {"negotiation": 3.0, "transfer": 7.0}
