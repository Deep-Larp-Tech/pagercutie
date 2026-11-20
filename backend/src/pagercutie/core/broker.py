"""Typed asyncio access to the Redpanda topics (SPEC §5) over the synchronous `confluent_kafka` client."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import confluent_kafka
import structlog
from google.protobuf.message import DecodeError, Message

from pagercutie.core.settings import Settings
from pagercutie.core.workers import Worker
from pagercutie.v1.messages_pb2 import Delivery, Event, Match

log = structlog.get_logger("broker")

# librdkafka's own log lines, rendered like every other record instead of raw on stderr.
_client_logger = logging.getLogger("rdkafka")
# Bounds how long shutdown waits for a blocked poll, which runs in a thread and cannot be cancelled.
POLL_TIMEOUT_S = 1.0
FLUSH_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class Topic[M: Message]:
    """A topic bound to its protobuf message type and partition key (SPEC §5.1)."""

    name: str
    message: type[M]
    # None spreads messages evenly over the partitions.
    key: Callable[[M], str | None]


EVENTS = Topic("events", Event, key=lambda _: None)
MATCHES = Topic("matches", Match, key=lambda match: f"{match.rule_id}:{match.fingerprint}")
DELIVERIES = Topic("deliveries", Delivery, key=lambda delivery: delivery.recipient_id)


def _settle(done: asyncio.Future[None], error: confluent_kafka.KafkaError | None) -> None:
    if done.done():
        return
    if error is None:
        done.set_result(None)
    else:
        done.set_exception(confluent_kafka.KafkaException(error))


class Producer:
    """Produces protobuf messages; `produce` returns once the broker acknowledged the write (`acks=all`)."""

    def __init__(self, producer: confluent_kafka.Producer) -> None:
        self._producer = producer

    async def produce[M: Message](self, topic: Topic[M], message: M) -> None:
        loop = asyncio.get_running_loop()
        done: asyncio.Future[None] = loop.create_future()

        def on_delivery(error: confluent_kafka.KafkaError | None, _: confluent_kafka.Message) -> None:
            # Runs on the poll thread.
            loop.call_soon_threadsafe(_settle, done, error)

        self._producer.produce(topic.name, message.SerializeToString(), key=topic.key(message), on_delivery=on_delivery)
        await done


@asynccontextmanager
async def open_producer(settings: Settings) -> AsyncGenerator[Producer]:
    producer = confluent_kafka.Producer(
        {
            "bootstrap.servers": settings.broker_bootstrap_servers,
            "logger": _client_logger,
            "acks": "all",
            "enable.idempotence": True,
            "linger.ms": 1,
        }
    )
    stopping = asyncio.Event()

    async def serve_delivery_callbacks() -> None:
        while not stopping.is_set():
            await asyncio.to_thread(producer.poll, POLL_TIMEOUT_S)

    poller = asyncio.create_task(serve_delivery_callbacks(), name="broker.producer.poll")
    try:
        yield Producer(producer)
    finally:
        stopping.set()
        await poller
        remaining = await asyncio.to_thread(producer.flush, FLUSH_TIMEOUT_S)
        if remaining:
            log.warning("broker.flush_incomplete", message="Messages left unsent at shutdown", remaining=remaining)


type Handler[M: Message] = Callable[[M], Awaitable[None]]


@dataclass(frozen=True)
class Subscription[M: Message]:
    """One consumer group reading one topic (SPEC §5.1)."""

    topic: Topic[M]
    group: str
    handle: Handler[M]


async def consume[M: Message](settings: Settings, subscription: Subscription[M], stopping: asyncio.Event) -> None:
    """Hands each message to the handler and commits its offset only afterwards (at-least-once, SPEC §5.3)."""
    topic = subscription.topic
    consumer = confluent_kafka.Consumer(
        {
            "bootstrap.servers": settings.broker_bootstrap_servers,
            "logger": _client_logger,
            "group.id": subscription.group,
            "group.instance.id": settings.worker_id,
            "partition.assignment.strategy": "cooperative-sticky",
            "session.timeout.ms": 30000,
            "enable.auto.commit": False,
            # A new consumer group starts at the oldest retained message, so no event produced before it is skipped.
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([topic.name])
    log.info("broker.subscribed", message="Consumer subscribed", topic=topic.name, group=subscription.group)
    try:
        while not stopping.is_set():
            record = await asyncio.to_thread(consumer.poll, POLL_TIMEOUT_S)
            if record is None:
                continue
            if error := record.error():
                if error.fatal():
                    raise confluent_kafka.KafkaException(error)
                log.warning("broker.consumer_error", message=error.str(), topic=topic.name, code=error.code())
                continue
            try:
                message = topic.message.FromString(record.value() or b"")
            except DecodeError:
                # A poison message would block its partition forever; producers are ours, so this is a bug to fix.
                log.exception(
                    "broker.undecodable",
                    message="Skipped a message that is not a valid protobuf",
                    topic=topic.name,
                    partition=record.partition(),
                    offset=record.offset(),
                )
            else:
                await subscription.handle(message)
            await asyncio.to_thread(consumer.commit, message=record, asynchronous=False)
    finally:
        await asyncio.to_thread(consumer.close)


def consumer_worker[M: Message](settings: Settings, subscription: Subscription[M]) -> Worker:
    async def run(stopping: asyncio.Event) -> None:
        await consume(settings, subscription, stopping)

    return Worker(name=f"consumer.{subscription.group}", run=run)
