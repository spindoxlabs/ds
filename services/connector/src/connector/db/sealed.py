"""Personal data and live credentials, sealed at rest.

Two kinds of value in this database are worth something to whoever reads a
backup or a replica: a subject's **data keys** (`pod:…`, the supply points the
data plane filters on) and an **EDR**, a live bearer for a counterparty's data
plane. Both are stored here as ciphertext, and nothing else changes for the code
that reads them: the column types below encrypt on write and decrypt on read.

**Two keys, two jobs.**

- ``CONNECTOR_AT_REST_KEYS`` — Fernet keys, comma-separated. The first seals,
  every one opens (``MultiFernet``), which is what makes a rotation possible
  without a window where old rows cannot be read.
- ``CONNECTOR_KEY_INDEX_SECRET`` — the HMAC key of the **blind index**. A
  ciphertext is randomised, so two seals of the same key never compare equal; a
  column that must answer "which rows carry this key" stores
  ``HMAC-SHA256(secret, key)`` beside it. Deterministic on purpose, so equality
  lookups and a unique constraint work on the index column, and keyed, so the
  index of a POD cannot be computed by anyone without the secret.

**A value that cannot be opened is an error, never the stored text.** Returning
the ciphertext as if it were the value would hand a data plane a key that
matches nothing and call it a match.

**Rotation.** Prepend a new Fernet key to ``CONNECTOR_AT_REST_KEYS``, restart,
run ``python -m connector.db.sealed reseal``, then drop the old key. To rotate
the index secret, set the new one and run ``reseal`` before serving traffic:
until it has run, a lookup by index misses the rows indexed with the old secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.types import Text, TypeDecorator

log = logging.getLogger(__name__)

#: What every sealed value starts with. Lets the migration and `reseal` tell a
#: row already sealed from one written before sealing existed.
PREFIX = "sealed:v1:"


class SealedValueError(RuntimeError):
    """A stored value could not be opened with any configured key."""


class Sealer:
    def __init__(self, keys: list[str], index_secret: str) -> None:
        if not keys:
            raise ValueError("CONNECTOR_AT_REST_KEYS names no key")
        try:
            self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "CONNECTOR_AT_REST_KEYS holds a value that is not a Fernet key "
                "(generate one with: python -c 'from cryptography.fernet import "
                "Fernet; print(Fernet.generate_key().decode())')"
            ) from exc
        if not index_secret:
            raise ValueError("CONNECTOR_KEY_INDEX_SECRET is empty")
        self._index_secret = index_secret.encode()

    def seal(self, plaintext: str) -> str:
        return PREFIX + self._fernet.encrypt(plaintext.encode()).decode()

    def open(self, stored: str) -> str:
        if not stored.startswith(PREFIX):
            raise SealedValueError("stored value is not sealed")
        try:
            return self._fernet.decrypt(stored[len(PREFIX) :].encode()).decode()
        except InvalidToken as exc:
            raise SealedValueError(
                "stored value could not be opened with any key in "
                "CONNECTOR_AT_REST_KEYS"
            ) from exc

    def reseal(self, stored: str) -> str:
        """The value sealed under the first key — a no-op re-encryption."""
        return self.seal(self.open(stored))

    def index(self, value: str) -> str:
        return hmac.new(self._index_secret, value.encode(), hashlib.sha256).hexdigest()


def parse_keys(raw: str) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()]


@lru_cache(maxsize=1)
def sealer() -> Sealer:
    from ..config import get_settings

    settings = get_settings()
    return Sealer(parse_keys(settings.at_rest_keys), settings.key_index_secret)


def blind_index(value: str) -> str:
    """The deterministic, keyed index of *value*, for equality lookups."""
    return sealer().index(value)


class SealedText(TypeDecorator):
    """A string stored as ciphertext."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str | None:
        if value is None:
            return None
        return sealer().seal(str(value))

    def process_result_value(self, value: Any, dialect) -> str | None:
        if value is None:
            return None
        return sealer().open(value)


class SealedJSON(TypeDecorator):
    """A JSON value stored as the ciphertext of its serialisation."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str | None:
        if value is None:
            return None
        return sealer().seal(json.dumps(value, separators=(",", ":")))

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        return json.loads(sealer().open(value))


#: Every sealed column: (table, primary key, column, index column or None).
#: `reseal` and the migration walk this list, so a new sealed column is added
#: here as well as on the model.
SEALED_COLUMNS: tuple[tuple[str, str, str, str | None], ...] = (
    ("consent_requests", "id", "subject_keys", None),
    ("consent_key_events", "id", "key", "key_index"),
    ("edr_entries", "transfer_id", "authorization", None),
    ("edr_entries", "transfer_id", "data_address", None),
)


def seal_rows(connection, s: Sealer, *, plaintext_ok: bool) -> dict[str, int]:
    """Re-seal every sealed column under the first key; recompute the indexes.

    ``plaintext_ok`` is the migration's case: a value written before sealing
    existed is sealed as it stands. Outside the migration a plaintext value is
    an error, because nothing should have written one. Idempotent: a second run
    re-encrypts again and changes nothing a reader sees.
    """
    from sqlalchemy import text

    counts: dict[str, int] = {}
    for table, pk, column, index_column in SEALED_COLUMNS:
        rows = connection.execute(
            text(f'SELECT {pk}, "{column}" FROM {table} WHERE "{column}" IS NOT NULL')
        ).all()
        done = 0
        for row_id, stored in rows:
            stored = str(stored)
            if stored.startswith(PREFIX):
                plain = s.open(stored)
            elif plaintext_ok:
                plain = stored
            else:
                raise SealedValueError(f"{table}.{column}: a row is not sealed")
            params: dict[str, Any] = {"v": s.seal(plain), "id": row_id}
            assignment = f'"{column}" = :v'
            if index_column:
                assignment += f', "{index_column}" = :ix'
                params["ix"] = s.index(plain)
            connection.execute(
                text(f"UPDATE {table} SET {assignment} WHERE {pk} = :id"), params
            )
            done += 1
        counts[f"{table}.{column}"] = done
    return counts


def _main() -> int:  # pragma: no cover - exercised through `seal_rows`
    import argparse
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from ..config import get_settings

    parser = argparse.ArgumentParser(prog="python -m connector.db.sealed")
    parser.add_argument("command", choices=["reseal"])
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    async def run() -> dict[str, int]:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.begin() as connection:
                return await connection.run_sync(
                    seal_rows, sealer(), plaintext_ok=False
                )
        finally:
            await engine.dispose()

    for name, n in asyncio.run(run()).items():
        log.info("resealed %s: %d row(s)", name, n)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
