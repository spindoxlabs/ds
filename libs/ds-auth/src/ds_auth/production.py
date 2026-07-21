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
    """The deployment environment, lowercased. Defaults to 'dev'."""
    return os.environ.get(ENV_VAR, "dev").strip().lower()


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
