import asyncio
from collections.abc import AsyncIterator, Iterator

import confluent_kafka
import pytest
from testcontainers.community.kafka import RedpandaContainer

from pagercutie.core.broker import EVENTS, Subscription, consume, open_producer
from pagercutie.core.settings import Settings
from pagercutie.v1.messages_pb2 import Event

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def redpanda() -> Iterator[RedpandaContainer]:
    # Same version as compose.yaml.
    with RedpandaContainer("redpandadata/redpanda:v26.2.7") as container:
        yield container


@pytest.fixture
def broker_settings(redpanda: RedpandaContainer) -> Settings:
    return Settings(broker_bootstrap_servers=redpanda.get_bootstrap_server(), worker_id="test-worker")


@pytest.fixture
async def received(broker_settings: Settings) -> AsyncIterator[asyncio.Queue[Event]]:
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def handle(event: Event) -> None:
        await queue.put(event)

    stopping = asyncio.Event()
    subscription = Subscription(topic=EVENTS, group="test-evaluator", handle=handle)
    task = asyncio.create_task(consume(broker_settings, subscription, stopping))
    yield queue
    stopping.set()
    await task


async def test_produced_message_reaches_the_consumer(broker_settings: Settings, received: asyncio.Queue[Event]) -> None:
    async with open_producer(broker_settings) as producer:
        await producer.produce(EVENTS, Event(event_id="e1", source="payments-webhook"))
        await producer.produce(EVENTS, Event(event_id="e2", source="payments-webhook"))

    first = await asyncio.wait_for(received.get(), timeout=30)
    second = await asyncio.wait_for(received.get(), timeout=30)
    assert {first.event_id, second.event_id} == {"e1", "e2"}


async def test_undecodable_message_is_skipped(broker_settings: Settings, received: asyncio.Queue[Event]) -> None:
    # Both on one partition, so the valid message arrives only if the consumer gets past the poison message.
    raw = confluent_kafka.Producer({"bootstrap.servers": broker_settings.broker_bootstrap_servers})
    raw.produce(EVENTS.name, b"\xff not protobuf", partition=0)
    raw.produce(EVENTS.name, Event(event_id="after-poison").SerializeToString(), partition=0)
    raw.flush(10)

    event = await asyncio.wait_for(received.get(), timeout=30)
    assert event.event_id == "after-poison"
