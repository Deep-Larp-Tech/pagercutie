"""Step attempts: the `running` mark and idempotency key, the error bound, timeouts, false guards, stale outcomes and
steps in flight when the alert is resolved (ADR-0106, ADR-0107, ADR-0109)."""

import asyncio
import dataclasses
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from tests.integration.pipeline.test_executor_loop import (
    CONFIG,
    LEASE,
    NOW,
    PAST,
    FakeHttp,
    at_now,
    audit,
    claim,
    make_run,
    rows,
    set_step,
)
from tests.integration.pipeline.test_executor_retry import RETRY_STEPS

from pagercutie.alerts.models import Alert, RunbookRun, StepRun
from pagercutie.alerts.schemas import AlertStatus, Resolution, StepStatus
from pagercutie.alerts.service import close_run
from pagercutie.audit.models import AuditEntry
from pagercutie.audit.schemas import AuditAction
from pagercutie.pipeline.executor import worker
from pagercutie.pipeline.executor.actions import Integrations, SimulatedOps
from pagercutie.pipeline.executor.outcomes import GuardPending, RetryFailed, RetryWatched, StepFailed, StepSucceeded
from pagercutie.pipeline.executor.perform import Settle
from pagercutie.pipeline.executor.stage import claim_due_steps, complete_step, plan_step, start_step
from pagercutie.rules.models import Rule
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.steps import HttpGet, OpenTicket, Step, StepGuard
from pagercutie.teams.models import Team

pytestmark = pytest.mark.anyio

TICKET: list[Step] = [OpenTicket(action="open_ticket", title="Settlement stuck"), HttpGet(action="http_get", url="h")]


@pytest.fixture
async def team(session: AsyncSession) -> Team:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    return team


def clock(at: datetime) -> worker.Clock:
    return lambda: at


class LostReplicaOps(SimulatedOps):
    """Acts, then raises once, as a replica that dies after the action and before the outcome is written."""

    def __init__(self) -> None:
        super().__init__()
        self.keys: list[uuid.UUID] = []
        self.lost = False

    async def open_ticket(self, title: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
        self.keys.append(idempotency_key)
        result = await super().open_ticket(title, idempotency_key)
        if not self.lost:
            self.lost = True
            raise RuntimeError("replica lost")
        return result


async def test_a_lost_completion_repeats_the_action_with_the_same_idempotency_key(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], team: Team
) -> None:
    run_id, _, _ = await make_run(session, team, TICKET)
    ops = LostReplicaOps()
    integrations = Integrations(http=FakeHttp(), ops=ops)

    assert await worker.process_due(sessionmaker, integrations, CONFIG, at_now) == 1
    first = (await rows(session, run_id))[0]
    assert (first.status, first.lease_until) == (StepStatus.RUNNING, NOW + LEASE)
    key = first.attempt_key
    assert key is not None

    assert await worker.process_due(sessionmaker, integrations, CONFIG, clock(NOW + LEASE)) == 1

    first = (await rows(session, run_id))[0]
    assert (first.status, first.attempts, first.errors, first.attempt_key) == (StepStatus.SUCCEEDED, 1, 1, key)
    assert ops.keys == [key, key]
    assert ops.performed == ["Simulated: ticket 'Settlement stuck' opened"]
    assert [action for action, _ in await audit(session, run_id)] == [
        AuditAction.STEP_STARTED,
        AuditAction.STEP_SUCCEEDED,
    ]


async def test_a_step_whose_claims_keep_ending_without_an_outcome_fails_at_the_bound(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], team: Team
) -> None:
    run_id, _, _ = await make_run(
        session, team, [HttpGet(action="http_get", url="a"), HttpGet(action="http_get", url="b")]
    )
    http = FakeHttp(error=RuntimeError("poison"))
    integrations = Integrations(http=http, ops=SimulatedOps())
    config = dataclasses.replace(CONFIG, max_errors=3)

    for attempt in range(4):
        assert await worker.process_due(sessionmaker, integrations, config, clock(NOW + attempt * LEASE)) == 1

    first, second = await rows(session, run_id)
    assert http.calls == ["a", "a", "a"]
    assert (first.status, first.failures, first.errors, first.lease_until) == (StepStatus.FAILED, 1, 3, None)
    assert first.result == "Gave up after 3 attempts that ended without an outcome"
    assert second.run_at == NOW + 3 * LEASE
    assert (await audit(session, run_id))[-1] == (
        AuditAction.STEP_FAILED,
        {
            "index": 0,
            "status": "failed",
            "result": "Gave up after 3 attempts that ended without an outcome",
            "reason": "errors",
            "errors": 3,
        },
    )


