"""The `escalate` action: add a team to the alert and notify it (SPEC §11.4 step 5, RUN-3, ADR-0102).

Runs in `complete_step`'s transaction, so the escalation commits with the step's outcome or not at all.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert
from pagercutie.alerts.service import notify_alert_changed
from pagercutie.audit.schemas import AuditAction
from pagercutie.audit.service import record
from pagercutie.core.enums import Channel
from pagercutie.pipeline import recipients
from pagercutie.pipeline.executor.claims import StepJob
from pagercutie.rules.schemas import TeamRecipient
from pagercutie.teams.models import Team


async def find_team(session: AsyncSession, slug: str) -> Team | None:
    """The team an `escalate` step names by slug, or None when no team has it."""
    return await session.scalar(select(Team).where(Team.slug == slug))


async def escalate(session: AsyncSession, job: StepJob, team: Team, now: datetime) -> list[uuid.UUID]:
    """Add `team` to the alert's `escalated_team_ids` and insert deliveries for its leads and members, using the team's
    channel preferences for the alert's severity at `now` (DEL-2); returns the delivery IDs inserted.

    Idempotent: the team is appended once, and delivery IDs derive from the alert, user, channel and escalated team, so
    a repeated escalation inserts nothing and does not collide with routing's deliveries (SPEC §5.4). Audits
    `alert.escalated` and sends `NOTIFY alert_changed` when the team was added; `insert_deliveries` sends
    `deliveries_pending`.
    """
    added = await session.scalar(
        update(Alert)
        .where(Alert.id == job.alert_id, ~Alert.escalated_team_ids.contains([team.id]))
        .values(escalated_team_ids=func.array_append(Alert.escalated_team_ids, team.id))
        .returning(Alert.id)
    )
    alert = (
        await session.execute(select(Alert.severity, Alert.title, Alert.body).where(Alert.id == job.alert_id))
    ).one()
    log_context = {"alert_id": str(job.alert_id), "run_id": str(job.run_id), "index": str(job.index)}
    reached = await recipients.resolve(session, [TeamRecipient(type="team", team_id=team.id)], now, log_context)
    channels = recipients.channels_by_user(reached, alert.severity, now, None)

    def key(user_id: uuid.UUID, channel: Channel) -> str:
        return f"{job.alert_id}:{user_id}:{channel}:escalation:{team.id}"

    deliveries = recipients.new_deliveries(channels, alert.title, alert.body, key)
    inserted = await recipients.insert_deliveries(session, job.alert_id, deliveries, now)
    if added is not None:
        record(
            session,
            None,
            AuditAction.ALERT_ESCALATED,
            job.alert_id,
            job.team_id,
            {
                "run_id": str(job.run_id),
                "index": job.index,
                "escalated_team_id": str(team.id),
                "approved_by": None if job.decided_by is None else str(job.decided_by),
                "deliveries": len(inserted),
            },
        )
        await notify_alert_changed(session, job.alert_id, "alert.updated")
    return inserted
