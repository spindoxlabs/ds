"""oauth2-proxy's secrets come from the environment, in every mode.

**Why this lives here.** The invariant spans three files owned by nobody in
common: the compose config `services/oauth2-proxy/oauth2-proxy.cfg`, the
compose service in `docker-compose.yml`, and the chart under
`helm/charts/ds-oauth2-proxy/`. `libs/ds-e2e` is the unit whose subject is the
whole running dataspace and it runs in CI, which is the same argument
`test_build_covers_every_stack.py` makes for living here.

**The defect (`O2P-01`).** `client_secret` and `cookie_secret` were literals in
the tracked `.cfg`. The chart had already moved both to a Secret, so only the
dev stack was affected — but the consequence was not "a weak dev value", which
this repository accepts everywhere. It was that **there was no lever**:
`docker-compose.yml` passed neither name to the container, so an operator who
set `OAUTH2_PROXY_COOKIE_SECRET` in `.env` got the committed value anyway, and
`task secrets:check` — which fails on `OAUTH2_PROXY_CLIENT_SECRET=oauth2_proxy`
— was checking a name nothing downstream read. A guard on a value that reaches
nothing is the `T-4` shape: it reports on a setting no process consumes.

**What is checked.** Not "the literal is gone" — that is the symptom, and a
symptom test passes again the moment someone adds a third secret option. The
invariant is *per secret-bearing option*: it appears in no config file, and it
is passed as an environment variable by every mode that runs the image. Adding
an option to `SECRET_OPTIONS` is therefore all it takes to cover the next one.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]

CFG = ROOT / "services" / "oauth2-proxy" / "oauth2-proxy.cfg"
COMPOSE = ROOT / "docker-compose.yml"
CHART = ROOT / "helm" / "charts" / "ds-oauth2-proxy" / "templates"

#: Every oauth2-proxy option whose value is a secret, with what a leak buys.
#:
#: The env-var name is oauth2-proxy's own mapping — `OAUTH2_PROXY_<OPTION>`,
#: uppercased — so it is derived here rather than listed, and a typo in one of
#: the two names cannot make the pair disagree.
SECRET_OPTIONS = {
    "client_secret": "sign in as any user of the realm",
    "cookie_secret": "forge a browser session with any identity",
}


def env_name(option: str) -> str:
    return f"OAUTH2_PROXY_{option.upper()}"


def _assignments(text: str) -> set[str]:
    """Option names assigned a value in a TOML-ish oauth2-proxy config.

    Comment lines are excluded deliberately: this file documents each absent
    secret *by name*, and a check that could not tell an explanation from an
    assignment would forbid saying why.
    """
    found = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", stripped)
        if m:
            found.add(m.group(1))
    return found


@pytest.fixture(scope="module")
def compose_service() -> dict:
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return doc["services"]["oauth2-proxy"]


@pytest.mark.parametrize("option", sorted(SECRET_OPTIONS))
def test_compose_config_assigns_no_secret(option: str) -> None:
    """The tracked dev config carries shape, never a secret."""
    assert option not in _assignments(CFG.read_text(encoding="utf-8")), (
        f"{CFG.relative_to(ROOT)} assigns {option}. It is tracked, so every "
        f"checkout would share one value and a leak lets an attacker "
        f"{SECRET_OPTIONS[option]}. Pass {env_name(option)} instead — the file "
        f"is mounted read-only into a container that already reads it."
    )


@pytest.mark.parametrize("option", sorted(SECRET_OPTIONS))
def test_compose_passes_the_secret_as_an_environment_variable(
    option: str, compose_service: dict
) -> None:
    """...and the compose service supplies it, or the proxy will not start."""
    environment = compose_service.get("environment") or {}
    if isinstance(environment, list):  # compose accepts both forms
        environment = dict(e.split("=", 1) for e in environment)
    assert env_name(option) in environment, (
        f"docker-compose.yml's oauth2-proxy service does not pass "
        f"{env_name(option)}. Removing it from the config file without adding "
        f"it here leaves the proxy with no value at all; adding it here without "
        f"removing it there is `O2P-01` again, from the other direction."
    )


@pytest.mark.parametrize("option", sorted(SECRET_OPTIONS))
def test_the_chart_keeps_the_secret_out_of_its_configmap(option: str) -> None:
    """A ConfigMap is readable by anyone who can `kubectl get cm`."""
    configmap = (CHART / "configmap.yaml").read_text(encoding="utf-8")
    body = configmap.split("oauth2-proxy.cfg: |", 1)[-1]
    assert option not in _assignments(body), (
        f"helm/charts/ds-oauth2-proxy/templates/configmap.yaml renders "
        f"{option} into the config. A ConfigMap is not a Secret — it is "
        f"readable by anyone with `get configmaps` in the namespace."
    )


@pytest.mark.parametrize("option", sorted(SECRET_OPTIONS))
def test_the_chart_passes_the_secret_from_a_secret(option: str) -> None:
    deployment = (CHART / "deployment.yaml").read_text(encoding="utf-8")
    secret = (CHART / "secret.yaml").read_text(encoding="utf-8")
    assert env_name(option) in deployment, (
        f"the chart's deployment does not set {env_name(option)}, so the "
        f"cluster runs with no value for {option}."
    )
    assert env_name(option) in secret, (
        f"the chart's Secret template has no {env_name(option)} key for the "
        f"deployment's secretKeyRef to resolve."
    )


def test_the_dev_defaults_are_declared_where_dev_defaults_live() -> None:
    """`.env.local` holds the dev pair, so `task` can override either in `.env`.

    Compose repeats them as `${VAR:-default}` because a hand-typed
    `docker compose up` does not read `.env.local` — but `task`'s `dotenv:`
    does, and that is the path every documented command takes.
    """
    env_local = (ROOT / ".env.local").read_text(encoding="utf-8")
    for option in SECRET_OPTIONS:
        assert re.search(rf"^{env_name(option)}=.+$", env_local, re.MULTILINE), (
            f"{env_name(option)} is not in .env.local. Compose's inline default "
            f"would still start the stack, which is exactly why this is worth "
            f"asserting: the dev value would drift out of the one file whose "
            f"job is to hold dev values."
        )
