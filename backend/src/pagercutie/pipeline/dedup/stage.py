"""Entrypoints of the dedup stage.

The orchestrator opens one `deduplicate` scope per event: it claims every match's window on entry, the orchestrator
records the matches that need Postgres inside its transaction, and on exit the scope confirms the windows of
committed alerts and releases the others (SPEC §5.2, ADR-0100).
"""

import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol, assert_never

import structlog
from opentelemetry import metrics
from pydantic import JsonValue
from sqlalchemy import DateTime, Integer, Uuid, case, column, func, literal_column, select, text, update, values
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import UNRESOLVED, Alert
from pagercutie.alerts.schemas import AlertField, AlertStatus
from pagercutie.alerts.service import notify_alert_changed
from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.core.fields import Missing
from pagercutie.core.redis import ResolvedWindows, dedup_window_key
from pagercutie.core.templates import parse, render
from pagercutie.pipeline.messages import DedupOutcome, Match, Opened, Renotified, Repeated
from pagercutie.rules import evaluator
from pagercutie.rules.schemas import RuleRead, TeamOwner, UserOwner

log = structlog.get_logger("dedup")

_meter = metrics.get_meter("pagercutie.dedup")
_fallbacks = _meter.create_counter(
    "dedup_fallback",
    description="Matches upserted in Postgres without a won window, by reason: pending or unavailable (SPEC §5.2)",
)
_outcomes = _meter.create_counter(
    "dedup_outcomes_total",
    description="Committed dedup outcomes, by outcome (opened, renotified, repeated) and path (redis, postgres)",
)
_alerts_created = _meter.create_counter("alerts_created_total", description="Alerts opened and committed")
_stale_counters = _meter.create_counter(
    "dedup_stale_counters_total",
    description="Flushed counters whose alert is missing (dropped) or resolved (applied), by reason (ADR-0101)",
)

# Value of a claimed window until it is confirmed; the claiming event's token is `pending:{event_id}`.
PENDING = "pending"


@dataclass(frozen=True)
class Won:
    """This match claimed the dedup window; the key holds the event's pending token until it is confirmed."""

    key: str


@dataclass(frozen=True)
class Held:
    """The window holds a committed, unresolved alert; the claim already counted the occurrence in Redis."""

    key: str
    alert_id: uuid.UUID


@dataclass(frozen=True)
class Pending:
    """The window is claimed but its alert is not committed yet, or its winner failed: upsert in Postgres."""

    key: str


@dataclass(frozen=True)
class Unavailable:
    """Redis could not be reached or answered with an error: upsert in Postgres."""

    key: str


type Claim = Won | Held | Pending | Unavailable


# Claims whose match is upserted in Postgres.
type Recordable = Won | Pending | Unavailable


@dataclass(frozen=True)
class ClaimRequest:
    """One window to claim for `window_s` seconds; if it holds an alert, one occurrence seen at `seen_at`."""

    key: str
    window_s: int
    # Stored while the claim is pending; only a confirm or release with the same token changes the window.
    token: str
    seen_at: datetime


@dataclass(frozen=True)
class Ownership:
    """A won window and the token its claim stored."""

    key: str
    token: str


@dataclass(frozen=True)
class Confirmation:
    """Replace a won window's token with its committed alert's ID."""

    key: str
    token: str
    alert_id: uuid.UUID
    # New time to live; None keeps the one set by the claim.
    ttl: timedelta | None


@dataclass(frozen=True)
class Counter:
    """Occurrences of one alert counted in Redis since the last flush."""

    alert_id: uuid.UUID
    occurrences: int
    # Newest `received_at` among them.
    last_seen_at: datetime


class WindowStore(ResolvedWindows, Protocol):
    """Dedup windows, occurrence counters and resolved markers shared by every replica (SPEC §5.2).

    Each method is one round trip, whatever the number of windows. Implementations return `Unavailable` (claim),
    nothing (drain, recover) or do nothing (the other methods) on Redis errors, and never raise for them: a Redis
    outage costs Postgres writes, not alerts.
    """

    async def claim(self, requests: Sequence[ClaimRequest]) -> list[Claim]:
        """One claim per request, in order. An absent window, or one holding a resolved alert, is set to the token
        for `window_s` (`Won`); one holding an alert counts the occurrence on it (`Held`); any other value is
        `Pending`."""
        ...

    async def confirm(self, confirmations: Sequence[Confirmation]) -> None:
        """Set each window that still holds its token to the alert ID; delete it instead when the alert is marked
        resolved."""
        ...

    async def release(self, owned: Sequence[Ownership]) -> None:
        """Delete each window that still holds its token."""
        ...

    async def drain(self, batch: str, limit: int) -> list[Counter]:
        """Move up to `limit` marked counters into the batch named `batch`, atomically, and return them; no other
        replica gets the same ones. The batch stays in Redis until `ack` or `restore`."""
        ...

    async def ack(self, batch: str) -> None:
        """Delete a drained batch, after the flush that took it committed."""
        ...

    async def restore(self, batch: str) -> None:
        """Add a drained batch back to the counters, after the flush that took it failed."""
        ...

    async def recover(self, older_than_s: int) -> int:
        """Restore every batch drained at least `older_than_s` seconds ago, left by a flush that died; returns how
        many."""
        ...


