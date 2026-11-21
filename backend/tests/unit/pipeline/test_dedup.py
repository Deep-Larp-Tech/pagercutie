import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fake_windows import FakeWindows
from pagercutie.core.enums import Severity
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.messages import DedupOutcome, Event, Match, Opened, Renotified, Repeated
from pagercutie.rules.schemas import RuleRead

pytestmark = pytest.mark.anyio

NOW = datetime.now(UTC)
TEAM_ID = uuid.uuid7()
WINDOW = timedelta(seconds=300)
EVENT = Event(
    event_id=uuid.uuid7(),
    source="payments-webhook",
    source_id=uuid.uuid7(),
    team_id=TEAM_ID,
    schema_id=uuid.uuid7(),
    schema_name="payment",
    severity=Severity.CRITICAL,
    received_at=NOW,
    payload={"workflowId": "wf-1"},
)
# Not connected to anything: `dedup.record` is replaced in these tests.
SESSION = AsyncSession()


def make_rule(rule_id: uuid.UUID | None = None) -> RuleRead:
    return RuleRead.model_validate(
        {
            "id": rule_id or uuid.uuid7(),
            "name": "Settlement failed",
            "description": None,
            "enabled": True,
            "owner": {"type": "team", "team_id": TEAM_ID},
            "schema_ids": [],
            "condition": {"op": "exists", "field": "payload.workflowId"},
            "dedup": {"fields": ["payload.workflowId"], "window_s": int(WINDOW.total_seconds())},
            "routing": {"recipients": [{"type": "on_call", "team_id": TEAM_ID}]},
            "presentation": {"title": "Failed", "severity": "critical", "colour": "red"},
            "runbook_id": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )


def make_match(rule_id: uuid.UUID | None = None) -> Match:
    return Match(event=EVENT, rule=make_rule(rule_id), fingerprint=uuid.uuid4().hex)


def opened(match: Match) -> DedupOutcome:
    return Opened(
        alert_id=uuid.uuid7(), match=match, team_id=TEAM_ID, severity=Severity.CRITICAL, title="Failed", body=None
    )


def renotified(match: Match) -> DedupOutcome:
    return Renotified(
        alert_id=uuid.uuid7(),
        match=match,
        notification_seq=2,
        team_id=TEAM_ID,
        severity=Severity.CRITICAL,
        title="Failed",
        body=None,
    )


def repeated(match: Match) -> DedupOutcome:
    return Repeated(alert_id=uuid.uuid7(), match=match)


class Records:
    """Replaces `dedup.record`: each match gets `outcome(match)` and the alert's `notified_at`."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, notified_at: datetime = NOW) -> None:
        self.notified_at = notified_at
        self.outcome = opened

        async def record(session: AsyncSession, match: Match, claim: dedup.Recordable) -> dedup.Recorded:
            return dedup.Recorded(outcome=self.outcome(match), notified_at=self.notified_at)

        monkeypatch.setattr(dedup, "record", record)


def owned(match: Match) -> dedup.Ownership:
    return dedup.Ownership(key=dedup.window_key(match), token=dedup.pending_token(match))


def test_the_window_key_names_the_rule_and_the_fingerprint() -> None:
    match = make_match()

    assert dedup.window_key(match) == f"dedup:{match.rule.id}:{match.fingerprint}"


async def test_every_window_is_claimed_in_one_call_with_the_events_token() -> None:
    first, second = make_match(), make_match()
    windows = FakeWindows()

    async with dedup.deduplicate([first, second], windows):
        pass

    [requests] = windows.claimed
    assert [(r.key, r.window_s, r.token, r.seen_at) for r in requests] == [
        (dedup.window_key(m), 300, f"pending:{EVENT.event_id}", NOW) for m in (first, second)
    ]


async def test_a_held_window_is_a_repeat_of_its_alert_without_a_record() -> None:
    match = make_match()
    held = dedup.Held(key=dedup.window_key(match), alert_id=uuid.uuid7())

    async with dedup.deduplicate([match], FakeWindows({held.key: held})) as scope:
        assert scope.to_record == []

    assert scope.outcomes() == [Repeated(alert_id=held.alert_id, match=match)]


async def test_matches_to_record_are_ordered_by_rule_id_then_fingerprint() -> None:
    ids = sorted(uuid.uuid4() for _ in range(4))
    matches = [make_match(rule_id) for rule_id in reversed(ids)]

    async with dedup.deduplicate(matches, FakeWindows()) as scope:
        pass

    assert [item.match.rule.id for item in scope.to_record] == ids


async def test_a_won_window_of_a_new_alert_keeps_the_ttl_of_its_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    Records(monkeypatch)
    match = make_match()
    windows = FakeWindows()

    async with dedup.deduplicate([match], windows) as scope:
        outcome = await scope.record(SESSION, scope.to_record[0])

    key, token = dedup.window_key(match), dedup.pending_token(match)
    assert windows.confirmed == [dedup.Confirmation(key=key, token=token, alert_id=outcome.alert_id, ttl=None)]
    assert windows.released == []


async def test_a_won_window_of_a_renotified_alert_keeps_the_ttl_of_its_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    Records(monkeypatch).outcome = renotified
    windows = FakeWindows()

    async with dedup.deduplicate([make_match()], windows) as scope:
        await scope.record(SESSION, scope.to_record[0])

    assert [c.ttl for c in windows.confirmed] == [None]


async def test_a_won_window_of_a_repeat_lives_until_the_alerts_round_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    Records(monkeypatch, datetime.now(UTC) - timedelta(seconds=100)).outcome = repeated
    windows = FakeWindows()

    async with dedup.deduplicate([make_match()], windows) as scope:
        await scope.record(SESSION, scope.to_record[0])

    [confirmation] = windows.confirmed
    assert confirmation.ttl is not None
    assert timedelta(seconds=199) <= confirmation.ttl <= timedelta(seconds=200)


async def test_a_won_window_of_a_repeat_whose_round_is_over_is_released(monkeypatch: pytest.MonkeyPatch) -> None:
    Records(monkeypatch, NOW - WINDOW - timedelta(seconds=1)).outcome = repeated
    match = make_match()
    windows = FakeWindows()

    async with dedup.deduplicate([match], windows) as scope:
        await scope.record(SESSION, scope.to_record[0])

    assert (windows.confirmed, windows.released) == ([], [owned(match)])


async def test_a_discarded_or_unrecorded_won_window_is_released(monkeypatch: pytest.MonkeyPatch) -> None:
    Records(monkeypatch)
    discarded, unrecorded = make_match(), make_match()
    windows = FakeWindows()

    async with dedup.deduplicate([discarded, unrecorded], windows) as scope:
        item = next(i for i in scope.to_record if i.match == discarded)
        await scope.record(SESSION, item)
        scope.discard(item)

    assert windows.confirmed == []
    assert {o.key for o in windows.released} == {owned(discarded).key, owned(unrecorded).key}
    assert scope.outcomes() == []


@pytest.mark.parametrize("claim", [dedup.Pending, dedup.Unavailable], ids=["pending", "unavailable"])
async def test_other_claims_are_neither_confirmed_nor_released(
    monkeypatch: pytest.MonkeyPatch, claim: type[dedup.Pending] | type[dedup.Unavailable]
) -> None:
    Records(monkeypatch)
    match = make_match()
    windows = FakeWindows({dedup.window_key(match): claim(key=dedup.window_key(match))})

    async with dedup.deduplicate([match], windows) as scope:
        await scope.record(SESSION, scope.to_record[0])

    assert (windows.confirmed, windows.released) == ([], [])
    assert [type(o) for o in scope.outcomes()] == [Opened]


@pytest.mark.parametrize("error", [RuntimeError("commit failed"), asyncio.CancelledError()], ids=["error", "cancel"])
async def test_an_exception_in_the_scope_releases_every_won_window(
    monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    Records(monkeypatch)
    won, pending = make_match(), make_match()
    windows = FakeWindows({dedup.window_key(pending): dedup.Pending(key=dedup.window_key(pending))})

    with pytest.raises(type(error)):
        async with dedup.deduplicate([won, pending], windows) as scope:
            for item in scope.to_record:
                await scope.record(SESSION, item)
            raise error

    assert (windows.confirmed, windows.released) == ([], [owned(won)])


@pytest.mark.parametrize("error", [RuntimeError("bug"), asyncio.CancelledError()], ids=["error", "cancel"])
async def test_a_failure_while_claiming_releases_whatever_the_event_claimed(error: BaseException) -> None:
    first, second = make_match(), make_match()
    windows = FakeWindows(claim_error=error)

    with pytest.raises(type(error)):
        async with dedup.deduplicate([first, second], windows):
            raise AssertionError("the scope must not open")

    assert windows.released == [owned(first), owned(second)]


async def test_outcomes_list_redis_repeats_then_recorded_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    Records(monkeypatch)
    held_match, won_match = make_match(), make_match()
    held = dedup.Held(key=dedup.window_key(held_match), alert_id=uuid.uuid7())

    async with dedup.deduplicate([won_match, held_match], FakeWindows({held.key: held})) as scope:
        recorded = await scope.record(SESSION, scope.to_record[0])

    assert scope.outcomes() == [Repeated(alert_id=held.alert_id, match=held_match), recorded]
