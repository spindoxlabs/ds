"""No compose file publishes an EDC's management port (plan decision 1, 2026-09-17).

EDC 0.18.0's v5 OAuth2 filter checks a token's signature, issuer, `sub` and
`scope` — never its audience. The organisation client is shared by its connector
and its batch jobs, so whoever holds its token can call its own EDC's management
API **wherever the port is reachable**. Keeping the port off the host is the
control; the connector reaches it on the project network.

Read from the files, not from a running stack: a port mapping added back is a
one-line diff nobody would read as a security change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "services" / "connector" / "config"
COMPOSE_FILES = sorted(REPO.glob("docker-compose*.yml"))


def _management_ports() -> set[int]:
    """`web.http.management.port` of every participant config."""
    ports: set[int] = set()
    for path in CONFIG.glob("*.properties"):
        if path.stem.endswith("-vault"):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("web.http.management.port="):
                ports.add(int(line.split("=", 1)[1]))
    return ports


def _published(service: dict) -> set[int]:
    """Host-side and container-side ports a service maps, in every syntax."""
    ports: set[int] = set()
    for entry in service.get("ports") or []:
        if isinstance(entry, dict):
            for key in ("published", "target"):
                if entry.get(key) is not None:
                    ports.add(int(str(entry[key]).split("-")[0]))
            continue
        # "[host-ip:]host:container[/proto]" or "container"
        parts = str(entry).split("/")[0].split(":")
        for part in parts[-2:]:
            if part.isdigit():
                ports.add(int(part))
    return ports


def test_the_participant_configs_name_their_management_ports():
    """Every assertion below is vacuous without them."""
    assert _management_ports() >= {19193, 29193, 39193}
    assert COMPOSE_FILES


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda p: p.name)
def test_no_compose_service_publishes_a_management_port(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    management = _management_ports()
    offenders = {
        name: sorted(_published(service) & management)
        for name, service in (doc.get("services") or {}).items()
        if _published(service) & management
    }
    assert offenders == {}, (
        f"{path.name} publishes an EDC management port: {offenders}. EDC does not "
        "check a token's audience, so the port must stay on the project network."
    )


def test_the_parser_sees_a_published_port():
    """A guard on the parser: the syntaxes above must actually be read."""
    assert _published({"ports": ["19193:19193"]}) == {19193}
    assert _published({"ports": ["127.0.0.1:29193:29193/tcp"]}) == {29193}
    assert _published({"ports": [{"target": 39193, "published": "39193"}]}) == {39193}


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda p: p.name)
def test_no_connector_is_configured_with_a_management_key(path):
    """The shared key is gone; a leftover variable would read as configuration."""
    text = path.read_text(encoding="utf-8")
    assert "EDC_API_KEY" not in text
    assert "WEB_HTTP_MANAGEMENT_AUTH_KEY" not in text