@dataclass(frozen=True)
class Recorded:
    """What the alert upsert returned: the outcome and the alert's `notified_at` after it."""

    outcome: DedupOutcome
    notified_at: datetime


@dataclass(frozen=True)
class ToRecord:
    """A match whose alert must be upserted in Postgres."""

    match: Match
    claim: Recordable


@dataclass
class Deduplication:
    """One event's matches between claiming their windows and settling them."""

    # Held matches, already counted in Redis.
    repeated: Sequence[Repeated]
    # By rule ID, then fingerprint: the order every transaction locks alert rows in (ADR-0100).
    to_record: Sequence[ToRecord]
    _windows: WindowStore
    _recorded: dict[str, Recorded] = field(default_factory=dict)

    async def record(self, session: AsyncSession, item: ToRecord) -> DedupOutcome:
        """Upsert the item's alert in `session`; the outcome counts as committed unless `discard` is called."""
        recorded = await record(session, item.match, item.claim)
        self._recorded[item.claim.key] = recorded
        return recorded.outcome

    def discard(self, item: ToRecord) -> None:
        """The item's savepoint rolled back: release its window on exit instead of confirming it."""
        self._recorded.pop(item.claim.key, None)

    def outcomes(self) -> list[DedupOutcome]:
        """The repeats counted in Redis, then the recorded outcomes in `to_record` order."""
        recorded = [self._recorded[i.claim.key].outcome for i in self.to_record if i.claim.key in self._recorded]
        return [*self.repeated, *recorded]

    async def _settle(self) -> None:
        now = datetime.now(UTC)
        confirmations: list[Confirmation] = []
        releases: list[Ownership] = []
        for item in self.to_record:
            recorded = self._recorded.get(item.claim.key)
            if recorded is not None:
                _count_outcome(recorded.outcome, "postgres")
            match item.claim:
                case Won(key=key):
                    token = pending_token(item.match)
                    ttl = None if recorded is None else _confirm_ttl(item.match, recorded, now)
                    if recorded is None or ttl == timedelta(0):
                        releases.append(Ownership(key=key, token=token))
                    else:
                        confirmations.append(
                            Confirmation(key=key, token=token, alert_id=recorded.outcome.alert_id, ttl=ttl)
                        )
                case Pending() | Unavailable():
                    pass
                case _:
                    assert_never(item.claim)
        for repeated in self.repeated:
            _count_outcome(repeated, "redis")
        await self._windows.confirm(confirmations)
        await self._windows.release(releases)

    async def _abandon(self) -> None:
        await self._windows.release(
            [
                Ownership(key=item.claim.key, token=pending_token(item.match))
                for item in self.to_record
                if isinstance(item.claim, Won)
            ]
        )


def window_key(match: Match) -> str:
    """Redis key of the match's dedup window, `dedup:{rule_id}:{fingerprint}`."""
    return dedup_window_key(match.rule.id, match.fingerprint)


def pending_token(match: Match) -> str:
    """What a claim by the match's event stores in a won window until it is confirmed."""
    return f"{PENDING}:{match.event.event_id}"


@asynccontextmanager
async def deduplicate(matches: Sequence[Match], windows: WindowStore) -> AsyncGenerator[Deduplication]:
    """Claim every match's window in one round trip, and settle them when the block ends.

    On a normal exit, the windows of committed outcomes are confirmed and the other won windows released. On any
    exception, `CancelledError` included, every won window is released and the exception propagates. A failure
    while claiming releases whatever the claim stored for this event.
    """
    requests = [
        ClaimRequest(
            key=window_key(match),
            window_s=match.rule.dedup.window_s,
            token=pending_token(match),
            seen_at=match.event.received_at,
        )
        for match in matches
    ]
    try:
        claims = await windows.claim(requests)
    except BaseException:
        await windows.release([Ownership(key=r.key, token=r.token) for r in requests])
        raise
    repeated: list[Repeated] = []
    to_record: list[ToRecord] = []
    for match, claim in zip(matches, claims, strict=True):
        match claim:
            case Held(alert_id=alert_id):
                repeated.append(Repeated(alert_id=alert_id, match=match))
            case Won() | Pending() | Unavailable():
                to_record.append(ToRecord(match=match, claim=claim))
            case _:
                assert_never(claim)
    to_record.sort(key=lambda item: (item.match.rule.id, item.match.fingerprint))
    scope = Deduplication(repeated=repeated, to_record=to_record, _windows=windows)
    try:
        yield scope
    except BaseException:
        await scope._abandon()
        raise
    await scope._settle()


