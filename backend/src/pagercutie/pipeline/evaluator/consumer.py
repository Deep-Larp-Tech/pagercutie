import structlog

from pagercutie.core.broker import EVENTS, Subscription
from pagercutie.v1.messages_pb2 import Event

log = structlog.get_logger("evaluator")


async def handle(event: Event) -> None:
    log.info(
        "evaluator.event_received",
        message="Event received; rule evaluation is not implemented yet",
        event_id=event.event_id,
        source=event.source,
    )


SUBSCRIPTION = Subscription(topic=EVENTS, group="evaluator", handle=handle)
