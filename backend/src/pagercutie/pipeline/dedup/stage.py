"""Entrypoints of the dedup stage.

The orchestrator calls them in order: `claim` before the transaction, `record` inside it, then `confirm` after the
commit or `release` after a failure (SPEC §5.2).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, assert_never

from opentelemetry import metrics
from pydantic import JsonValue
from sqlalchemy import DateTime, Integer, Uuid, case, column, func, literal_column, text, update, values
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import UNRESOLVED, Alert
from pagercutie.alerts.schemas import AlertField, AlertStatus
from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.fields import Missing
from pagercutie.core.redis import dedup_window_key
from pagercutie.core.templates import parse, render
from pagercutie.pipeline.messages import DedupOutcome, Match, Opened, Renotified, Repeated
from pagercutie.rules import evaluator
from pagercutie.rules.schemas import RuleRead, TeamOwner, UserOwner

_fallbacks = metrics.get_meter("pagercutie.dedup").create_counter(
    "dedup_fallback",
    description="Matches upserted in Postgres without a won window, by reason: pending or unavailable (SPEC §5.2)",
)


@dataclass(frozen=True)
class Won:
    """This match claimed the dedup window; the key holds `pending` until `confirm`."""

    key: str


@dataclass(frozen=True)
class Held:
    """The window is claimed and its alert is committed: count the occurrence in Redis only."""

    key: str
    alert_id: uuid.UUID


@dataclass(frozen=True)
class Pending:
    """The window is claimed but its alert is not committed yet, or its winner failed: upsert in Postgres."""

    key: str


@dataclass(frozen=True)
class Unavailable:
    """Redis could not be reached: upsert in Postgres."""

    key: str


type Claim = Won | Held | Pending | Unavailable


@dataclass(frozen=True)
class Counter:
    """Occurrences of one alert counted in Redis since the last flush."""

    alert_id: uuid.UUID
    occurrences: int
    # Newest `received_at` among them.
    last_seen_at: datetime


# Claims whose match is upserted in Postgres; the claim only feeds the fallback metric.
type Recordable = Won | Pending | Unavailable


class WindowStore(Protocol):
    """Dedup windows and occurrence counters shared by every replica; the Redis implementation (SPEC §5.2).

    Implementations return `Unavailable` (claim) or do nothing (the other methods) when Redis cannot be reached,
    and never raise for it: a Redis outage costs Postgres writes, not alerts.
    """

    async def claim(self, key: str, window_s: int) -> Claim:
        """`SET key pending NX GET EX window_s`; `Held` or `Pending` from the previous value when the key exists."""
        ...

    async def confirm(self, key: str, alert_id: uuid.UUID) -> None:
        """`SET key alert_id XX KEEPTTL`, after the alert is committed."""
        ...

    async def release(self, key: str) -> None:
        """`DEL key`, after the transaction that would have committed the alert failed."""
        ...

    async def increment(self, alert_id: uuid.UUID, seen_at: datetime) -> None:
        """Count one occurrence of the alert, keep the newest `seen_at`, and mark the alert for the next flush."""
        ...

    async def drain(self, limit: int) -> list[Counter]:
        """Take up to `limit` marked counters and delete them, atomically; no other replica gets the same ones."""
        ...

    async def restore(self, counters: Sequence[Counter]) -> None:
        """Add drained counters back, after the flush that took them failed to commit."""
        ...


def window_key(match: Match) -> str:
    """Redis key of the match's dedup window, `dedup:{rule_id}:{fingerprint}`."""
    return dedup_window_key(match.rule.id, match.fingerprint)


async def claim(match: Match, windows: WindowStore) -> Claim:
    """Try to claim the match's dedup window for `match.rule.dedup.window_s` seconds."""
    return await windows.claim(window_key(match), match.rule.dedup.window_s)


