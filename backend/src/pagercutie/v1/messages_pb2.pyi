from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Event(_message.Message):
    __slots__ = ("event_id", "source", "schema_id", "received_at_ms", "payload", "severity")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_ID_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    source: str
    schema_id: str
    received_at_ms: int
    payload: bytes
    severity: str
    def __init__(self, event_id: _Optional[str] = ..., source: _Optional[str] = ..., schema_id: _Optional[str] = ..., received_at_ms: _Optional[int] = ..., payload: _Optional[bytes] = ..., severity: _Optional[str] = ...) -> None: ...

class Match(_message.Message):
    __slots__ = ("event_id", "rule_id", "fingerprint", "received_at_ms", "payload")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    rule_id: str
    fingerprint: str
    received_at_ms: int
    payload: bytes
    def __init__(self, event_id: _Optional[str] = ..., rule_id: _Optional[str] = ..., fingerprint: _Optional[str] = ..., received_at_ms: _Optional[int] = ..., payload: _Optional[bytes] = ...) -> None: ...

class Delivery(_message.Message):
    __slots__ = ("delivery_id", "alert_id", "recipient_id", "channel", "received_at_ms")
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    ALERT_ID_FIELD_NUMBER: _ClassVar[int]
    RECIPIENT_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    delivery_id: str
    alert_id: str
    recipient_id: str
    channel: str
    received_at_ms: int
    def __init__(self, delivery_id: _Optional[str] = ..., alert_id: _Optional[str] = ..., recipient_id: _Optional[str] = ..., channel: _Optional[str] = ..., received_at_ms: _Optional[int] = ...) -> None: ...
