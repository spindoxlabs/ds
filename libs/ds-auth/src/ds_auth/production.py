"""Production configuration guard.

Dev is zero-config: every service ships working defaults so `task start` needs
no `.env`. That convenience becomes a liability the moment a chart forgets to
override one of those values, because an insecure default fails *silently*.

This module makes the failure loud, and makes it loud at exactly one point:
unless the deployment declares `DS_ENV=dev`, every registered dev default
becomes a boot-time error instead of a log line.

**Only the explicit value ``dev`` relaxes.** ``DS_ENV`` unset, empty, or set to
*any* other value — ``production``, ``prod``, ``staging``, ``test``, a typo — is
production. An allow-list of one, not a deny-list of one: the old check armed
the guards only on the exact string ``production``, so ``DS_ENV=prod`` or a
compose ``${DS_ENV:-}`` that rendered an empty string disarmed every guard on
the platform and said nothing.

Usage in a service lifespan::

    guard = ProductionGuard("connector")
    guard.forbid_default(
        "CONNECTOR_EDC_CALLBACK_SECRET", settings.edc_callback_secret,
        {"insecure-dev-callback-key"}, "Generate with: openssl rand -hex 32",
    )
    guard.forbid_true(
        "CONNECTOR_OIDC_INSECURE_DEV", settings.oidc_insecure_dev,
        "Set CONNECTOR_OIDC_ISSUER_URL and leave this false.",
    )
    guard.enforce()

In dev (`DS_ENV=dev`, and nothing else) every violation is logged as a warning
and startup proceeds unchanged. Otherwise the guard collects *all* violations
and raises once, so a chart author gets the complete list in a single deploy
cycle rather than discovering them one at a time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

log = logging.getLogger(__name__)

ENV_VAR = "DS_ENV"
#: The one value that relaxes the guards. Compared after strip + lower.
DEV = "dev"
#: What an unset or empty ``DS_ENV`` reads as. Not the only production value —
#: anything other than :data:`DEV` is production — but the one reported.
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


def weak_form(value: object) -> str:
    """The form a value is compared to the weak lists in.

    Case, surrounding space, ``_`` and ``-`` are ignored, so ``CHANGE_ME``,
    ``Change-Me`` and ``changeme`` are one placeholder. It was compared after
    ``lower()`` only, against a list holding ``changeme`` and ``change-me`` — and
    ``CHANGE_ME``, the value every key of ``helm/secrets.example.yaml`` ships
    with, passed every guard.
    """
    return str(value).strip().lower().replace("_", "").replace("-", "")


def is_weak(value: object, extra: set[str] | frozenset[str] = frozenset()) -> bool:
    """True when ``value`` is a universal weak value (or one of ``extra``),
    compared in :func:`weak_form`."""
    form = weak_form(value)
    return form in {weak_form(w) for w in UNIVERSAL_WEAK_VALUES | set(extra)}


#: Database passwords that mark a URL as the dev compose database (or as one
#: nobody chose). Checked on the *password* of a URL, because a whole-value
#: compare against :data:`UNIVERSAL_WEAK_VALUES` never matches a URL.
#: ``postgres`` (the compose default) is already a universal weak value.
WEAK_DATABASE_PASSWORDS = UNIVERSAL_WEAK_VALUES | {"dev"}


class InsecureProductionConfig(RuntimeError):
    """Raised at startup when ``DS_ENV`` is not ``dev`` and dev defaults are in use."""


@dataclass(frozen=True)
class Violation:
    setting: str
    reason: str
    remediation: str

    def render(self) -> str:
        return f"  - {self.setting}: {self.reason}\n    → {self.remediation}"


def normalise_env(value: str | None) -> str:
    """Strip and lowercase; ``None`` and the empty string both read as production."""
    text = (value or "").strip().lower()
    return text or PRODUCTION


def is_dev_env(value: str | None) -> bool:
    """True only for the explicit value ``dev`` (any case, surrounding space)."""
    return normalise_env(value) == DEV


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

    An *empty* value counts as unset (compose renders ``${DS_ENV:-}`` as
    ``""``), and the value is returned as given otherwise — callers must not
    compare it with ``production``; ask :func:`is_production` instead, which
    treats every value but ``dev`` as production.

    The charts are unaffected — ``ds.env.common`` has always pinned
    ``DS_ENV=production`` as a constant rather than a value, which is the same
    reasoning arrived at from the other end.
    """
    return normalise_env(os.environ.get(ENV_VAR))


