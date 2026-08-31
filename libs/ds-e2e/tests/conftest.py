"""The unit suite may not touch the network. Enforced, not asked for.

`libs/ds-e2e/Taskfile.yml` says of `test`: *it mocks the database and the HTTP
client and needs no stack.* That was a description, not a constraint — and the
difference cost three sessions.

`run_cleanup` constructed its own `httpx.Client` rather than taking one, so
`test_cleanup.py` mocked `psycopg` and `HttpClient`, passed eight green
assertions, and **deleted every contract definition and policy from the running
dev stack's EDCs** on both providers (`E2E-17`). The wreckage did not look like
a clean: the asset deletes 409 while an agreement references them, so the assets
survived and the state resembled a half-finished provider sync. Nothing in any
service log accounted for it, because the deletes go straight to the EDC
Management API.

Mocking at each call site cannot prevent the next instance — the failure is that
a unit test *could* reach the network at all. So the socket is closed for the
whole suite, and a test that opens one fails naming itself.

The message matters as much as the block: a test that trips this has found a
code path that talks to a real service, and the fix is to inject the client, not
to add an exemption here.
"""

from __future__ import annotations

import socket

import pytest

_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex
_REAL_CREATE_CONNECTION = socket.create_connection


class NetworkAccessInUnitTest(RuntimeError):
    """A unit test tried to open a socket."""


def _refuse(target: object) -> NetworkAccessInUnitTest:
    return NetworkAccessInUnitTest(
        f"a unit test tried to open a socket to {target!r}. The ds-e2e unit "
        "suite runs with no stack, and a suite that can reach the network can "
        "change it — `run_cleanup` deleted the dev stack's contract "
        "definitions this way (`E2E-17`). Inject the client instead of "
        "constructing one, and pass a fake here."
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Autouse, so it covers tests written after this file.

    An opt-in marker would protect only the tests someone remembered to mark,
    which is the same shape as the defect."""

    def _connect(self, address, *args, **kwargs):
        raise _refuse(address)

    def _connect_ex(self, address, *args, **kwargs):
        raise _refuse(address)

    def _create_connection(address, *args, **kwargs):
        raise _refuse(address)

    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex)
    monkeypatch.setattr(socket, "create_connection", _create_connection)
