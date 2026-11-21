import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from pagercutie.core.enums import Severity
from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.messages import Event, Match, Opened, Repeated
from pagercutie.rules.schemas import RuleRead

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
TEAM_ID = uuid.uuid7()
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
RULE = RuleRead.model_validate(
    {
        "id": uuid.uuid7(),
        "name": "Settlement failed",
        "description": None,
        "enabled": True,
        "owner": {"type": "team", "team_id": TEAM_ID},
        "schema_ids": [],
        "condition": {"op": "exists", "field": "payload.workflowId"},
        "dedup": {"fields": ["payload.workflowId"], "window_s": 300},
        "routing": {"recipients": [{"type": "on_call", "team_id": TEAM_ID}]},
        "presentation": {"title": "Failed", "severity": "critical", "colour": "red"},
        "runbook_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
)
MATCH = Match(event=EVENT, rule=RULE, fingerprint="a" * 64)
KEY = dedup.window_key(MATCH)
ALERT_ID = uuid.uuid7()


class RecordingWindows:
    """Records every call; claims and the flush methods are not used by these entrypoints."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def claim(self, key: str, window_s: int) -> dedup.Claim:
        raise AssertionError("not called")

    async def confirm(self, key: str, alert_id: uuid.UUID) -> None:
        self.calls.append(("confirm", key, str(alert_id)))

    async def release(self, key: str) -> None:
        self.calls.append(("release", key))

    async def increment(self, alert_id: uuid.UUID, seen_at: datetime) -> None:
        self.calls.append(("increment", str(alert_id), seen_at.isoformat()))

    async def drain(self, limit: int) -> list[dedup.Counter]:
        raise AssertionError("not called")

    async def restore(self, counters: Sequence[dedup.Counter]) -> None:
        raise AssertionError("not called")


OTHER_CLAIMS = [dedup.Held(key=KEY, alert_id=ALERT_ID), dedup.Pending(key=KEY), dedup.Unavailable(key=KEY)]


def test_the_window_key_names_the_rule_and_the_fingerprint() -> None:
    assert dedup.window_key(MATCH) == f"dedup:{RULE.id}:{'a' * 64}"


async def test_repeat_counts_the_occurrence_on_the_held_alert_at_the_event_time() -> None:
    windows = RecordingWindows()

    outcome = await dedup.repeat(MATCH, dedup.Held(key=KEY, alert_id=ALERT_ID), windows)

    assert outcome == Repeated(alert_id=ALERT_ID, match=MATCH)
    assert windows.calls == [("increment", str(ALERT_ID), NOW.isoformat())]


async def test_confirm_stores_the_alert_in_a_won_window() -> None:
    windows = RecordingWindows()

    await dedup.confirm(dedup.Won(key=KEY), Opened(alert_id=ALERT_ID, match=MATCH), windows)

    assert windows.calls == [("confirm", KEY, str(ALERT_ID))]


@pytest.mark.parametrize("claim", OTHER_CLAIMS, ids=["held", "pending", "unavailable"])
async def test_confirm_leaves_other_windows_alone(claim: dedup.Claim) -> None:
    windows = RecordingWindows()

    await dedup.confirm(claim, Opened(alert_id=ALERT_ID, match=MATCH), windows)

    assert windows.calls == []


async def test_release_frees_a_won_window() -> None:
    windows = RecordingWindows()

    await dedup.release(dedup.Won(key=KEY), windows)

    assert windows.calls == [("release", KEY)]


@pytest.mark.parametrize("claim", OTHER_CLAIMS, ids=["held", "pending", "unavailable"])
async def test_release_leaves_other_windows_alone(claim: dedup.Claim) -> None:
    windows = RecordingWindows()

    await dedup.release(claim, windows)

    assert windows.calls == []
