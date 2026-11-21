import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import AlertStatus, DeliveryStatus, Resolution
from pagercutie.alerts.service import AlertChanged
from pagercutie.core.db import NotifyChannel, create_sessionmaker, notify
from pagercutie.core.enums import Channel, Severity
from pagercutie.core.settings import Settings
from pagercutie.main import create_app
from pagercutie.pipeline.dispatch import metrics, state, worker
from pagercutie.pipeline.dispatch.fallback import FellBack, Unreachable, fallback_id
from pagercutie.pipeline.dispatch.stage import (
    DIGEST_EMPTIED,
    Completion,
    DeliveryJob,
    Digest,
    GaveUp,
    LeaseLost,
    SendFailed,
    SendResult,
    Sent,
    Throttled,
    cancel_for_resolved_alerts,
    claim_due,
    complete,
    retry_delay,
)
from pagercutie.pipeline.dispatch.worker import MAX_CONCURRENT_SENDS, DispatchContext, dispatch_loop, dispatch_once
from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.rules.ast import Compare
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, UserRecipient
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
LEASE = timedelta(seconds=30)
REFILL = timedelta(seconds=12)


class AlwaysAllow:
    async def allow(self, user_id: uuid.UUID) -> bool:
        return True

    async def refund(self, user_id: uuid.UUID) -> None:
        pass


@dataclass(frozen=True)
class World:
    """A recipient and an alert the deliveries of a test hang off."""

    user_id: uuid.UUID
    rule_id: uuid.UUID
    alert_id: uuid.UUID


async def create_world(session: AsyncSession) -> World:
    user = User(email=f"{uuid.uuid4()}@example.com", display_name="Anna", timezone="UTC", role=GlobalRole.USER)
    session.add(user)
    await session.flush()
    rule = Rule(
        name="Workflow failed",
        enabled=True,
        team_id=None,
        user_id=user.id,
        schema_ids=[],
        condition=Compare(op="eq", field="payload.type", value="failed"),
        dedup=Dedup(fields=[]),
        routing=Routing(recipients=[UserRecipient(type="user", user_id=user.id)]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR, colour=Colour.RED),
    )
    session.add(rule)
    await session.flush()
    alert = Alert(
        rule_id=rule.id,
        team_id=None,
        fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,
        status=AlertStatus.OPEN,
        severity=Severity.ERROR,
        colour=Colour.RED,
        title="Failed",
        fields=[],
        occurrences=1,
        notified_at=NOW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        escalated_team_ids=[],
        payload={},
    )
    session.add(alert)
    await session.flush()
    return World(user_id=user.id, rule_id=rule.id, alert_id=alert.id)


@pytest.fixture
async def world(session: AsyncSession) -> World:
    return await create_world(session)


@pytest.fixture
async def committed_world(engine: AsyncEngine) -> AsyncIterator[World]:
    """Committed rows, for tests that need several connections; removed afterwards."""
    async with async_sessionmaker(engine, expire_on_commit=False)() as session, session.begin():
        world = await create_world(session)
    yield world
    async with async_sessionmaker(engine)() as session, session.begin():
        await session.execute(update(Delivery).where(Delivery.alert_id == world.alert_id).values(digest_id=None))
        await session.execute(delete(Delivery).where(Delivery.alert_id == world.alert_id))
        await session.execute(delete(Alert).where(Alert.id == world.alert_id))
        await session.execute(delete(Rule).where(Rule.id == world.rule_id))
        await session.execute(delete(User).where(User.id == world.user_id))


def add_delivery(
    session: AsyncSession,
    world: World,
    *,
    channel: Channel = Channel.SMS,
    status: DeliveryStatus = DeliveryStatus.PENDING,
    attempts: int = 0,
    retry_at: datetime | None = None,
    lease_until: datetime | None = None,
    digest_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    message: str = "Workflow failed",
    age: int = 0,
    received_before_created: timedelta = timedelta(seconds=5),
) -> uuid.UUID:
    """`age` orders the rows: a larger one was created earlier. Ingest received the event before it created the row."""
    delivery = Delivery(
        id=uuid.uuid7(),
        alert_id=world.alert_id,
        user_id=user_id or world.user_id,
        channel=channel,
        status=status,
        attempts=attempts,
        message=message,
        received_at=NOW - timedelta(minutes=age) - received_before_created,
        retry_at=retry_at,
        lease_until=lease_until,
        digest_id=digest_id,
    )
    delivery.created_at = NOW - timedelta(minutes=age)
    session.add(delivery)
    return delivery.id