async def record(session: AsyncSession, match: Match, claim: Recordable) -> Recorded:
    """Upsert the match's alert in Postgres; the row decides the outcome, whatever the claim was (SPEC §5.2).

    A new alert is `Opened`. An unresolved alert whose last notification is at least `rule.dedup.window_s` older
    than the event is `Renotified`; any other is `Repeated`. The partial unique index on the fingerprint of
    unresolved alerts makes concurrent upserts of one fingerprint meet on one row. Opened and renotified alerts are
    audited as the system's (RUN-5); repeats are not, since every matching event makes one.
    """
    _count_fallback(claim)
    rule, event = match.rule, match.event
    view = event.view()
    resolve = evaluator.template_resolver(view)
    insert_alert = insert(Alert).values(
        id=uuid.uuid7(),
        rule_id=rule.id,
        team_id=_team_id(rule),
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
        Alert.notified_at,
        Alert.team_id,
        Alert.severity,
        Alert.title,
        Alert.body,
    )
    alert_id, notifications, previous, notified_at, team_id, severity, title, body = (
        await session.execute(upsert)
    ).one()
    await notify_alert_changed(session, alert_id, "alert.created" if previous is None else "alert.updated")
    outcome: DedupOutcome
    if previous is None:
        opened: dict[str, JsonValue] = {"rule_id": str(rule.id), "event_id": str(event.event_id)}
        audit.record(session, None, AuditAction.ALERT_CREATED, alert_id, team_id, opened)
        outcome = Opened(alert_id=alert_id, match=match, team_id=team_id, severity=severity, title=title, body=body)
    elif notifications > previous:
        renotified: dict[str, JsonValue] = {"notification_seq": notifications, "event_id": str(event.event_id)}
        audit.record(session, None, AuditAction.ALERT_RENOTIFIED, alert_id, team_id, renotified)
        outcome = Renotified(
            alert_id=alert_id,
            match=match,
            notification_seq=notifications,
            team_id=team_id,
            severity=severity,
            title=title,
            body=body,
        )
    else:
        outcome = Repeated(alert_id=alert_id, match=match)
    return Recorded(outcome=outcome, notified_at=notified_at)


async def apply_counters(session: AsyncSession, counters: Sequence[Counter]) -> None:
    """Add drained counters to their alerts: `occurrences` grows, `last_seen_at` never moves back.

    The rows are locked by rule ID, then fingerprint, the order ingest upserts them in, so a flush and an ingest
    transaction never wait on each other in a cycle. A counter whose alert is missing is dropped; one whose alert
    is resolved is still applied, since the occurrences were counted before the resolve reached Redis. Both are
    logged and counted in `dedup_stale_counters_total` (ADR-0101).
    """
    if not counters:
        return
    ids = [c.alert_id for c in counters]
    locked = await session.execute(
        select(Alert.id, Alert.status)
        .where(Alert.id.in_(ids))
        .order_by(Alert.rule_id, Alert.fingerprint)
        .with_for_update()
    )
    statuses = {alert_id: status for alert_id, status in locked}
    missing = [str(alert_id) for alert_id in ids if alert_id not in statuses]
    resolved = [str(alert_id) for alert_id, status in statuses.items() if status is AlertStatus.RESOLVED]
    if missing:
        _stale_counters.add(len(missing), {"reason": "missing"})
        log.warning("dedup.counters_dropped", message="Counted occurrences of missing alerts", alert_ids=missing)
    if resolved:
        _stale_counters.add(len(resolved), {"reason": "resolved"})
        log.warning("dedup.counters_on_resolved", message="Counted occurrences of resolved alerts", alert_ids=resolved)
    present = [c for c in counters if c.alert_id in statuses]
    if not present:
        return
    rows = values(
        column("alert_id", Uuid()),
        column("occurrences", Integer()),
        column("last_seen_at", DateTime(timezone=True)),
        name="counters",
    ).data([(c.alert_id, c.occurrences, c.last_seen_at) for c in present])
    await session.execute(
        update(Alert)
        .where(Alert.id == rows.c.alert_id)
        .values(
            occurrences=Alert.occurrences + rows.c.occurrences,
            last_seen_at=func.greatest(Alert.last_seen_at, rows.c.last_seen_at),
        )
        .execution_options(synchronize_session=False)
    )
    for counter in present:
        await notify_alert_changed(session, counter.alert_id, "alert.updated")


def _confirm_ttl(match: Match, recorded: Recorded, now: datetime) -> timedelta | None:
    """The won window's new time to live: unchanged when this event started a notification round, else what is left
    of the alert's current round (`notified_at + window_s`), zero when nothing is (ADR-0100)."""
    match recorded.outcome:
        case Opened() | Renotified():
            return None
        case Repeated():
            left = recorded.notified_at + timedelta(seconds=match.rule.dedup.window_s) - now
            return max(left, timedelta(0))
        case _:
            assert_never(recorded.outcome)


def _count_outcome(outcome: DedupOutcome, path: str) -> None:
    match outcome:
        case Opened():
            _alerts_created.add(1)
            _outcomes.add(1, {"outcome": "opened", "path": path})
        case Renotified():
            _outcomes.add(1, {"outcome": "renotified", "path": path})
        case Repeated():
            _outcomes.add(1, {"outcome": "repeated", "path": path})
        case _:
            assert_never(outcome)


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