async def test_advancing_to_a_leased_step_keeps_its_lease_and_its_outcome_is_written(
    session: AsyncSession, team: Team
) -> None:
    run_id, _, _ = await make_run(session, team, [HttpGet(action="http_get", url=u) for u in ("a", "b", "c")])
    await set_step(session, run_id, 1, run_at=PAST)
    first, second = sorted(await claim_due_steps(session, 10, NOW, LEASE), key=lambda job: job.index)

    await complete_step(session, first, StepSucceeded("HTTP 200"), NOW + timedelta(seconds=1))

    step = (await rows(session, run_id))[1]
    assert (step.run_at, step.lease_until) == (NOW + timedelta(seconds=1), second.lease)
    assert await claim_due_steps(session, 10, NOW + timedelta(seconds=2), LEASE) == []
    await complete_step(session, second, StepSucceeded("HTTP 200"), NOW + timedelta(seconds=2))
    assert [s.status for s in await rows(session, run_id)] == [StepStatus.SUCCEEDED] * 2 + [StepStatus.PENDING]


async def test_a_failure_counted_during_a_guard_check_makes_the_guarded_step_due_again(
    session: AsyncSession, team: Team
) -> None:
    run_id, _, _ = await make_run(session, team, RETRY_STEPS)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    await set_step(session, run_id, 1, status=StepStatus.SUCCEEDED, occurrences_at_run=1, failures=1)
    guarded = await claim(session, run_id, 2)
    assert plan_step(guarded, CONFIG.max_errors) == Settle(GuardPending())
    # Meanwhile the retry counts its second failure and moves the run on.
    retry = dataclasses.replace(guarded, index=1, status=StepStatus.SUCCEEDED, step=RETRY_STEPS[1], due_at=PAST)
    await set_step(session, run_id, 1, lease_until=retry.lease, run_at=PAST, failures=1)
    await complete_step(session, retry, RetryFailed(StepSucceeded("again")), NOW + timedelta(seconds=1))

    await complete_step(session, guarded, GuardPending(), NOW + timedelta(seconds=2))

    escalate = (await rows(session, run_id))[2]
    assert (escalate.status, escalate.run_at, escalate.lease_until) == (
        StepStatus.PENDING,
        NOW + timedelta(seconds=1),
        None,
    )
    (job,) = await claim_due_steps(session, 10, NOW + timedelta(seconds=3), LEASE)
    assert (job.index, job.failures(1)) == (2, 2)


async def test_a_false_guard_skips_its_step_and_the_run_finishes(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], team: Team
) -> None:
    steps: list[Step] = [
        HttpGet(action="http_get", url="a"),
        OpenTicket(action="open_ticket", title="t", if_=StepGuard(step=0, failures_gte=2)),
        HttpGet(action="http_get", url="c"),
    ]
    run_id, _, _ = await make_run(session, team, steps)
    http = FakeHttp()
    integrations = Integrations(http=http, ops=SimulatedOps())

    for _ in range(3):
        assert await worker.process_due(sessionmaker, integrations, CONFIG, at_now) == 1

    assert [s.status for s in await rows(session, run_id)] == [
        StepStatus.SUCCEEDED,
        StepStatus.SKIPPED,
        StepStatus.SUCCEEDED,
    ]
    assert http.calls == ["a", "c"]
    entries = await audit(session, run_id)
    assert (
        AuditAction.STEP_SKIPPED,
        {
            "index": 1,
            "status": "skipped",
            "result": "Guard not met: step 1 failed 0 of the 2 times needed",
            "reason": "guard_false",
        },
    ) in entries
    assert entries[-1] == (AuditAction.RUNBOOK_RUN_FINISHED, {"steps": 3})
    assert (await session.get_one(RunbookRun, run_id, populate_existing=True)).finished_at == NOW


async def test_a_guard_on_a_watched_retry_waits_instead_of_skipping(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team, RETRY_STEPS)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    await set_step(session, run_id, 1, status=StepStatus.SUCCEEDED, occurrences_at_run=1, run_at=None)
    job = await claim(session, run_id, 2)

    assert plan_step(job, CONFIG.max_errors) == Settle(GuardPending())


