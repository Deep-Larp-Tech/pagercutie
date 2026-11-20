import structlog

from pagercutie.core.broker import DELIVERIES, Subscription
from pagercutie.v1.messages_pb2 import Delivery

log = structlog.get_logger("dispatcher")


async def handle(delivery: Delivery) -> None:
    log.info(
        "dispatcher.delivery_received",
        message="Delivery received; sending is not implemented yet",
        delivery_id=delivery.delivery_id,
        alert_id=delivery.alert_id,
        channel=delivery.channel,
    )


SUBSCRIPTION = Subscription(topic=DELIVERIES, group="dispatcher", handle=handle)
