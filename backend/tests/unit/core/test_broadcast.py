import pytest

from pagercutie.core import broadcast as broadcast_module
from pagercutie.core.broadcast import Broadcast, Subscription

pytestmark = pytest.mark.anyio


async def collect(subscription: Subscription) -> list[list[str]]:
    return [batch async for batch in subscription.batches()]


async def test_a_subscription_while_closed_has_already_ended() -> None:
    broadcast = Broadcast()

    async with broadcast.subscribe() as subscription:
        broadcast.publish("lost")

        assert await collect(subscription) == []
        assert broadcast.subscriber_count == 0


async def test_payloads_queued_together_arrive_as_one_batch_in_order() -> None:
    broadcast = Broadcast()
    broadcast.open()

    async with broadcast.subscribe() as subscription:
        broadcast.publish("a")
        broadcast.publish("b")
        broadcast.close()

        assert await collect(subscription) == [["a", "b"]]


async def test_close_ends_every_subscription_until_reopened() -> None:
    broadcast = Broadcast()
    broadcast.open()

    async with broadcast.subscribe() as first, broadcast.subscribe() as second:
        broadcast.close()
        async with broadcast.subscribe() as while_closed:
            assert await collect(while_closed) == []
        broadcast.open()
        async with broadcast.subscribe() as reopened:
            broadcast.publish("after")
            broadcast.close()

            assert (await collect(first), await collect(second)) == ([], [])
            assert await collect(reopened) == [["after"]]


async def test_a_subscriber_that_falls_behind_is_ended_and_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(broadcast_module, "QUEUE_SIZE", 2)
    broadcast = Broadcast()
    broadcast.open()

    async with broadcast.subscribe() as slow:
        for payload in ["a", "b", "c"]:
            broadcast.publish(payload)

        assert broadcast.subscriber_count == 0
        assert await collect(slow) == []


async def test_leaving_the_context_unsubscribes() -> None:
    broadcast = Broadcast()
    broadcast.open()

    async with broadcast.subscribe():
        assert broadcast.subscriber_count == 1

    assert broadcast.subscriber_count == 0
