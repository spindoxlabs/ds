"""`provenance-admin` — the operator's commands over the event record.

    provenance-admin verify               recompute the hash chain; exit 1 if broken
    provenance-admin backfill             chain rows written before migration 0004
    provenance-admin retention [--days N] pseudonymise person ids older than N days

`retention` takes `PROVENANCE_PERSON_ID_RETENTION_DAYS` (default 3650) when
`--days` is not given. It is meant for a scheduled job.
Each command prints one JSON line.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import get_settings
from .db.engine import get_session_factory
from .services import chain


async def _run(args: argparse.Namespace) -> int:
    async with get_session_factory()() as session:
        if args.command == "verify":
            result = await chain.verify(session)
            print(json.dumps(result.as_dict()))
            return 0 if result.ok else 1
        if args.command == "backfill":
            count = await chain.backfill(session)
            await session.commit()
            print(json.dumps({"chained": count}))
            return 0
        days = args.days or get_settings().person_id_retention_days
        retention = await chain.apply_retention(session, days)
        await session.commit()
        print(json.dumps(retention.as_dict()))
        return 0


def _period(value: str) -> int:
    """A retention period in days: a whole number, at least 1. Anything less
    would put the cutoff at or after now and pseudonymise every record."""
    try:
        days = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of days: {value!r}") from None
    if days < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1 day, got {days}")
    return days


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provenance-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="recompute the event record's hash chain")
    commands.add_parser("backfill", help="chain the rows that have no place yet")
    retention = commands.add_parser("retention", help="pseudonymise aged person ids")
    retention.add_argument("--days", type=_period, default=None)
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
