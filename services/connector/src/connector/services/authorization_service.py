"""Authorization query — consented subjects per dataset."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ConsentRequestORM


async def get_authorized_datasets(
    session: AsyncSession,
) -> list[dict]:
    """Return datasets with their consented subject DIDs.

    For each dataset that has any consent records, determines which subjects
    currently have an active (granted) consent by inspecting the latest
    consent record per (subject, dataset) pair.

    Response contains only public identifiers (dataset IDs, subject DIDs)
    — no consumer IDs, purposes, messages, or notification URLs.
    """
    dataset_ids_result = await session.execute(
        select(distinct(ConsentRequestORM.dataset_id))
    )
    dataset_ids = [row[0] for row in dataset_ids_result.all()]

    datasets = []
    for dataset_id in sorted(dataset_ids):
        result = await session.execute(
            select(ConsentRequestORM)
            .where(ConsentRequestORM.dataset_id == dataset_id)
            .order_by(
                ConsentRequestORM.subject_id.asc(),
                ConsentRequestORM.requested_at.desc(),
                ConsentRequestORM.revoked_at.desc(),
                ConsentRequestORM.decided_at.desc(),
            )
        )

        latest_by_subject: dict[str, ConsentRequestORM] = {}
        for consent in result.scalars().all():
            latest_by_subject.setdefault(consent.subject_id, consent)

        consented = [
            sid
            for sid, consent in latest_by_subject.items()
            if consent.status == "granted"
        ]

        if not consented:
            continue

        latest_update = max(
            (
                consent.decided_at or consent.requested_at
                for consent in latest_by_subject.values()
                if consent.status == "granted"
            ),
            default=datetime.now(timezone.utc),
        )

        datasets.append({
            "dataset_id": dataset_id,
            "consented_subjects": sorted(consented),
            "updated_at": latest_update.isoformat(),
        })

    return datasets
