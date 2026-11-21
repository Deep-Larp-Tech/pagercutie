"""In-process fan-out of one `NOTIFY` channel's payloads to the replica's subscribers, e.g. live feeds (SPEC §5.3)."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

import structlog

log = structlog.get_logger("broadcast")

QUEUE_SIZE = 1000


class Subscription:
    """One subscriber's payloads in arrival order. Ends after the payloads already queued when the broadcast closes,
    and at once when the subscriber falls `QUEUE_SIZE` behind."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(QUEUE_SIZE)

    def offer(self, payload: str) -> bool:
        """Queues `payload`; False when the subscription has ended, or ends now because it is full."""
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            self._queue.shutdown(immediate=True)
            return False
        except asyncio.QueueShutDown:
            return False
        return True

    def end(self) -> None:
        self._queue.shutdown()

    async def batches(self) -> AsyncIterator[list[str]]:
        """Waits for one payload, then takes every payload queued with it; returns once the subscription ends."""
        while True:
            try:
                batch = [await self._queue.get()]
            except asyncio.QueueShutDown:
                return
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty, asyncio.QueueShutDown:
                    break
            yield batch


class Broadcast:
    """Payloads of one channel for every current subscriber; `core.listen` opens it once the channel is listened to
    and closes it when the listening connection ends.

    While closed, a new subscription has already ended: notifications sent then are lost, so the subscriber must
    reload instead of waiting.
    """

    def __init__(self) -> None:
        self._subscribers: set[Subscription] = set()
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self) -> AsyncGenerator[Subscription]:
        """Payloads published from now on, until the context exits."""
        subscription = Subscription()
        if self._open:
            self._subscribers.add(subscription)
        else:
            subscription.end()
        try:
            yield subscription
        finally:
            self._subscribers.discard(subscription)

    def open(self) -> None:
        self._open = True

    def publish(self, payload: str) -> None:
        """Hands `payload` to every subscriber; never blocks, ends and drops subscribers that are full."""
        for subscription in list(self._subscribers):
            if not subscription.offer(payload):
                self._subscribers.discard(subscription)
                log.warning("broadcast.subscriber_dropped", message="Subscriber fell behind, ending it")

    def close(self) -> None:
        """Ends every subscription after its queued payloads; later subscriptions end at once until reopened."""
        self._open = False
        for subscription in self._subscribers:
            subscription.end()
        self._subscribers.clear()
