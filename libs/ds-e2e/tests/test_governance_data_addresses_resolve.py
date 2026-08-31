"""Every governance `data_address.base_url` must name a host the stack serves.

**Why this lives here.** The invariant spans the governance fixtures under
`services/connector/` and the set of compose files that decide what resolves on
the `dataspaces` network — so it belongs to no single unit, and `libs/ds-e2e` is
the unit whose subject is the whole running dataspace. It is the same reasoning
as `test_build_covers_every_stack.py` beside it.

**The defect** (`E2E-15`, https://github.com/spindoxlabs/ds/issues/7). All three
datasets declared `base_url: http://dataset-api:30002/query`, and no container
has ever answered to the host `dataset-api`. The stack's stand-in plane is the
`dataset-api-rec` service; the real celine plane comes up as `dataset-api-real`
in a separate compose project that never joins the `dataspaces` network. Neither
is called `dataset-api`.

**Why it survived.** The address travels into the EDC asset and out to the
consumer as the transfer's data address, so it is only dereferenced on the leg
the e2e flows reach through the mock's own port mapping. Nothing ever asked the
name to resolve — and rulebook `X-7` is *Declared* precisely because nothing
checked it. A fixture is what the next person copies when adding a dataset, so a
name that resolves nowhere propagates.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]

#: The docker bridge gateway. Reaches a published host port from inside a
#: container and from a host process alike, which is what makes a service
#: interchangeable between the two — the convention `governance.local.yaml` uses
#: to bind the real celine plane.
BRIDGE_HOST = "172.17.0.1"


def _compose_service_names() -> set[str]:
    """Every service name declared on the shared `dataspaces` network.

    Derived, never listed: a participant added tomorrow brings its services with
    it, and a check that enumerated them would be wrong from that commit on.
    """
    names: set[str] = set()
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        document = yaml.safe_load(path.read_text()) or {}
        for name, service in (document.get("services") or {}).items():
            service = service or {}
            networks = service.get("networks") or {}
            joined = networks if isinstance(networks, list) else list(networks)
            if "dataspaces" not in joined:
                # A separate compose project — `docker-compose.dataset-api.yml`
                # is the case. Its services are unreachable by name from the ds
                # network, which is the whole point of excluding them.
                continue
            names.add(name)
            for alias in (
                (networks.get("dataspaces") or {}).get("aliases", [])
                if isinstance(networks, dict)
                else []
            ):
                names.add(alias)
    return names


def _data_address_urls() -> list[tuple[Path, str, str]]:
    """`(file, dataset key, base_url)` for every dataset in every fixture."""
    found: list[tuple[Path, str, str]] = []
    for path in sorted(ROOT.glob("services/connector/governance-*/governance.yaml")):
        document = yaml.safe_load(path.read_text()) or {}
        for key, source in (document.get("sources") or {}).items():
            address = ((source or {}).get("dataspace") or {}).get("data_address") or {}
            if base_url := address.get("base_url"):
                found.append((path, key, base_url))
    return found


def test_there_is_something_to_check():
    """A glob that matches nothing passes every test below vacuously."""
    assert _data_address_urls(), (
        "no governance fixture declared a data_address.base_url — the layout "
        "moved and this test is now checking nothing"
    )


@pytest.mark.parametrize(
    ("path", "key", "base_url"),
    _data_address_urls(),
    ids=lambda v: v.name if isinstance(v, Path) else str(v),
)
def test_every_data_address_host_resolves(path: Path, key: str, base_url: str):
    host = urlparse(base_url).hostname
    assert host, f"{path.name}:{key}: base_url {base_url!r} has no host"
    if host == BRIDGE_HOST:
        return
    services = _compose_service_names()
    assert host in services, (
        f"{path.relative_to(ROOT)}: dataset {key} addresses its data plane at "
        f"{host!r}, and no compose service or network alias on the `dataspaces` "
        f"network serves that name. Use the service name (the stand-in plane is "
        f"`dataset-api-rec`) or {BRIDGE_HOST} for something published on the "
        f"host. Known names: {sorted(services)}"
    )
