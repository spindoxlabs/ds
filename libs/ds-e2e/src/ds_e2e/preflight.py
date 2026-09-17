"""What `e2e:all` needs from the stack, checked before it spends minutes on it.

**The run needs every data plane it will query.** `E2E_DATA_PLANES` defaults to
the mock on `:30022` *and* the real celine `dataset-api` on `:30002`, because
`docs/development/testing.md` makes the real one the default and asks for both
(`T-1`, `X-6c`). `task start` brings up only the mock. The real one is
`docker-compose.dataset-api.yml`, run by hand.

Before this check, a stack without the real plane ran `e2e:prepare` for two
minutes and then failed five flows on `health` and aborted a sixth with a
traceback. The requirement was real and nothing stated it. Now it is stated
once, here, before anything is reset, with both remedies.

The second check is consistency. `CONNECTOR_DATASET_API_URL` is what the
`health` steps probe, and `E2E_DATA_PLANES` is what the query flows use. A run
whose health check names a plane the queries never touch can pass `health` for
the wrong service, or fail it for a service it does not need.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from ds_e2e.config import E2ESettings

REMEDY = (
    "Either start the real data plane and seed it:\n"
    "    docker compose -f docker-compose.dataset-api.yml up -d\n"
    "    ./services/dataset-api-mock/fixtures/seed.sh\n"
    "or run against the mock alone, which the summary will then name:\n"
    "    CONNECTOR_DATASET_API_URL=http://172.17.0.1:30022 \\\n"
    "    E2E_DATA_PLANES=http://172.17.0.1:30022 task e2e:all"
)

Probe = Callable[[str], str | None]


def _probe(url: str, timeout: float = 5.0) -> str | None:
    """`None` when `<url>/health` answers 2xx, otherwise why not."""
    try:
        response = httpx.get(f"{url.rstrip('/')}/health", timeout=timeout)
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"
    if response.is_success:
        return None
    return f"HTTP {response.status_code}"


def data_plane_problems(settings: E2ESettings, probe: Probe = _probe) -> list[str]:
    """Everything that stops the configured data planes from being tested."""
    problems: list[str] = []
    planes = [url for _, url in settings.data_planes]

    if settings.dataset_api_url.rstrip("/") not in {u.rstrip("/") for u in planes}:
        problems.append(
            f"CONNECTOR_DATASET_API_URL ({settings.dataset_api_url}) is not one of "
            f"E2E_DATA_PLANES ({', '.join(planes)}), so the health checks would "
            "probe a plane the query flows do not use"
        )

    for label, url in settings.data_planes:
        why = probe(url)
        if why is not None:
            problems.append(f"{label} is not answering: {why}")
    return problems
