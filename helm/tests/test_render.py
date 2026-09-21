"""Render tests for the chart set, run locally with ``task helm:test``.

No cluster, no CI: ``helm lint`` and ``helmfile -e example template``, parsed as
YAML, with assertions over the objects. The whole ``helm/`` tree is copied to a
temporary directory first, because ``helm dependency update`` writes into it.

Every assertion names the change that turns it red.
"""

from __future__ import annotations

import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

HELM_DIR = Path(__file__).resolve().parent.parent
CHARTS = sorted(p.name for p in (HELM_DIR / "charts").iterdir() if (p / "Chart.yaml").is_file())

# The value that selected the removed ExternalSecret mode. Rendering with it set
# proves no chart still reads it.
FORMER_EXTERNAL_SECRETS_FLAG = "global.externalSecrets.enabled=true"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def _objects(manifest: str) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(manifest) if isinstance(doc, dict) and doc.get("kind")]


def _key(obj: dict) -> tuple[str, str, str]:
    meta = obj.get("metadata") or {}
    return (obj["kind"], meta.get("namespace") or "", meta["name"])


@pytest.fixture(scope="session")
def helm_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dest = tmp_path_factory.mktemp("render") / "helm"
    shutil.copytree(
        HELM_DIR,
        dest,
        ignore=shutil.ignore_patterns("Chart.lock", "tests", "__pycache__", ".pytest_cache"),
    )
    for chart in CHARTS:
        vendored = dest / "charts" / chart / "charts"
        if vendored.exists():
            shutil.rmtree(vendored)
        result = _run(["helm", "dependency", "update", f"charts/{chart}"], dest)
        assert result.returncode == 0, f"helm dependency update {chart}:\n{result.stderr}"
    return dest


def _render(helm_copy: Path, *extra: str) -> list[dict]:
    result = _run(["helmfile", "-e", "example", "template", "--skip-deps", *extra], helm_copy)
    assert result.returncode == 0, f"helmfile -e example template {' '.join(extra)}:\n{result.stderr}"
    objects = _objects(result.stdout)
    assert objects, "the render produced no objects"
    return objects


@pytest.fixture(scope="session")
def default_render(helm_copy: Path) -> list[dict]:
    """T0.1: the example environment renders, exit 0. *Red:* delete a `required` secret key."""
    return _render(helm_copy)


@pytest.fixture(scope="session")
def flagged_render(helm_copy: Path) -> list[dict]:
    return _render(helm_copy, "--set", FORMER_EXTERNAL_SECRETS_FLAG)


@pytest.mark.parametrize("chart", CHARTS)
@pytest.mark.parametrize("extra", [[], ["--set", FORMER_EXTERNAL_SECRETS_FLAG]], ids=["default", "flagged"])
def test_every_chart_lints(helm_copy: Path, chart: str, extra: list[str]) -> None:
    """T0.3: `helm lint` passes on every chart. *Red:* break a template."""
    result = _run(["helm", "lint", f"charts/{chart}", *extra], helm_copy)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("render", ["default_render", "flagged_render"])
def test_no_external_secret_renders(render: str, request: pytest.FixtureRequest) -> None:
    """The ExternalSecret mode is gone. *Red:* restore a chart's `externalsecret.yaml`
    and the `ds.externalSecret` helper: the flagged render emits ExternalSecret CRs."""
    objects = request.getfixturevalue(render)
    found = [_key(o) for o in objects if o["kind"] == "ExternalSecret"]
    assert not found, f"ExternalSecret objects rendered: {found}"


def test_every_release_with_a_secret_template_renders_its_secret(flagged_render: list[dict]) -> None:
    """Every release of a chart that has `templates/secret.yaml` renders its Secret,
    even with the former ExternalSecret flag set. *Red:* restore the
    `externalSecrets.enabled` branch in `ds.createSecret`: the flagged render has no
    Secret at all."""
    charts_with_secret = {c for c in CHARTS if (HELM_DIR / "charts" / c / "templates" / "secret.yaml").is_file()}
    assert charts_with_secret, "no chart has templates/secret.yaml"

    kinds_by_release: dict[str, set[str]] = defaultdict(set)
    chart_of_release: dict[str, str] = {}
    for obj in flagged_render:
        labels = (obj.get("metadata") or {}).get("labels") or {}
        release = labels.get("app.kubernetes.io/instance")
        chart_label = labels.get("helm.sh/chart", "")
        chart = next((c for c in charts_with_secret if chart_label.startswith(f"{c}-")), None)
        if release and chart:
            kinds_by_release[release].add(obj["kind"])
            chart_of_release[release] = chart

    assert set(chart_of_release.values()) == charts_with_secret, (
        f"charts with a secret template but no release in the example render: "
        f"{sorted(charts_with_secret - set(chart_of_release.values()))}"
    )
    missing = sorted(r for r, kinds in kinds_by_release.items() if "Secret" not in kinds)
    assert not missing, f"releases that render no Secret: {missing}"


def test_the_former_flag_changes_nothing(default_render: list[dict], flagged_render: list[dict]) -> None:
    """Setting the former flag leaves the rendered object set (kind, namespace, name)
    unchanged. *Red:* any template still reading `global.externalSecrets`."""
    default_keys = sorted(_key(o) for o in default_render)
    flagged_keys = sorted(_key(o) for o in flagged_render)
    assert flagged_keys == default_keys