async def record(session: AsyncSession, match: Match, claim: Recordable) -> DedupOutcome:
    """Upsert the match's alert in Postgres; the row decides the outcome, whatever the claim was (SPEC §5.2).

    A new alert is `Opened`. An unresolved alert whose last notification is at least `rule.dedup.window_s` older
    than the event is `Renotified`; any other is `Repeated`. The partial unique index on the fingerprint of
    unresolved alerts makes concurrent upserts of one fingerprint meet on one row. Opened and renotified alerts are
    audited as the system's (RUN-5); repeats are not, since every matching event makes one.
    """
    _count_fallback(claim)
    rule, event = match.rule, match.event
    view = evaluator.event_view(
        source=event.source,
        schema=event.schema_name,
        schema_id=event.schema_id,
        severity=event.severity,
        payload=event.payload,
    )
    resolve = evaluator.template_resolver(view)
    team_id = _team_id(rule)
    insert_alert = insert(Alert).values(
        id=uuid.uuid7(),
        rule_id=rule.id,
        team_id=team_id,
        fingerprint=match.fingerprint,
        status=AlertStatus.OPEN,
        severity=rule.presentation.severity,
        colour=rule.presentation.colour,
        title=render(parse(rule.presentation.title), resolve),
        body=None if rule.presentation.body is None else render(parse(rule.presentation.body), resolve),
        fields=[AlertField(path=path, value=_value(view, path)) for path in rule.presentation.fields],
        occurrences=1,
        first_seen_at=event.received_at,
        last_seen_at=event.received_at,
        notified_at=event.received_at,
        escalated_team_ids=[],
        payload=event.payload,
    )
    renotify = Alert.notified_at <= event.received_at - timedelta(seconds=rule.dedup.window_s)
    upsert = insert_alert.on_conflict_do_update(
        index_elements=[Alert.fingerprint],
        index_where=text(UNRESOLVED),
        set_={
            "occurrences": Alert.occurrences + 1,
            "last_seen_at": func.greatest(Alert.last_seen_at, insert_alert.excluded.last_seen_at),
            "notifications": case((renotify, Alert.notifications + 1), else_=Alert.notifications),
            "notified_at": case((renotify, insert_alert.excluded.notified_at), else_=Alert.notified_at),
        },
    ).returning(
        Alert.id,
        Alert.notifications,
        # Postgres 18: the row before the update, NULL after an insert.
        literal_column("old.notifications", Integer()),
    )
    alert_id, notifications, old_notifications = (await session.execute(upsert)).one()
    previous: int | None = old_notifications
    await notify(session, NotifyChannel.ALERT_CHANGED)
    if previous is None:
        opened: dict[str, JsonValue] = {"rule_id": str(rule.id), "event_id": str(event.event_id)}
        audit.record(session, None, AuditAction.ALERT_CREATED, alert_id, team_id, opened)
        return Opened(alert_id=alert_id, match=match)
    if notifications > previous:
        renotified: dict[str, JsonValue] = {"notification_seq": notifications, "event_id": str(event.event_id)}
        audit.record(session, None, AuditAction.ALERT_RENOTIFIED, alert_id, team_id, renotified)
        return Renotified(alert_id=alert_id, match=match, notification_seq=notifications)
    return Repeated(alert_id=alert_id, match=match)


async def repeat(match: Match, claim: Held, windows: WindowStore) -> Repeated:
    """Count one more occurrence of the committed alert in Redis; the counter flush adds it to the row."""
    await windows.increment(claim.alert_id, match.event.received_at)
    return Repeated(alert_id=claim.alert_id, match=match)


async def confirm(claim: Claim, outcome: DedupOutcome, windows: WindowStore) -> None:
    """Store the committed alert's ID in a `Won` window, so later matches take the Redis-only path.

    Other claims leave the window alone: its winner confirms or releases it, and the alert row decides
    renotification either way.
    """
    match claim:
        case Won(key=key):
            await windows.confirm(key, outcome.alert_id)
        case Held() | Pending() | Unavailable():
            pass
        case _:
            assert_never(claim)


async def release(claim: Claim, windows: WindowStore) -> None:
    """Free a `Won` window whose alert was not committed, so the next match retries the upsert."""
    match claim:
        case Won(key=key):
            await windows.release(key)
        case Held() | Pending() | Unavailable():
            pass
        case _:
            assert_never(claim)


async def apply_counters(session: AsyncSession, counters: Sequence[Counter]) -> None:
    """Add drained counters to their alerts in one statement: `occurrences` grows, `last_seen_at` never moves back."""
    if not counters:
        return
    rows = values(
        column("alert_id", Uuid()),
        column("occurrences", Integer()),
        column("last_seen_at", DateTime(timezone=True)),
        name="counters",
    ).data([(c.alert_id, c.occurrences, c.last_seen_at) for c in counters])
    await session.execute(
        update(Alert)
        .where(Alert.id == rows.c.alert_id)
        .values(
            occurrences=Alert.occurrences + rows.c.occurrences,
            last_seen_at=func.greatest(Alert.last_seen_at, rows.c.last_seen_at),
        )
        .execution_options(synchronize_session=False)
    )
    await notify(session, NotifyChannel.ALERT_CHANGED)


def _count_fallback(claim: Recordable) -> None:
    match claim:
        case Won():
            pass
        case Pending():
            _fallbacks.add(1, {"reason": "pending"})
        case Unavailable():
            _fallbacks.add(1, {"reason": "unavailable"})
        case _:
            assert_never(claim)


def _team_id(rule: RuleRead) -> uuid.UUID | None:
    """The alert's team: the rule's owning team, none for a personal rule."""
    match rule.owner:
        case TeamOwner(team_id=team_id):
            return team_id
        case UserOwner():
            return None
        case _:
            assert_never(rule.owner)


def _value(view: evaluator.EventView, path: str) -> JsonValue:
    found = evaluator.lookup(view, path.split("."))
    return None if isinstance(found, Missing) else found
