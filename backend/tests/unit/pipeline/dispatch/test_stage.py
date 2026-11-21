import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pagercutie.core.enums import Channel
from pagercutie.pipeline.dispatch.digest import digest_message
from pagercutie.pipeline.dispatch.stage import (
    ChannelAdapter,
    DeliveryJob,
    SendFailed,
    SendResult,
    Sent,
    Throttle,
    Throttled,
    retry_delay,
)
from pagercutie.pipeline.dispatch.stage import send as send_with_timeout

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
TIMEOUT_S = 5.0


async def send(
    job: DeliveryJob, adapters: dict[Channel, ChannelAdapter], throttle: Throttle, timeout_s: float = TIMEOUT_S
) -> SendResult:
    return await send_with_timeout(job, adapters, throttle, timeout_s)


def make_job(channel: Channel) -> DeliveryJob:
    return DeliveryJob(
        delivery_id=uuid.uuid4(),
        alert_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        channel=channel,
        message="Workflow failed",
        attempts=0,
        lease_until=NOW,
    )


class FakeThrottle:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.asked: list[uuid.UUID] = []
        self.refunded: list[uuid.UUID] = []

    async def allow(self, user_id: uuid.UUID) -> bool:
        self.asked.append(user_id)
        return self.allowed

    async def refund(self, user_id: uuid.UUID) -> None:
        self.refunded.append(user_id)


class FakeAdapter:
    def __init__(
        self, result: Sent | SendFailed | None = None, error: Exception | None = None, delay_s: float = 0
    ) -> None:
        self.result = result or Sent(at=NOW)
        self.error = error
        self.delay_s = delay_s
        self.sent: list[DeliveryJob] = []

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        self.sent.append(job)
        await asyncio.sleep(self.delay_s)
        if self.error:
            raise self.error
        return self.result


def adapters(adapter: FakeAdapter) -> dict[Channel, ChannelAdapter]:
    return dict.fromkeys(Channel, adapter)


@pytest.mark.parametrize("channel", [Channel.EMAIL, Channel.SMS, Channel.PHONE])
async def test_an_empty_bucket_throttles_external_channels_without_sending(channel: Channel) -> None:
    job, adapter, throttle = make_job(channel), FakeAdapter(), FakeThrottle(allowed=False)

    assert await send(job, adapters(adapter), throttle) == Throttled()

    assert throttle.asked == [job.user_id]
    assert adapter.sent == []


@pytest.mark.parametrize("channel", [Channel.EMAIL, Channel.SMS, Channel.PHONE])
async def test_a_token_lets_external_channels_send(channel: Channel) -> None:
    job, adapter, throttle = make_job(channel), FakeAdapter(), FakeThrottle(allowed=True)

    assert await send(job, adapters(adapter), throttle) == Sent(at=NOW)

    assert adapter.sent == [job]


async def test_the_ui_channel_never_asks_the_throttle() -> None:
    job, adapter, throttle = make_job(Channel.UI), FakeAdapter(), FakeThrottle(allowed=False)

    assert await send(job, adapters(adapter), throttle) == Sent(at=NOW)

    assert throttle.asked == []
    assert adapter.sent == [job]


async def test_an_adapter_that_raises_becomes_a_retryable_failure() -> None:
    adapter = FakeAdapter(error=RuntimeError("boom"))

    result = await send(make_job(Channel.EMAIL), adapters(adapter), FakeThrottle(allowed=True))

    assert result == SendFailed(error="RuntimeError: boom", permanent=False)


async def test_an_adapter_failure_is_passed_through() -> None:
    failure = SendFailed(error="no phone number", permanent=True)

    result = await send(make_job(Channel.SMS), adapters(FakeAdapter(result=failure)), FakeThrottle(allowed=True))

    assert result is failure


async def test_a_channel_without_an_adapter_becomes_a_failure() -> None:
    result = await send(make_job(Channel.UI), {}, FakeThrottle(allowed=True))

    assert isinstance(result, SendFailed)
    assert not result.permanent


def test_the_backoff_doubles_up_to_five_minutes() -> None:
    assert [retry_delay(attempts) for attempts in range(11)] == [
        timedelta(seconds=seconds) for seconds in [1, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300]
    ]
    assert retry_delay(10_000) == timedelta(seconds=300)


def test_a_digest_lists_the_first_line_of_each_message() -> None:
    text = digest_message(["Failed: a\nbody", "  Failed: b  "])

    assert text == "2 notifications held back by the rate limit:\n- Failed: a\n- Failed: b"


def test_a_digest_counts_the_messages_beyond_its_line_limit() -> None:
    text = digest_message([f"m{n}" for n in range(13)])

    assert text.splitlines()[0] == "13 notifications held back by the rate limit:"
    assert len(text.splitlines()) == 12
    assert text.splitlines()[-1] == "... and 3 more"


@pytest.mark.parametrize(
    "adapter",
    [
        FakeAdapter(result=SendFailed(error="SMTP down")),
        FakeAdapter(error=RuntimeError("boom")),
        FakeAdapter(delay_s=1),
    ],
    ids=["failed", "raised", "timed_out"],
)
async def test_a_failed_send_gives_its_token_back(adapter: FakeAdapter) -> None:
    job, throttle = make_job(Channel.EMAIL), FakeThrottle(allowed=True)

    result = await send(job, adapters(adapter), throttle, timeout_s=0.05)

    assert isinstance(result, SendFailed)
    assert throttle.refunded == [job.user_id]


async def test_a_sent_or_throttled_delivery_keeps_the_bucket_as_it_is() -> None:
    allowed, empty = FakeThrottle(allowed=True), FakeThrottle(allowed=False)

    await send(make_job(Channel.SMS), adapters(FakeAdapter()), allowed)
    await send(make_job(Channel.SMS), adapters(FakeAdapter()), empty)

    assert allowed.refunded == []
    assert empty.refunded == []


async def test_a_failed_ui_send_refunds_nothing_since_it_took_no_token() -> None:
    throttle = FakeThrottle(allowed=True)

    await send(make_job(Channel.UI), adapters(FakeAdapter(result=SendFailed(error="db down"))), throttle)

    assert throttle.refunded == []


async def test_a_send_slower_than_the_timeout_is_a_transient_failure() -> None:
    adapter = FakeAdapter(delay_s=1)

    result = await send(make_job(Channel.SMS), adapters(adapter), FakeThrottle(allowed=True), timeout_s=0.05)

    assert result == SendFailed(error="Send timed out after 0.05 s", permanent=False)
