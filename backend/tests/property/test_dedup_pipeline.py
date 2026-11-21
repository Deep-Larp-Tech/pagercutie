"""Pipeline-level dedup properties without a database (SPEC §5.2, §9): N matches of one fingerprint inside a window
make one alert with N occurrences after the counter flush, whatever order they arrive in and however they interleave.

Redis is modelled by `StatefulWindows` (the shared `FakeWindows` with window and counter state) and the alert upsert
by `AlertTable`, which applies the row's rules: insert opens, any later match on the unresolved row repeats.
"""

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from fake_windows import FakeWindows
from pagercutie.core.enums import Severity
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.messages import DedupOutcome, Event, Match, Opened, Repeated
from pagercutie.rules.schemas import RuleRead

START = datetime(2030, 1, 1, tzinfo=UTC)
WINDOW_S = 300
TEAM_ID = uuid.UUID(int=1)
RULE = RuleRead.model_validate(
    {
        "id": uuid.UUID(int=2),
        "name": "Settlement failed",
        "description": None,
        "enabled": True,
        "owner": {"type": "team", "team_id": TEAM_ID},
        "schema_ids": [],
        "condition": {"op": "exists", "field": "payload.workflowId"},
        "dedup": {"fields": ["payload.workflowId"], "window_s": WINDOW_S},
        "routing": {"recipients": [{"type": "on_call", "team_id": TEAM_ID}]},
        "presentation": {"title": "Failed", "severity": "critical", "colour": "red"},
        "runbook_id": None,
        "created_at": START,
        "updated_at": START,
    }
)
FINGERPRINT = "f" * 64
# Never connected: `dedup.record` is replaced by `AlertTable.record`.
SESSION = AsyncSession()


def match_at(offset_s: int) -> Match:
    event = Event(
        event_id=uuid.uuid7(),
        source="payments-webhook",
        source_id=uuid.UUID(int=3),
        team_id=TEAM_ID,
        schema_id=uuid.UUID(int=4),
        schema_name="payment",
        severity=Severity.CRITICAL,
        received_at=START + timedelta(seconds=offset_s),
        payload={"workflowId": "wf-1"},
    )
    return Match(event=event, rule=RULE, fingerprint=FINGERPRINT)


class StatefulWindows(FakeWindows):
    """`FakeWindows` with the semantics of `RedisWindowStore`: `SET NX` claims, counters, confirms and drains.

    Each call yields to the event loop first, so concurrent events interleave between round trips.
    """

    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}
        self.counters: dict[uuid.UUID, dedup.Counter] = {}

    async def claim(self, requests: Sequence[dedup.ClaimRequest]) -> list[dedup.Claim]:
        await asyncio.sleep(0)
        claims: list[dedup.Claim] = []
        for request in requests:
            value = self.values.get(request.key)
            if value is None:
                self.values[request.key] = request.token
                claims.append(dedup.Won(key=request.key))
            elif value.startswith(dedup.PENDING):
                claims.append(dedup.Pending(key=request.key))
            else:
                alert_id = uuid.UUID(value)
                counter = self.counters.get(alert_id, dedup.Counter(alert_id, 0, request.seen_at))
                self.counters[alert_id] = dedup.Counter(
                    alert_id, counter.occurrences + 1, max(counter.last_seen_at, request.seen_at)
                )
                claims.append(dedup.Held(key=request.key, alert_id=alert_id))
        return claims

    async def confirm(self, confirmations: Sequence[dedup.Confirmation]) -> None:
        await asyncio.sleep(0)
        for confirmation in confirmations:
            if self.values.get(confirmation.key) == confirmation.token:
                self.values[confirmation.key] = str(confirmation.alert_id)

    async def release(self, owned: Sequence[dedup.Ownership]) -> None:
        await asyncio.sleep(0)
        for ownership in owned:
            if self.values.get(ownership.key) == ownership.token:
                del self.values[ownership.key]

    async def drain(self, batch: str, limit: int) -> list[dedup.Counter]:
        drained = list(self.counters.values())[:limit]
        for counter in drained:
            del self.counters[counter.alert_id]
        return drained


@dataclass
class Row:
    """The columns of an alert row these properties read."""

    alert_id: uuid.UUID
    occurrences: int
    last_seen_at: datetime


class AlertTable:
    """Stands in for the alert upsert: one unresolved row per fingerprint, the row decides the outcome."""

    def __init__(self) -> None:
        self.rows: dict[str, Row] = {}

    async def record(self, session: AsyncSession, match: Match, claim: dedup.Recordable) -> dedup.Recorded:
        await asyncio.sleep(0)
        at = match.event.received_at
        row = self.rows.get(match.fingerprint)
        outcome: DedupOutcome
        if row is None:
            row = self.rows[match.fingerprint] = Row(alert_id=uuid.uuid7(), occurrences=1, last_seen_at=at)
            outcome = Opened(
                alert_id=row.alert_id,
                match=match,
                team_id=TEAM_ID,
                severity=Severity.CRITICAL,
                title="Failed",
                body=None,
            )
        else:
            row.occurrences += 1
            row.last_seen_at = max(row.last_seen_at, at)
            outcome = Repeated(alert_id=row.alert_id, match=match)
        return dedup.Recorded(outcome=outcome, notified_at=START)

    def flush(self, counters: Sequence[dedup.Counter]) -> None:
        for counter in counters:
            row = next(row for row in self.rows.values() if row.alert_id == counter.alert_id)
            row.occurrences += counter.occurrences
            row.last_seen_at = max(row.last_seen_at, counter.last_seen_at)


async def ingest(match: Match, windows: StatefulWindows) -> list[DedupOutcome]:
    """What the orchestrator does for one event with one match."""
    async with dedup.deduplicate([match], windows) as scope:
        for item in scope.to_record:
            await scope.record(SESSION, item)
    return scope.outcomes()


async def run(offsets: Sequence[int], concurrent: bool) -> tuple[AlertTable, list[DedupOutcome]]:
    windows, table = StatefulWindows(), AlertTable()
    matches = [match_at(offset) for offset in offsets]
    with patch.object(dedup, "record", table.record):
        if concurrent:
            results = await asyncio.gather(*(ingest(match, windows) for match in matches))
        else:
            results = [await ingest(match, windows) for match in matches]
    table.flush(await windows.drain("flush", len(matches)))
    return table, [outcome for outcomes in results for outcome in outcomes]


offsets_in_one_window = st.lists(st.integers(min_value=0, max_value=WINDOW_S - 1), min_size=1, max_size=25)


@given(offsets=offsets_in_one_window, concurrent=st.booleans())
def test_n_matches_in_one_window_make_one_alert_with_n_occurrences(offsets: list[int], concurrent: bool) -> None:
    table, outcomes = asyncio.run(run(offsets, concurrent))

    assert len(table.rows) == 1
    (row,) = table.rows.values()
    assert row.occurrences == len(offsets)
    assert row.last_seen_at == START + timedelta(seconds=max(offsets))
    assert [type(outcome) for outcome in outcomes].count(Opened) == 1
    assert {outcome.alert_id for outcome in outcomes} == {row.alert_id}


@given(offsets=offsets_in_one_window, data=st.data())
def test_the_result_does_not_depend_on_arrival_order(offsets: list[int], data: st.DataObject) -> None:
    reordered = data.draw(st.permutations(offsets))

    results = [asyncio.run(run(order, concurrent)) for order in (offsets, reordered) for concurrent in (False, True)]

    summaries = {
        (len(table.rows), *((row.occurrences, row.last_seen_at) for row in table.rows.values())) for table, _ in results
    }
    assert len(summaries) == 1
