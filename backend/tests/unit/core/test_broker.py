from pagercutie.core.broker import DELIVERIES, EVENTS, MATCHES
from pagercutie.v1.messages_pb2 import Delivery, Event, Match


def test_partition_keys_follow_the_topic_table() -> None:
    assert EVENTS.key(Event(event_id="e1")) is None
    assert MATCHES.key(Match(rule_id="r1", fingerprint="abc")) == "r1:abc"
    assert DELIVERIES.key(Delivery(recipient_id="u1")) == "u1"