async def test_a_stale_outcome_of_an_action_that_ran_is_audited_as_discarded(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team, TICKET)
    job = await claim(session, run_id, 0)
    started = await start_step(session, job, NOW)
    assert started is not None
    await set_step(session, run_id, 0, lease_until=NOW + timedelta(seconds=45))

    await complete_step(session, started.job, StepSucceeded("ticket opened"), NOW + timedelta(seconds=40))

    first = (await rows(session, run_id))[0]
    assert (first.status, first.attempts, first.result) == (StepStatus.RUNNING, 0, None)
    assert (await audit(session, run_id))[-1] == (
        AuditAction.STEP_SUCCEEDED,
        {
            "index": 0,
            "status": "succeeded",
            "result": "ticket opened",
            "discarded": True,
            "attempt_key": str(started.key),
        },
    )


async def test_a_stale_outcome_without_an_action_is_not_audited(session: AsyncSession, team: Team) -> None:
    run_id, _, _ = await make_run(session, team, TICKET)
    job = await claim(session, run_id, 0)
    await set_step(session, run_id, 0, lease_until=NOW + timedelta(seconds=45))

    await complete_step(session, job, StepSucceeded("ticket opened"), NOW)

    assert await audit(session, run_id) == []


async def test_an_action_slower_than_the_step_timeout_fails_as_timed_out(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], team: Team
) -> None:
    class SlowOps(SimulatedOps):
        async def open_ticket(self, title: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
            await asyncio.sleep(5)
            return StepSucceeded("late")

    run_id, _, _ = await make_run(session, team, TICKET)
    config = dataclasses.replace(CONFIG, step_timeout_seconds=0.05)

    assert await worker.process_due(sessionmaker, Integrations(http=FakeHttp(), ops=SlowOps()), config, at_now) == 1

    first, second = await rows(session, run_id)
    assert (first.status, first.failures, first.result) == (StepStatus.FAILED, 1, "Timed out after 0.05 s")
    assert second.run_at == NOW
    assert (await audit(session, run_id))[-1][1]["reason"] == "timed_out"


async def resolve(session: AsyncSession, alert_id: uuid.UUID) -> Alert:
    await session.execute(
        update(Alert)
        .where(Alert.id == alert_id)
        .values(status=AlertStatus.RESOLVED, resolved_at=NOW, resolution=Resolution.AUTO)
    )
    alert = await session.get_one(Alert, alert_id, populate_existing=True)
    await close_run(session, None, alert)
    await session.flush()
    return alert


async def test_resolving_while_an_action_runs_records_its_real_outcome(session: AsyncSession, team: Team) -> None:
    run_id, alert_id, _ = await make_run(session, team, TICKET)
    started = await start_step(session, await claim(session, run_id, 0), NOW)
    assert started is not None

    await resolve(session, alert_id)
    assert [s.status for s in await rows(session, run_id)] == [StepStatus.RUNNING, StepStatus.SKIPPED]
    await complete_step(session, started.job, StepSucceeded("ticket opened"), NOW + timedelta(seconds=1))

    assert [s.status for s in await rows(session, run_id)] == [StepStatus.SUCCEEDED, StepStatus.SKIPPED]
    assert [(action, data.get("index")) for action, data in await audit(session, run_id)] == [
        (AuditAction.STEP_STARTED, 0),
        (AuditAction.STEP_SKIPPED, 1),
        (AuditAction.STEP_SUCCEEDED, 0),
        (AuditAction.RUNBOOK_RUN_FINISHED, None),
    ]


async def test_a_running_action_whose_replica_was_lost_after_the_resolve_fails_as_unknown(
    session: AsyncSession, team: Team
) -> None:
    run_id, alert_id, _ = await make_run(session, team, TICKET)
    assert await start_step(session, await claim(session, run_id, 0), NOW) is not None
    await resolve(session, alert_id)

    assert await claim_due_steps(session, 10, NOW + LEASE, LEASE) == []

    first = (await rows(session, run_id))[0]
    assert (first.status, first.run_at, first.lease_until) == (StepStatus.FAILED, None, None)
    assert first.result is not None
    assert first.result.startswith("Outcome unknown")
    assert [action for action, _ in await audit(session, run_id)][-2:] == [
        AuditAction.STEP_FAILED,
        AuditAction.RUNBOOK_RUN_FINISHED,
    ]


async def test_a_late_count_after_watching_stopped_changes_nothing(session: AsyncSession, team: Team) -> None:
    run_id, alert_id, _ = await make_run(session, team, RETRY_STEPS)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    await set_step(session, run_id, 1, status=StepStatus.SUCCEEDED, occurrences_at_run=1, acted_at=PAST)
    await set_step(session, run_id, 2, status=StepStatus.SKIPPED)
    await complete_step(session, await claim(session, run_id, 1), RetryWatched(), NOW)
    assert (await rows(session, run_id))[1].run_at is None

    await session.execute(update(Alert).where(Alert.id == alert_id).values(occurrences=3, last_seen_at=NOW))

    assert await claim_due_steps(session, 10, NOW + timedelta(minutes=1), LEASE) == []
    retry = (await rows(session, run_id))[1]
    assert (retry.status, retry.failures, retry.attempts) == (StepStatus.SUCCEEDED, 0, 0)


async def test_a_late_count_of_occurrences_before_the_attempt_only_moves_the_baseline(
    session: AsyncSession, team: Team
) -> None:
    run_id, alert_id, _ = await make_run(session, team, RETRY_STEPS)
    await set_step(session, run_id, 0, status=StepStatus.SUCCEEDED)
    await set_step(session, run_id, 1, status=StepStatus.SUCCEEDED, occurrences_at_run=1, acted_at=PAST)
    await session.execute(update(Alert).where(Alert.id == alert_id).values(occurrences=3, last_seen_at=PAST))
    job = await claim(session, run_id, 1)

    assert plan_step(job, CONFIG.max_errors) == Settle(RetryWatched(baseline=3))
    await complete_step(session, job, RetryWatched(baseline=3), NOW)

    retry = (await rows(session, run_id))[1]
    assert (retry.status, retry.failures, retry.occurrences_at_run) == (StepStatus.SUCCEEDED, 0, 3)
    assert await audit(session, run_id) == []


class GatedOps(SimulatedOps):
    """`open_ticket` waits until `release` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

    async def open_ticket(self, title: str, idempotency_key: uuid.UUID) -> StepSucceeded | StepFailed:
        await self.release.wait()
        return await super().open_ticket(title, idempotency_key)


@pytest.fixture
async def committed_runs(engine: AsyncEngine) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """A slow run (`open_ticket`) and a fast run (`http_get`), committed so the loop's own sessions see them."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        team = Team(slug=f"loop-{uuid.uuid7().hex[:8]}", name="Loop")
        session.add(team)
        await session.flush()
        slow, slow_alert, slow_opened = await make_run(session, team, [OpenTicket(action="open_ticket", title="t")])
        fast, fast_alert, fast_opened = await make_run(
            session, team, [HttpGet(action="http_get", url="fast")], fingerprint="b" * 64
        )
        await session.commit()
    yield slow, fast
    async with AsyncSession(engine) as session, session.begin():
        runbook_ids = list(await session.scalars(select(RunbookRun.runbook_id).where(RunbookRun.id.in_([slow, fast]))))
        await session.execute(delete(AuditEntry).where(AuditEntry.team_id == team.id))
        await session.execute(delete(RunbookRun).where(RunbookRun.id.in_([slow, fast])))
        await session.execute(delete(Alert).where(Alert.id.in_([slow_alert, fast_alert])))
        await session.execute(delete(Rule).where(Rule.id.in_([slow_opened.match.rule.id, fast_opened.match.rule.id])))
        await session.execute(delete(Runbook).where(Runbook.id.in_(runbook_ids)))
        await session.execute(delete(Team).where(Team.id == team.id))


async def test_a_slow_step_does_not_hold_up_another_steps_completion(
    engine: AsyncEngine, committed_runs: tuple[uuid.UUID, uuid.UUID]
) -> None:
    slow, fast = committed_runs
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ops = GatedOps()
    stopping = asyncio.Event()
    loop = worker.executor_loop(sessionmaker, Integrations(http=FakeHttp(), ops=ops), asyncio.Event(), CONFIG)
    task = asyncio.ensure_future(loop(stopping))

    async def status(run_id: uuid.UUID) -> StepStatus | None:
        async with sessionmaker() as session:
            return await session.scalar(select(StepRun.status).where(StepRun.run_id == run_id))

    try:
        for _ in range(100):
            if await status(fast) is StepStatus.SUCCEEDED:
                break
            await asyncio.sleep(0.05)
        assert await status(fast) is StepStatus.SUCCEEDED
        assert await status(slow) is StepStatus.RUNNING
    finally:
        ops.release.set()
        stopping.set()
        await asyncio.wait_for(task, 5)
    assert await status(slow) is StepStatus.SUCCEEDED
