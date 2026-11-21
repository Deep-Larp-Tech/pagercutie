from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Event(_message.Message):
    __slots__ = ("payload",)
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    payload: _struct_pb2.Struct
    def __init__(self, payload: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class Accepted(_message.Message):
    __slots__ = ("event_id", "matches")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    MATCHES_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    matches: int
    def __init__(self, event_id: _Optional[str] = ..., matches: _Optional[int] = ...) -> None: ...
