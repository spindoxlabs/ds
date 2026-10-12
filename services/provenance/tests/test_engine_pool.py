"""The engine tests a pooled connection before it hands it out.

A connection idle in the pool can be dead without the service knowing: on a cluster whose
kube-proxy runs IPVS (default TCP timeout 900 s), an idle connection to a ClusterIP is
forgotten, and the next packet is answered with a reset. Without a pre-ping, the first
request after a quiet quarter of an hour fails with a 500 (seen on a staging deployment,
the participant registries' DID documents, 2026-10-12).
"""

from __future__ import annotations

from provenance.db import engine as engine_module


def test_the_engine_pre_pings_pooled_connections(monkeypatch) -> None:
    seen: dict = {}

    def _capture(url, *args, **kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(engine_module, "create_async_engine", _capture)
    monkeypatch.setattr(engine_module, "_engine", None)
    engine_module.get_engine()
    assert seen.get("pool_pre_ping") is True
