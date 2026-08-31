"""Production configuration guard.

Dev is zero-config: every service ships working defaults so `task start` needs
no `.env`. That convenience becomes a liability the moment a chart forgets to
override one of those values, because an insecure default fails *silently*.

This module makes the failure loud, and makes it loud at exactly one point:
the deployment declares `DS_ENV=production` and every registered dev default
becomes a boot-time error instead of a log line.

Usage in a service lifespan::

    guard = ProductionGuard("connector")
    guard.forbid_default(
        "EDC_API_KEY", settings.edc_api_key, {"insecure-dev-key"},
        "Generate with: openssl rand -hex 32",
    )
    guard.forbid_true(
        "CONNECTOR_OIDC_INSECURE_DEV", settings.oidc_insecure_dev,
        "Set CONNECTOR_OIDC_ISSUER_URL and leave this false.",
    )
    guard.enforce()

In dev (`DS_ENV` unset or `dev`) every violation is logged as a warning and
startup proceeds unchanged. In production the guard collects *all* violations
and raises once, so a chart author gets the complete list in a single deploy
cycle rather than discovering them one at a time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

ENV_VAR = "DS_ENV"
PRODUCTION = "production"

#: Values that are never acceptable as a secret, whatever the setting is named.
#: Registered defaults are checked against this too, so a new dev default that
#: happens to look like these is caught even if nobody registers it explicitly.
UNIVERSAL_WEAK_VALUES = frozenset(
    {
        "",
        "admin",
        "changeme",
        "change-me",
        "password",
        "postgres",
        "secret",
        "test",
    }
)


class InsecureProductionConfig(RuntimeError):
    """Raised at startup when DS_ENV=production and dev defaults are in use."""


@dataclass(frozen=True)
class Violation:
    setting: str
    reason: str
    remediation: str

    def render(self) -> str:
        return f"  - {self.setting}: {self.reason}\n    → {self.remediation}"


def current_env() -> str:
    """The deployment environment, lowercased. **Defaults to production.**

    Inverted deliberately. It used to default to ``dev``, which meant every
    guard in the platform was disarmed by *forgetting* a variable — a chart that
    omits ``DS_ENV``, a Helm values file that drops it in a refactor, a
    hand-rolled deployment that never heard of it. The one case the guard exists
    for is the one where nobody thought about configuration, and that was
    precisely the case it stayed silent in.

    Now the safe state is the default and the *unsafe* one has to be asked for:
    development sets ``DS_ENV=dev`` explicitly (`.env.local`, committed), and
    anything that does not is treated as production and refuses to start on a
    dev default. Forgetting the variable now fails loudly instead of silently.

    The charts are unaffected — ``ds.env.common`` has always pinned
    ``DS_ENV=production`` as a constant rather than a value, which is the same
    reasoning arrived at from the other end.
    """
    return os.environ.get(ENV_VAR, PRODUCTION).strip().lower()


def is_production() -> bool:
    return current_env() == PRODUCTION


class ProductionGuard:
    """Collects insecure-default violations and enforces them per environment.

    The guard is deliberately dumb about *how* a value is wrong — each service
    declares its own dangerous values next to the settings that produce them,
    so a new insecure default cannot be added without also being registered.
    """

    def __init__(self, service: str, env: str | None = None) -> None:
        self.service = service
        self.env = (env or current_env()).strip().lower()
        self._violations: list[Violation] = []

    @property
    def violations(self) -> list[Violation]:
        return list(self._violations)

    def add(self, setting: str, reason: str, remediation: str) -> None:
        self._violations.append(Violation(setting, reason, remediation))

    def forbid_default(
        self,
        setting: str,
        value: object,
        dev_defaults: set[str],
        remediation: str,
    ) -> None:
        """Flag a value still equal to a known dev default (or trivially weak)."""
        if value is None:
            return
        text = str(value)
        if text in dev_defaults:
            self.add(setting, "still set to the dev default value", remediation)
        elif text.strip().lower() in UNIVERSAL_WEAK_VALUES:
            self.add(setting, "set to a trivially weak value", remediation)

    def forbid_secret_equal_to_client_id(
        self,
        setting: str,
        client_id: object,
        client_secret: object,
        remediation: str,
    ) -> None:
        """Flag an OIDC client secret that is still just the client id.

        Dev sets every service client's secret equal to its own ``client_id``,
        on both sides at once: ``clients.yaml`` declares
        ``secret: ${SVC_…_SECRET:-<client-id>}`` and each service defaults its
        own setting to the same string. So the two agree by coincidence, and
        nothing distinguishes *configured* from *never configured*.

        **This is the only check that can tell the difference at runtime**, and
        it has to live here rather than in ``secrets:check``. That task reads an
        env file; it cannot see a realm that was synced before a secret was set,
        or a chart that renders a Secret nobody filled in. Whether the realm and
        the service agree is decided at the token endpoint, and the service is
        the one holding both halves.

        It matters because ``celine-policies keycloak sync`` applies a client
        secret only when it *creates* the client — its plan does not diff
        secrets — so a realm synced once keeps the client-id default even after
        the variable is set. Deliberate: rewriting a live client's secret on
        every sync would be worse. The cost is that "I set the variable" is not
        evidence the realm agrees, and this is what says so.
        """
        if client_id is None or client_secret is None:
            return
        identifier = str(client_id).strip()
        secret = str(client_secret).strip()
        if identifier and secret and identifier == secret:
            self.add(
                setting,
                f"is still equal to the client id ({identifier!r}) — the dev "
                "default, so this client's secret was never overridden",
                remediation,
            )

    def require_set(self, setting: str, value: object, remediation: str) -> None:
        """Flag a value that must be present in production."""
        if value is None or (isinstance(value, str) and not value.strip()):
            self.add(setting, "is not set", remediation)

    def forbid_true(self, setting: str, value: object, remediation: str) -> None:
        """Flag a development-only toggle that must be off in production."""
        if bool(value):
            self.add(setting, "is enabled — development only", remediation)

    def require_https(self, setting: str, value: object, remediation: str) -> None:
        """Flag a URL that is not https:// in production."""
        if value is None:
            return
        text = str(value).strip()
        if text and not text.startswith("https://"):
            self.add(setting, f"is not https ({text!r})", remediation)

    def enforce(self) -> None:
        """Warn in dev; raise in production. Safe to call with no violations."""
        if not self._violations:
            if self.env == PRODUCTION:
                log.info(
                    "%s: production configuration guard passed (%s=%s)",
                    self.service,
                    ENV_VAR,
                    self.env,
                )
            return

        detail = "\n".join(v.render() for v in self._violations)

        if self.env == PRODUCTION:
            raise InsecureProductionConfig(
                f"{self.service}: refusing to start — {len(self._violations)} "
                f"insecure default(s) detected with {ENV_VAR}={PRODUCTION}:\n"
                f"{detail}\n"
                "See .env.example for the required production values."
            )

        log.warning(
            "%s: %d insecure development default(s) in use "
            "(acceptable for local dev; set %s=%s to enforce):\n%s",
            self.service,
            len(self._violations),
            ENV_VAR,
            PRODUCTION,
            detail,
        )
