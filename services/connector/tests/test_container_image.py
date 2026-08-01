"""The image serves and probes the same port, and can build without the lockfile.

Two container defects that no Python test could have caught, so they are
asserted against the files themselves.

*The health check probed 30001 unconditionally.* One image runs as both roles;
the consumer binds 31001. A consumer container therefore reported unhealthy for
as long as it ran, however well it served — and `depends_on: service_healthy`
is what waits on that. Compose happened to override the probe per role, so this
never bit the dev stack; anything running the image as built inherited it.

*The Dockerfile's fallback install list omitted `pyjwt[crypto]`.* The list is
what runs when `-r pyproject.toml` cannot be resolved, and it must match the
real dependency set: a package missing from it does not fail the build, it
fails at import — in an image that looked like it built. `pyjwt` is what
verifies every JWT this service accepts, so the failure lands on the first
authenticated request.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

UNIT = Path(__file__).resolve().parents[1]
ROOT = UNIT.parents[1]
DOCKERFILE = (UNIT / "Dockerfile").read_text(encoding="utf-8")

#: (compose file, service, expected port)
ROLES = [
    ("docker-compose.provider.yml", "ds-connector-provider", "30001"),
    ("docker-compose.consumer.yml", "ds-connector-consumer", "31001"),
]


def test_the_fallback_install_list_carries_pyjwt():
    fallback = DOCKERFILE.split("-r /build/pyproject.toml 2>/dev/null || ")[1]
    assert "pyjwt[crypto]" in fallback


def test_the_healthcheck_does_not_hardcode_a_port():
    healthcheck = re.search(r"HEALTHCHECK.*?\n(?:.*?\n)*?\s*CMD .*", DOCKERFILE)
    assert healthcheck, "no HEALTHCHECK in the Dockerfile"
    probe = healthcheck.group(0)
    assert "CONNECTOR_PORT" in probe
    assert "30001" not in probe and "31001" not in probe


def test_the_server_binds_the_same_port_it_is_probed_on():
    cmd = re.search(r"^CMD \[.*$", DOCKERFILE, re.MULTILINE).group(0)
    assert "${CONNECTOR_PORT}" in cmd
    assert "--port 30001" not in cmd


@pytest.mark.parametrize("compose_file,service,port", ROLES)
def test_each_role_declares_its_port(compose_file, service, port):
    """The port is one fact per role, and the published mapping must match it."""
    spec = yaml.safe_load((ROOT / compose_file).read_text(encoding="utf-8"))
    svc = spec["services"][service]

    assert str(svc["environment"]["CONNECTOR_PORT"]) == port
    assert f"{port}:{port}" in svc["ports"]
    # No `command:` override: it would re-state the port and could then contradict
    # CONNECTOR_PORT, which is the disagreement this row is about.
    assert "command" not in svc
