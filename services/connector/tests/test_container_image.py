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
    ("docker-compose.rec.yml", "ds-connector-rec", "30001"),
    ("docker-compose.third-party.yml", "ds-connector-third-party", "31001"),
]


def test_there_is_no_fallback_install_list():
    """The dependency set has one source, and a resolution failure fails the build.

    This replaces an assertion that the fallback list carried `pyjwt[crypto]`.
    The fallback is **gone** — a better fix than the one that test was written
    for: two lists that must agree eventually disagree, and the failure mode was
    silent, because `|| ` turns an unresolvable `-r pyproject.toml` into a
    *successful* build of an image missing a package. `pyjwt` verifies every JWT
    this service accepts, so that landed on the first authenticated request.

    Asserted as the absence of the `|| ` fallback rather than as the presence of
    a package, because the invariant is now structural: if the install cannot be
    satisfied, `docker build` must stop.
    """
    install = [
        line for line in DOCKERFILE.splitlines()
        if "pyproject.toml" in line and "uv pip install" in line
    ]
    assert install, "no pyproject-driven install in the Dockerfile"
    for line in install:
        assert "||" not in line, (
            "a fallback install list has come back. A dependency the image lacks "
            "must fail the build, not fail at import in a container that looked "
            "like it built."
        )
        assert "2>/dev/null" not in line, "the resolver's error must not be discarded"


def test_the_declared_dependencies_are_what_gets_installed():
    """`pyjwt[crypto]` is in `pyproject.toml`, which is now the only list.

    With the fallback gone, the Dockerfile no longer names packages — so the
    place this can regress is the declaration itself. `crypto` is the extra, not
    the package: plain `pyjwt` imports fine and then cannot verify an RS256
    signature, which is every token this service is issued.
    """
    pyproject = (UNIT / "pyproject.toml").read_text(encoding="utf-8")
    assert "pyjwt[crypto]" in pyproject
    assert "cryptography" in pyproject


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