def is_production() -> bool:
    """True unless ``DS_ENV`` is exactly ``dev`` (after strip + lower).

    ``prod``, ``staging``, ``test``, an empty string and a typo are all
    production: the safe posture is the one you get without asking.
    """
    return not is_dev_env(current_env())


def database_url_password(url: object) -> str | None:
    """The password component of a database URL, percent-decoded, or ``None``.

    Tolerates SQLAlchemy driver suffixes (``postgresql+asyncpg://``) — they are
    part of the scheme, which ``urlsplit`` ignores for the netloc.
    """
    if url is None:
        return None
    try:
        password = urlsplit(str(url).strip()).password
    except ValueError:
        return None
    return None if password is None else unquote(password)


class ProductionGuard:
    """Collects insecure-default violations and enforces them per environment.

    The guard is deliberately dumb about *how* a value is wrong — each service
    declares its own dangerous values next to the settings that produce them,
    so a new insecure default cannot be added without also being registered.
    """

    def __init__(self, service: str, env: str | None = None) -> None:
        self.service = service
        self.env = normalise_env(env) if env is not None else current_env()
        self._violations: list[Violation] = []

    @property
    def is_production(self) -> bool:
        """True unless this guard's environment is exactly ``dev``."""
        return not is_dev_env(self.env)

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
        elif is_weak(text):
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
        elif secret and is_weak(secret):
            # A placeholder (`CHANGE_ME`) or a weak word is no more a secret than
            # the client id is; the equality check alone let it through.
            self.add(setting, "is a placeholder or trivially weak value", remediation)

    def forbid_dev_database_url(
        self,
        setting: str,
        url: object,
        remediation: str,
        weak_passwords: set[str] | frozenset[str] | None = None,
    ) -> None:
        """Flag a database URL whose password is a dev or trivially weak value.

        :meth:`forbid_default` compares the *whole* value, so a dev URL is caught
        only if somebody registers that exact string — and the host or database
        name changing (``172.17.0.1`` → ``postgres``) defeats it while the
        password stays ``postgres``. This parses the URL and checks the
        password, which is the part that matters: a URL with no password at all
        (peer / IAM auth, a socket) is not flagged.
        """
        if url is None:
            return
        text = str(url).strip()
        if not text:
            return
        password = database_url_password(text)
        if password is None:
            return
        weak = WEAK_DATABASE_PASSWORDS | set(weak_passwords or ())
        if is_weak(password, weak):
            self.add(
                setting,
                "uses a dev or trivially weak database password",
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
        """Warn under ``DS_ENV=dev``; raise under every other value.

        Safe to call with no violations.
        """
        if not self._violations:
            if self.is_production:
                log.info(
                    "%s: production configuration guard passed (%s=%s)",
                    self.service,
                    ENV_VAR,
                    self.env,
                )
            return

        detail = "\n".join(v.render() for v in self._violations)

        if self.is_production:
            raise InsecureProductionConfig(
                f"{self.service}: refusing to start — {len(self._violations)} "
                f"insecure default(s) detected with {ENV_VAR}={self.env!r} "
                f"(only {ENV_VAR}={DEV} relaxes this guard; unset, empty or any "
                "other value is production):\n"
                f"{detail}\n"
                "See .env.example for the required production values."
            )

        log.warning(
            "%s: %d insecure development default(s) in use "
            "(acceptable for local dev only because %s=%s; any other value "
            "enforces):\n%s",
            self.service,
            len(self._violations),
            ENV_VAR,
            DEV,
            detail,
        )
