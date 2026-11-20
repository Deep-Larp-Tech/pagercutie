import structlog

from pagercutie.core.broker import MATCHES, Subscription
from pagercutie.v1.messages_pb2 import Match

log = structlog.get_logger("dedup")


async def handle(match: Match) -> None:
    log.info(
        "dedup.match_received",
        message="Match received; deduplication is not implemented yet",
        event_id=match.event_id,
        rule_id=match.rule_id,
        fingerprint=match.fingerprint,
    )


SUBSCRIPTION = Subscription(topic=MATCHES, group="dedup", handle=handle)
