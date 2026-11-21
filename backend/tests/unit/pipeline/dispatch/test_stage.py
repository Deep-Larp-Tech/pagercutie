import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pagercutie.core.enums import Channel
from pagercutie.pipeline.dispatch.stage import (
    ChannelAdapter,
    DeliveryJob,
    SendFailed,
    Sent,
    Throttled,
    digest_message,
    retry_delay,
    send,
)

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


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

    async def allow(self, user_id: uuid.UUID) -> bool:
        self.asked.append(user_id)
        return self.allowed


class FakeAdapter:
    def __init__(self, result: Sent | SendFailed | None = None, error: Exception | None = None) -> None:
        self.result = result or Sent(at=NOW)
        self.error = error
        self.sent: list[DeliveryJob] = []

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        self.sent.append(job)
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
