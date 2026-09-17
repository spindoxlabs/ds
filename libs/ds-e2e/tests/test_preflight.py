"""`ds-e2e preflight` — the data planes a run needs, stated before the run.

`task e2e:all` on a `task start` stack used to reset everything, then fail five
flows on `health` and abort a sixth, because the default queries the real
dataset-api that `task start` does not run. These pin the check that now says so
first, without touching the network: the probe is injected.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ds_e2e import cli, preflight
from ds_e2e.config import E2ESettings

MOCK = "http://172.17.0.1:30022"
REAL = "http://172.17.0.1:30002"


@pytest.fixture(autouse=True)
def _no_ambient_data_plane_env(monkeypatch):
    monkeypatch.delenv("E2E_DATA_PLANES", raising=False)
    monkeypatch.delenv("CONNECTOR_DATASET_API_URL", raising=False)


def _settings(**env) -> E2ESettings:
    return E2ESettings(_env_file=None, **env)


def _answering(*up: str):
    def probe(url: str) -> str | None:
        return None if url in up else "ConnectError: [Errno 111] Connection refused"

    return probe


def test_the_default_needs_both_planes():
    settings = _settings(CONNECTOR_DATASET_API_URL=REAL)
    assert {url for _, url in settings.data_planes} == {MOCK, REAL}


def test_a_task_start_stack_is_refused_and_the_real_plane_is_named():
    settings = _settings(CONNECTOR_DATASET_API_URL=REAL)

    problems = preflight.data_plane_problems(settings, probe=_answering(MOCK))

    assert len(problems) == 1
    assert "real celine dataset-api" in problems[0]
    assert "Connection refused" in problems[0]


def test_both_planes_up_passes():
    settings = _settings(CONNECTOR_DATASET_API_URL=REAL)
    assert preflight.data_plane_problems(settings, probe=_answering(MOCK, REAL)) == []


def test_the_mock_only_opt_in_passes_on_a_task_start_stack():
    settings = _settings(CONNECTOR_DATASET_API_URL=MOCK, E2E_DATA_PLANES=MOCK)
    assert preflight.data_plane_problems(settings, probe=_answering(MOCK)) == []


def test_a_health_url_outside_the_queried_planes_is_refused():
    """The half-configured opt-in: queries on the mock, health on the real one."""
    settings = _settings(CONNECTOR_DATASET_API_URL=REAL, E2E_DATA_PLANES=MOCK)

    problems = preflight.data_plane_problems(settings, probe=_answering(MOCK, REAL))

    assert len(problems) == 1
    assert "CONNECTOR_DATASET_API_URL" in problems[0]


def test_the_command_exits_non_zero_and_prints_both_remedies(monkeypatch):
    monkeypatch.setenv("CONNECTOR_DATASET_API_URL", REAL)
    monkeypatch.setattr(
        cli,
        "data_plane_problems",
        lambda s: preflight.data_plane_problems(s, probe=_answering(MOCK)),
    )

    result = CliRunner().invoke(cli.app, ["preflight"])

    assert result.exit_code == 1
    assert "docker-compose.dataset-api.yml" in result.output
    assert "E2E_DATA_PLANES=http://172.17.0.1:30022" in result.output


def test_e2e_all_runs_the_preflight_before_it_resets_anything():
    from pathlib import Path

    taskfile = (Path(__file__).resolve().parents[3] / "Taskfile.yml").read_text()
    block = taskfile.split("\n  e2e:all:\n", 1)[1].split("\n  e2e:", 1)[0]
    assert block.index("ds-e2e preflight") < block.index("task: e2e:prepare")