async def fetch(session: AsyncSession, delivery_id: uuid.UUID) -> Delivery:
    result = await session.execute(
        select(Delivery).where(Delivery.id == delivery_id).execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def claim(session: AsyncSession, now: datetime = NOW, limit: int = 100) -> list[DeliveryJob]:
    return await claim_due(session, limit, now, LEASE)


async def claim_one(session: AsyncSession, delivery_id: uuid.UUID, now: datetime = NOW) -> DeliveryJob:
    await session.flush()
    jobs = {job.delivery_id: job for job in await claim(session, now)}
    return jobs[delivery_id]


async def finish(session: AsyncSession, job: DeliveryJob, result: SendResult, now: datetime = NOW) -> Completion:
    completion = await complete(session, job, result, now, REFILL)
    metrics.record_completion(completion)
    return completion


async def test_claim_leases_the_due_deliveries_oldest_first(session: AsyncSession, world: World) -> None:
    past, future = NOW - timedelta(seconds=1), NOW + timedelta(seconds=1)
    new = add_delivery(session, world, age=1)
    old = add_delivery(session, world, age=3)
    retry_due = add_delivery(session, world, age=2, retry_at=past)
    failed_due = add_delivery(session, world, age=4, status=DeliveryStatus.FAILED, retry_at=past)
    not_due = [
        add_delivery(session, world, retry_at=future),
        add_delivery(session, world, status=DeliveryStatus.FAILED, retry_at=future),
        add_delivery(session, world, status=DeliveryStatus.FAILED),
        add_delivery(session, world, status=DeliveryStatus.SENT),
        add_delivery(session, world, lease_until=future),
        add_delivery(session, world, digest_id=old),
    ]
    await session.flush()

    jobs = await claim(session)

    mine = [job for job in jobs if job.delivery_id in {new, old, retry_due, failed_due, *not_due}]
    assert [job.delivery_id for job in mine] == [failed_due, old, retry_due, new]
    assert {job.lease_until for job in mine} == {NOW + LEASE}
    assert (await fetch(session, new)).lease_until == NOW + LEASE
    assert (await fetch(session, not_due[0])).lease_until is None


async def test_claim_respects_the_limit(session: AsyncSession, world: World) -> None:
    ids = [add_delivery(session, world, age=age) for age in (3, 2, 1)]
    await session.flush()

    jobs = await claim(session, limit=2)

    assert [job.delivery_id for job in jobs if job.delivery_id in ids] == ids[:2]


async def test_an_expired_lease_is_claimed_again(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world)
    await session.flush()
    first = await claim_one(session, delivery_id)

    assert delivery_id not in [job.delivery_id for job in await claim(session, NOW + timedelta(seconds=29))]
    second = await claim_one(session, delivery_id, NOW + LEASE + timedelta(seconds=1))

    assert second.lease_until == NOW + LEASE + LEASE + timedelta(seconds=1)
    assert second.lease_until != first.lease_until


async def test_two_claimers_never_get_the_same_delivery(engine: AsyncEngine, committed_world: World) -> None:
    async with async_sessionmaker(engine, expire_on_commit=False)() as setup, setup.begin():
        ids = {add_delivery(setup, committed_world, age=age) for age in range(4)}

    async with engine.connect() as first_connection, engine.connect() as second_connection:
        first_tx, second_tx = await first_connection.begin(), await second_connection.begin()
        first = AsyncSession(first_connection, expire_on_commit=False)
        second = AsyncSession(second_connection, expire_on_commit=False)
        first_jobs = await claim_due(first, 2, NOW, LEASE)
        second_jobs = await claim_due(second, 10, NOW, LEASE)
        await first_tx.commit()
        await second_tx.commit()
        await first.close()
        await second.close()

    first_ids = {job.delivery_id for job in first_jobs} & ids
    second_ids = {job.delivery_id for job in second_jobs} & ids
    assert len(first_ids) == 2
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == ids


async def test_sent_ends_the_lease(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world, attempts=1, retry_at=NOW, message="m")
    job = await claim_one(session, delivery_id)

    await finish(session, job, Sent(at=NOW + timedelta(seconds=2)))

    delivery = await fetch(session, delivery_id)
    assert (delivery.status, delivery.attempts, delivery.sent_at) == (
        DeliveryStatus.SENT,
        2,
        NOW + timedelta(seconds=2),
    )
    assert (delivery.lease_until, delivery.retry_at, delivery.last_error) == (None, None, None)


class LatencyRecorder:
    """Stands in for the `end_to_end_latency_seconds` histogram."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    def record(self, amount: float, attributes: Mapping[str, str]) -> None:
        self.seconds.append(amount)


@pytest.fixture
def latency(monkeypatch: pytest.MonkeyPatch) -> LatencyRecorder:
    recorder = LatencyRecorder()
    monkeypatch.setattr(metrics, "_latency", recorder)
    return recorder


async def test_latency_runs_from_the_event_not_from_the_delivery_row(
    session: AsyncSession, world: World, latency: LatencyRecorder
) -> None:
    delivery_id = add_delivery(session, world, received_before_created=timedelta(seconds=60))
    job = await claim_one(session, delivery_id)

    await finish(session, job, Sent(at=NOW + timedelta(seconds=2)))

    assert latency.seconds == [62.0]


async def test_a_digest_takes_the_oldest_received_at_and_records_each_members_latency(
    session: AsyncSession, world: World, latency: LatencyRecorder
) -> None:
    members = [add_delivery(session, world, age=2), add_delivery(session, world, age=1)]
    await throttle_all(session, members)
    digest_id = (await fetch(session, members[0])).digest_id
    assert digest_id is not None
    assert (await fetch(session, digest_id)).received_at == (await fetch(session, members[0])).received_at
    jobs = {job.delivery_id: job for job in await claim(session, NOW + REFILL)}

    await finish(session, jobs[digest_id], Sent(at=NOW + REFILL + timedelta(seconds=1)), NOW + REFILL)

    assert sorted(latency.seconds) == [78.0, 138.0]


async def test_a_late_result_from_the_old_claimant_is_ignored(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world)
    old_claim = await claim_one(session, delivery_id)
    new_claim = await claim_one(session, delivery_id, NOW + LEASE + timedelta(seconds=1))

    await finish(session, old_claim, SendFailed(error="late"), NOW + LEASE + timedelta(seconds=2))
    await finish(session, old_claim, Sent(at=NOW))

    delivery = await fetch(session, delivery_id)
    assert (delivery.status, delivery.attempts, delivery.last_error) == (DeliveryStatus.PENDING, 0, None)
    assert delivery.lease_until == new_claim.lease_until

    await finish(session, new_claim, Sent(at=NOW))

    assert (await fetch(session, delivery_id)).status == DeliveryStatus.SENT


@pytest.mark.parametrize("attempts", range(11))
async def test_a_failure_backs_off_exponentially_up_to_five_minutes(
    session: AsyncSession, world: World, attempts: int
) -> None:
    delivery_id = add_delivery(session, world, attempts=attempts)
    job = await claim_one(session, delivery_id)

    await finish(session, job, SendFailed(error="smtp down"))

    delivery = await fetch(session, delivery_id)
    expected = min(2**attempts, 300)
    assert retry_delay(attempts) == timedelta(seconds=expected)
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.attempts == attempts + 1
    assert delivery.last_error == "smtp down"
    assert delivery.lease_until is None
    assert delivery.retry_at == NOW + timedelta(seconds=expected)


async def test_a_failed_delivery_is_claimed_again_once_retry_at_passes(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world)
    job = await claim_one(session, delivery_id)
    await finish(session, job, SendFailed(error="smtp down"))

    assert delivery_id not in [job.delivery_id for job in await claim(session, NOW)]
    again = await claim_one(session, delivery_id, NOW + timedelta(seconds=1))

    assert again.attempts == 1


async def test_a_permanent_failure_is_never_claimed_again(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world)
    job = await claim_one(session, delivery_id)

    await finish(session, job, SendFailed(error="no phone number", permanent=True))

    delivery = await fetch(session, delivery_id)
    assert (delivery.status, delivery.retry_at, delivery.lease_until) == (DeliveryStatus.UNDELIVERABLE, None, None)
    assert delivery_id not in [job.delivery_id for job in await claim(session, NOW + timedelta(days=365))]


async def test_a_throttled_delivery_stays_pending_until_the_next_token(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world, attempts=2)
    job = await claim_one(session, delivery_id)

    await finish(session, job, Throttled())

    delivery = await fetch(session, delivery_id)
    assert (delivery.status, delivery.attempts, delivery.lease_until) == (DeliveryStatus.PENDING, 2, None)
    assert delivery.retry_at == NOW + REFILL
    assert delivery.digest_id is None
    assert delivery_id not in [job.delivery_id for job in await claim(session, NOW + REFILL - timedelta(seconds=1))]
    assert delivery_id in [job.delivery_id for job in await claim(session, NOW + REFILL)]


async def throttle_all(session: AsyncSession, ids: Sequence[uuid.UUID]) -> None:
    """Claims the deliveries together, like one batch, then completes them as throttled one by one."""
    await session.flush()
    jobs = {job.delivery_id: job for job in await claim(session)}
    for delivery_id in ids:
        await finish(session, jobs[delivery_id], Throttled())


async def test_throttled_deliveries_of_one_recipient_and_channel_merge_into_one_digest(
    session: AsyncSession, world: World
) -> None:
    other_user = (await create_world(session)).user_id
    members = [
        add_delivery(session, world, age=3, message="Failed: a\nbody"),
        add_delivery(session, world, age=2, message="Failed: b"),
        add_delivery(session, world, age=1, message="Failed: c"),
    ]
    other_channel = add_delivery(session, world, channel=Channel.EMAIL)
    other_recipient = add_delivery(session, world, user_id=other_user)

    await throttle_all(session, [*members, other_channel, other_recipient])

    digests = (
        (
            await session.execute(
                select(Delivery).where(
                    Delivery.id.not_in([*members, other_channel, other_recipient]), Delivery.alert_id == world.alert_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(digests) == 1
    digest = digests[0]
    assert (digest.user_id, digest.channel, digest.status, digest.attempts) == (
        world.user_id,
        Channel.SMS,
        DeliveryStatus.PENDING,
        0,
    )
    assert digest.retry_at == NOW + REFILL
    assert digest.message == "3 notifications held back by the rate limit:\n- Failed: a\n- Failed: b\n- Failed: c"
    assert {(await fetch(session, member)).digest_id for member in members} == {digest.id}
    assert (await fetch(session, other_channel)).digest_id is None
    assert (await fetch(session, other_recipient)).digest_id is None
    assert digest.id == uuid.uuid5(
        uuid.uuid5(uuid.NAMESPACE_DNS, "digest.pagercutie"), ",".join(sorted(map(str, members[:2])))
    )


async def test_a_lone_throttled_delivery_makes_no_digest(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world)
    await throttle_all(session, [delivery_id])

    count = (await session.execute(select(Delivery.id).where(Delivery.alert_id == world.alert_id))).all()
    assert len(count) == 1


async def test_later_throttled_deliveries_join_the_open_digest(session: AsyncSession, world: World) -> None:
    first = [add_delivery(session, world, age=3), add_delivery(session, world, age=2)]
    await throttle_all(session, first)
    late = add_delivery(session, world, age=1, message="Failed: late")
    await throttle_all(session, [late])

    digest_id = (await fetch(session, late)).digest_id
    assert digest_id is not None
    assert {(await fetch(session, member)).digest_id for member in first} == {digest_id}
    assert (await fetch(session, digest_id)).message.splitlines()[0] == "3 notifications held back by the rate limit:"
    assert (await fetch(session, digest_id)).message.endswith("- Failed: late")


async def test_members_are_marked_sent_when_the_digest_is(session: AsyncSession, world: World) -> None:
    members = [add_delivery(session, world, age=2), add_delivery(session, world, age=1)]
    await throttle_all(session, members)
    digest_id = (await fetch(session, members[0])).digest_id
    assert digest_id is not None

    assert not {job.delivery_id for job in await claim(session, NOW + REFILL - timedelta(seconds=1))} & set(members)
    jobs = {job.delivery_id: job for job in await claim(session, NOW + REFILL)}
    assert set(members).isdisjoint(jobs)
    sent_at = NOW + REFILL + timedelta(seconds=1)
    await finish(session, jobs[digest_id], Sent(at=sent_at), NOW + REFILL)

    digest = await fetch(session, digest_id)
    assert (digest.status, digest.attempts) == (DeliveryStatus.SENT, 1)
    for member in members:
        row = await fetch(session, member)
        assert (row.status, row.sent_at, row.attempts, row.digest_id) == (DeliveryStatus.SENT, sent_at, 0, digest_id)


async def test_members_fail_with_a_digest_that_can_never_be_sent(session: AsyncSession, world: World) -> None:
    members = [add_delivery(session, world, age=2), add_delivery(session, world, age=1)]
    await throttle_all(session, members)
    digest_id = (await fetch(session, members[0])).digest_id
    assert digest_id is not None
    jobs = {job.delivery_id: job for job in await claim(session, NOW + REFILL)}

    await finish(session, jobs[digest_id], SendFailed(error="no phone number", permanent=True), NOW + REFILL)

    for member in members:
        row = await fetch(session, member)
        assert (row.status, row.last_error, row.retry_at) == (DeliveryStatus.UNDELIVERABLE, "no phone number", None)


async def test_a_burst_completed_concurrently_ends_in_one_digest(engine: AsyncEngine, committed_world: World) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as setup, setup.begin():
        ids = {add_delivery(setup, committed_world, age=age) for age in range(20)}
    async with sessionmaker() as setup, setup.begin():
        jobs = [job for job in await claim(setup) if job.delivery_id in ids]

    async def throttle(job: DeliveryJob) -> None:
        async with sessionmaker() as session, session.begin():
            await finish(session, job, Throttled())

    await asyncio.gather(*(throttle(job) for job in jobs))

    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(Delivery).where(Delivery.alert_id == committed_world.alert_id)))
            .scalars()
            .all()
        )
    digests = [row for row in rows if row.id not in ids]
    assert len(jobs) == 20
    assert len(digests) == 1
    assert {row.digest_id for row in rows if row.id in ids} == {digests[0].id}
    assert digests[0].message.splitlines()[0] == "20 notifications held back by the rate limit:"


async def test_the_dispatch_loop_sends_a_delivery_after_a_wake(engine: AsyncEngine, committed_world: World) -> None:
    class RecordingAdapter:
        def __init__(self) -> None:
            self.sent: list[uuid.UUID] = []
            self.done = asyncio.Event()

        async def send(self, job: DeliveryJob) -> Sent:
            self.sent.append(job.delivery_id)
            self.done.set()
            return Sent(at=datetime.now(UTC))

    adapter = RecordingAdapter()
    sessionmaker = create_sessionmaker(engine)
    context = DispatchContext(
        sessionmaker=sessionmaker,
        adapters=dict.fromkeys(Channel, adapter),
        throttle=AlwaysAllow(),
        settings=Settings(),
        wake=asyncio.Event(),
    )
    stopping = asyncio.Event()
    loop = asyncio.create_task(dispatch_loop(context, stopping))
    await asyncio.sleep(0.2)
    async with sessionmaker() as session, session.begin():
        delivery_id = add_delivery(session, committed_world)
    context.wake.set()

    await asyncio.wait_for(adapter.done.wait(), timeout=0.6)
    stopping.set()
    await asyncio.wait_for(loop, timeout=2)

    async with sessionmaker() as session:
        delivery = await fetch(session, delivery_id)
    assert (delivery.status, delivery.attempts, delivery.lease_until) == (DeliveryStatus.SENT, 1, None)
    assert adapter.sent == [delivery_id]


async def test_a_batch_claims_no_more_deliveries_than_can_be_sent_at_once(
    engine: AsyncEngine, committed_world: World
) -> None:
    class SlowAdapter:
        def __init__(self) -> None:
            self.running = 0
            self.peak = 0
            self.sent: list[uuid.UUID] = []

        async def send(self, job: DeliveryJob) -> Sent:
            self.running += 1
            self.peak = max(self.peak, self.running)
            await asyncio.sleep(0.05)
            self.running -= 1
            self.sent.append(job.delivery_id)
            return Sent(at=datetime.now(UTC))

    adapter = SlowAdapter()
    sessionmaker = create_sessionmaker(engine)
    context = DispatchContext(
        sessionmaker=sessionmaker,
        adapters=dict.fromkeys(Channel, adapter),
        throttle=AlwaysAllow(),
        settings=Settings(delivery_batch_size=MAX_CONCURRENT_SENDS + 4),
        wake=asyncio.Event(),
    )
    async with sessionmaker() as session, session.begin():
        ids = {add_delivery(session, committed_world, age=age) for age in range(MAX_CONCURRENT_SENDS + 4)}

    assert await dispatch_once(context)
    assert len(adapter.sent) == MAX_CONCURRENT_SENDS
    assert adapter.peak == MAX_CONCURRENT_SENDS
    assert not await dispatch_once(context)
    assert set(adapter.sent) == ids


async def test_the_app_dispatches_a_delivery_on_a_deliveries_pending_notify(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, engine: AsyncEngine, database_url: str, committed_world: World
) -> None:
    monkeypatch.setattr(worker, "POLL_SECONDS", 60.0)
    app = create_app(settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"}))
    sessionmaker = create_sessionmaker(engine)
    sent: asyncio.Queue[str] = asyncio.Queue()

    async def deliver_and_wait() -> uuid.UUID:
        async with sessionmaker() as session, session.begin():
            delivery_id = add_delivery(session, committed_world, channel=Channel.UI)
            await notify(session, NotifyChannel.DELIVERIES_PENDING)
        payload = await asyncio.wait_for(sent.get(), timeout=5)
        assert AlertChanged.model_validate_json(payload).alert_id == committed_world.alert_id
        return delivery_id

    observer = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await observer.add_listener("alert_changed", lambda _conn, _pid, _channel, payload: sent.put_nowait(payload))
        async with app.router.lifespan_context(app):
            await deliver_and_wait()
            await asyncio.sleep(0.3)
            second = await deliver_and_wait()
        async with sessionmaker() as session:
            assert (await fetch(session, second)).status == DeliveryStatus.SENT
    finally:
        await observer.close()


async def resolve(session: AsyncSession, world: World) -> None:
    await session.execute(
        update(Alert)
        .where(Alert.id == world.alert_id)
        .values(status=AlertStatus.RESOLVED, resolved_at=NOW, resolution=Resolution.AUTO)
    )


async def test_a_resolved_alerts_unsent_deliveries_are_cancelled_and_never_sent(
    session: AsyncSession, world: World
) -> None:
    pending = add_delivery(session, world)
    retrying = add_delivery(session, world, status=DeliveryStatus.FAILED, attempts=9, retry_at=NOW)
    held_back = add_delivery(session, world, retry_at=NOW + REFILL)
    sent = add_delivery(session, world, status=DeliveryStatus.SENT)
    leased = add_delivery(session, world, lease_until=NOW + LEASE)
    await session.flush()
    await resolve(session, world)

    cancelled = await cancel_for_resolved_alerts(session, NOW, 100)

    assert sorted(cancelled) == [Channel.SMS] * 3
    for delivery_id in (pending, retrying, held_back):
        row = await fetch(session, delivery_id)
        assert (row.status, row.retry_at, row.last_error) == (
            DeliveryStatus.CANCELLED,
            None,
            "Alert resolved before the delivery was sent",
        )
    assert (await fetch(session, sent)).status == DeliveryStatus.SENT
    # The replica that holds it completes it; the next pass cancels it if it fails.
    assert (await fetch(session, leased)).status == DeliveryStatus.PENDING
    assert not {job.delivery_id for job in await claim(session, NOW + timedelta(days=1))} & {
        pending,
        retrying,
        held_back,
    }


async def test_an_acknowledged_alerts_deliveries_are_still_sent(session: AsyncSession, world: World) -> None:
    delivery_id = add_delivery(session, world)
    await session.flush()
    await session.execute(
        update(Alert).where(Alert.id == world.alert_id).values(status=AlertStatus.ACKNOWLEDGED, acknowledged_at=NOW)
    )

    assert await cancel_for_resolved_alerts(session, NOW, 100) == []
    assert delivery_id in {job.delivery_id for job in await claim(session)}


async def test_a_digest_whose_members_were_all_cancelled_is_cancelled_at_claim(
    session: AsyncSession, world: World
) -> None:
    members = [add_delivery(session, world, age=2), add_delivery(session, world, age=1)]
    await throttle_all(session, members)
    digest_id = (await fetch(session, members[0])).digest_id
    assert digest_id is not None
    await resolve(session, world)

    await cancel_for_resolved_alerts(session, NOW + REFILL, 100)
    jobs = await claim(session, NOW + REFILL)

    assert digest_id not in {job.delivery_id for job in jobs}
    digest = await fetch(session, digest_id)
    assert (digest.status, digest.last_error, digest.lease_until) == (DeliveryStatus.CANCELLED, DIGEST_EMPTIED, None)
    assert {(await fetch(session, member)).status for member in members} == {DeliveryStatus.CANCELLED}


async def test_a_digest_lists_and_completes_only_its_live_members(session: AsyncSession, world: World) -> None:
    other = await create_world(session)
    members = [
        add_delivery(session, world, age=3, message="Failed: a"),
        add_delivery(session, world, age=2, message="Failed: b"),
        add_delivery(session, other, age=1, message="Failed: c", user_id=world.user_id),
    ]
    await throttle_all(session, members)
    digest_id = (await fetch(session, members[0])).digest_id
    assert digest_id is not None
    await session.execute(
        update(Alert)
        .where(Alert.id == other.alert_id)
        .values(status=AlertStatus.RESOLVED, resolved_at=NOW, resolution=Resolution.MANUAL)
    )
    await cancel_for_resolved_alerts(session, NOW + REFILL, 100)

    job = {job.delivery_id: job for job in await claim(session, NOW + REFILL)}[digest_id]

    assert job.kind == Digest(member_ids=frozenset(members[:2]))
    assert job.message == "2 notifications held back by the rate limit:\n- Failed: a\n- Failed: b"
    assert (await fetch(session, digest_id)).message == job.message


async def test_digest_completion_marks_only_the_members_its_message_listed(session: AsyncSession, world: World) -> None:
    members = [add_delivery(session, world, age=3), add_delivery(session, world, age=2)]
    await throttle_all(session, members)
    digest_id = (await fetch(session, members[0])).digest_id
    assert digest_id is not None
    job = {job.delivery_id: job for job in await claim(session, NOW + REFILL)}[digest_id]
    # Joined after the claim composed the message, as when the lease expired mid-send.
    late = add_delivery(session, world, age=1, digest_id=digest_id)
    await session.flush()

    await finish(session, job, Sent(at=NOW + REFILL), NOW + REFILL)

    assert {(await fetch(session, member)).status for member in members} == {DeliveryStatus.SENT}
    late_row = await fetch(session, late)
    assert (late_row.status, late_row.digest_id) == (DeliveryStatus.PENDING, None)
    assert late in {job.delivery_id for job in await claim(session, NOW + REFILL)}


async def test_an_expired_digest_gains_no_members_while_it_may_still_be_sending(
    session: AsyncSession, world: World
) -> None:
    members = [add_delivery(session, world, age=3), add_delivery(session, world, age=2)]
    await throttle_all(session, members)
    digest_id = (await fetch(session, members[0])).digest_id
    assert digest_id is not None
    late = [add_delivery(session, world, age=1), add_delivery(session, world, age=0)]
    await session.flush()
    jobs = {job.delivery_id: job for job in await claim(session, NOW + REFILL)}
    assert digest_id in jobs
    after_expiry = NOW + REFILL + LEASE + timedelta(seconds=1)

    for delivery_id in late:
        await finish(session, jobs[delivery_id], Throttled(), after_expiry)

    late_digests = {(await fetch(session, delivery_id)).digest_id for delivery_id in late}
    assert len(late_digests) == 1
    assert late_digests.isdisjoint({None, digest_id})


async def set_preferences(session: AsyncSession, world: World, rules: list[dict[str, object]]) -> None:
    await session.execute(
        update(User)
        .where(User.id == world.user_id)
        .values(channel_preferences=ChannelPreferences.model_validate({"rules": rules}))
    )


async def test_a_permanent_failure_falls_back_to_the_next_preferred_channel_exactly_once(
    session: AsyncSession, world: World
) -> None:
    await set_preferences(session, world, [{"min_severity": "error", "channels": ["phone", "sms", "email"]}])
    phone = add_delivery(session, world, channel=Channel.PHONE)
    sms = add_delivery(session, world, channel=Channel.SMS, status=DeliveryStatus.SENT)
    job = await claim_one(session, phone)
    await session.execute(update(Delivery).where(Delivery.id == phone).values(traceparent="00-trace-span-01"))

    completion = await finish(session, job, SendFailed(error="User has no phone number", permanent=True))
    again = await finish(session, job, SendFailed(error="User has no phone number", permanent=True))

    expected = fallback_id(phone, Channel.EMAIL)
    assert completion == GaveUp(
        channel=Channel.PHONE,
        fallbacks=(FellBack(delivery_id=expected, from_channel=Channel.PHONE, to_channel=Channel.EMAIL),),
    )
    assert again == LeaseLost(channel=Channel.PHONE)
    rows = (await session.scalars(select(Delivery).where(Delivery.alert_id == world.alert_id))).all()
    assert {row.id for row in rows} == {phone, sms, expected}
    fallback = await fetch(session, expected)
    original = await fetch(session, phone)
    assert (fallback.channel, fallback.status, fallback.user_id, fallback.message) == (
        Channel.EMAIL,
        DeliveryStatus.PENDING,
        world.user_id,
        "Failed",
    )
    assert (fallback.received_at, fallback.traceparent) == (original.received_at, "00-trace-span-01")


async def test_a_recipient_with_no_channel_left_is_recorded_as_unreachable(
    session: AsyncSession, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    unreachable: list[Mapping[str, str]] = []

    class Counter:
        def add(self, amount: int, attributes: Mapping[str, str]) -> None:
            unreachable.append(attributes)

    monkeypatch.setattr(metrics, "_unreachable", Counter())
    sms = add_delivery(session, world, channel=Channel.SMS)
    job = await claim_one(session, sms)
    first = await finish(session, job, SendFailed(error="User has no phone number", permanent=True))
    assert isinstance(first, GaveUp)
    email_job = await claim_one(session, fallback_id(sms, Channel.EMAIL))

    completion = await finish(session, email_job, SendFailed(error="550 mailbox unavailable", permanent=True))

    assert completion == GaveUp(
        channel=Channel.EMAIL,
        fallbacks=(
            Unreachable(
                alert_id=world.alert_id,
                user_id=world.user_id,
                channel=Channel.EMAIL,
                tried=(Channel.EMAIL, Channel.SMS),
            ),
        ),
    )
    assert unreachable == [{"channel": "email"}]
    statuses = await session.scalars(select(Delivery.status).where(Delivery.alert_id == world.alert_id))
    assert sorted(statuses) == [DeliveryStatus.UNDELIVERABLE] * 2


async def test_a_renotification_round_falls_back_on_its_own(session: AsyncSession, world: World) -> None:
    first_round = add_delivery(session, world, channel=Channel.SMS, status=DeliveryStatus.UNDELIVERABLE)
    email_first_round = add_delivery(session, world, channel=Channel.EMAIL, status=DeliveryStatus.SENT)
    second_round = add_delivery(session, world, channel=Channel.SMS, age=-10)
    job = await claim_one(session, second_round, NOW + timedelta(minutes=11))

    completion = await finish(session, job, SendFailed(error="no phone", permanent=True), NOW + timedelta(minutes=11))

    assert isinstance(completion, GaveUp)
    assert completion.fallbacks == (
        FellBack(
            delivery_id=fallback_id(second_round, Channel.EMAIL), from_channel=Channel.SMS, to_channel=Channel.EMAIL
        ),
    )
    assert {first_round, email_first_round} <= set(
        await session.scalars(select(Delivery.id).where(Delivery.alert_id == world.alert_id))
    )


async def test_a_send_slower_than_its_timeout_fails_and_is_retried(engine: AsyncEngine, committed_world: World) -> None:
    class HangingAdapter:
        async def send(self, job: DeliveryJob) -> Sent:
            await asyncio.sleep(10)
            return Sent(at=datetime.now(UTC))

    sessionmaker = create_sessionmaker(engine)
    context = DispatchContext(
        sessionmaker=sessionmaker,
        adapters=dict.fromkeys(Channel, HangingAdapter()),
        throttle=AlwaysAllow(),
        settings=Settings(delivery_send_timeout_seconds=0.1),
        wake=asyncio.Event(),
    )
    async with sessionmaker() as session, session.begin():
        delivery_id = add_delivery(session, committed_world)

    await asyncio.wait_for(dispatch_once(context), timeout=5)

    async with sessionmaker() as session:
        delivery = await fetch(session, delivery_id)
    assert (delivery.status, delivery.attempts, delivery.last_error) == (
        DeliveryStatus.FAILED,
        1,
        "Send timed out after 0.1 s",
    )
    assert delivery.retry_at is not None


@pytest.mark.parametrize("status", list(DeliveryStatus))
@pytest.mark.parametrize("retry_at", [None, NOW - timedelta(seconds=1), NOW + timedelta(seconds=1)])
@pytest.mark.parametrize("lease_until", [None, NOW - timedelta(seconds=1), NOW + timedelta(seconds=1)])
@pytest.mark.parametrize("in_digest", [False, True])
async def test_the_claim_takes_exactly_the_rows_whose_parsed_state_is_claimable(
    session: AsyncSession,
    world: World,
    status: DeliveryStatus,
    retry_at: datetime | None,
    lease_until: datetime | None,
    in_digest: bool,
) -> None:
    digest_id = add_delivery(session, world, status=DeliveryStatus.SENT, age=5) if in_digest else None
    delivery_id = add_delivery(
        session, world, status=status, retry_at=retry_at, lease_until=lease_until, digest_id=digest_id
    )
    await session.flush()
    expected = state.is_claimable(state.parse(status, retry_at, lease_until, digest_id, NOW), NOW)

    claimed = delivery_id in {job.delivery_id for job in await claim(session)}

    assert claimed == expected
