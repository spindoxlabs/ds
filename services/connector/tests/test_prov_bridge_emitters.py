"""Every emitter on `ProvBridge` is reached, and emits a declared event type.

Rulebook `L-15`: an event type has a schema, a materialiser **and an emitter**,
or it does not exist. The failure this guards is the mirror image — a method that
*looks* like an emitter and is called by nothing, so the event type appears
covered from inside this class and is emitted in no deployment.

Two such methods had accumulated (`data_disclosed`, `usage_obligation_fulfilled`).
They are the same shape as the dead `POST /webhooks/transfer-process` producer
that decision `D-4` dealt with, and they are why that one was hard to see: when
an unreachable emitter is indistinguishable from a reachable one, "does this
participant record `X`?" cannot be answered by reading the bridge.

This is a source-level scan for the same reason `test_settings_are_read.py` is:
it must fail on something a change *did not* do — add the call site — and an
uncalled method is invisible to any test that runs code.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "connector"
BRIDGE = SRC / "services" / "prov_bridge.py"

# The sixteen types of `docs/rulebook/provenance-and-logging.md` §"sixteen event
# types". Duplicated here deliberately: a test that read the rulebook would pass
# whenever somebody edited the rulebook, which is the wrong direction of proof.
RULEBOOK_EVENT_TYPES = frozenset({
    "CataloguePublished",
    "CatalogViewed",
    "AccessRequested",
    "NegotiationStarted",
    "NegotiationFinalized",
    "NegotiationTerminated",
    "ContractAgreementSigned",
    "TransferStarted",
    "DataTransferCompleted",
    "QueryExecuted",
    "AccessRevoked",
    "ConsentGranted",
    "ConsentRevoked",
    "DataIngested",
    "DataDisclosed",
})

# **Empty, and that is the point.** Every event type the rulebook names is
# emitted by this connector.
#
# `UsageObligationFulfilled` was the last entry, and it was **deleted rather
# than implemented** (2026-08-09). It is a *consumer* reporting that it met an
# obligation, and a provider cannot verify such a report: the obligations this
# platform declares — notify-on-access, anonymise-before-use, retention — are
# ones no third party can attest. Recording "the consumer says it complied" as
# provenance is a record whose only content is that somebody said so, which is
# `PROV-01`'s mistake with a hash. `L-15` already says an event type with no
# emitter does not exist; deleting the schema makes the code agree.
NOT_EMITTED_BY_THIS_CONNECTOR: set[str] = set()

# `DataDisclosed` was in that set, as "produced out of repo by the onboarding
# service after a CSV export". It is emitted here now, through
# `POST /admin/disclosure`, and the reason is `L-2` rather than tidiness: the
# event must carry a **recomputable** `consent_snapshot_hash`, that hash is a
# fingerprint of this connector's consent DB, and the out-of-repo producer
# cannot read it. A rule addressed to the one component unable to comply is not
# a rule anything enforces, so the emitter moved to where the fact lives.


def _emitter_methods() -> dict[str, str]:
    """`{method name: event type}` for every method on `ProvBridge` that emits."""
    text = BRIDGE.read_text()
    return {
        m.group("name"): m.group("event")
        for m in re.finditer(
            r"async def (?P<name>\w+)\((?:.|\n)*?"
            r"\"event_type\": \"(?P<event>\w+)\"",
            text,
        )
    }


def _src_files_except_bridge() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if p != BRIDGE]


def _has_call_site(method: str) -> bool:
    pattern = re.compile(rf"\.{re.escape(method)}\s*\(")
    return any(pattern.search(p.read_text()) for p in _src_files_except_bridge())


@pytest.mark.rule("L-1", "L-15")
def test_the_scan_finds_the_emitters():
    """Guards the scan. A regex that matches nothing passes everything below."""
    emitters = _emitter_methods()
    assert len(emitters) >= 10, f"only found {len(emitters)} emitters — regex drift"
    assert emitters["consent_granted"] == "ConsentGranted"


@pytest.mark.rule("L-1", "L-15")
@pytest.mark.parametrize("method", sorted(_emitter_methods()))
def test_every_emitter_has_a_call_site(method: str):
    assert _has_call_site(method), (
        f"ProvBridge.{method} emits "
        f"{_emitter_methods()[method]!r} and nothing in src/ calls it. Either "
        f"wire it, or delete it and record where that event type is produced "
        f"instead — an emitter with no caller reads as coverage this "
        f"participant does not have (rulebook L-15)."
    )


@pytest.mark.rule("L-1")
def test_every_emitted_type_is_a_rulebook_type():
    emitted = set(_emitter_methods().values())
    invented = sorted(emitted - RULEBOOK_EVENT_TYPES)
    assert not invented, (
        f"{invented} is emitted but is not one of the rulebook's sixteen. A "
        f"seventeenth event type is a rulebook change, not a code change."
    )


@pytest.mark.rule("L-1", "L-1a")
def test_the_unemitted_types_are_exactly_the_declared_ones():
    """The gap is stated, so it cannot widen quietly.

    If this fails because the set shrank, an event type gained an emitter —
    delete it from `NOT_EMITTED_BY_THIS_CONNECTOR`. If it grew, an emitter was
    removed without anyone saying where that event now comes from.
    """
    missing = RULEBOOK_EVENT_TYPES - set(_emitter_methods().values())
    assert missing == NOT_EMITTED_BY_THIS_CONNECTOR
