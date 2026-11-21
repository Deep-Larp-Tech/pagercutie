import math
import uuid
from collections.abc import Mapping, Sequence

import orjson
import pytest
from google.protobuf import struct_pb2
from pydantic import JsonValue

from pagercutie.core.enums import Severity
from pagercutie.core.errors import SourceSlugNotFound, Unauthenticated
from pagercutie.core.tokens import hash_token
from pagercutie.event_schemas.service import TeamSchema
from pagercutie.pipeline.ingest.stage import (
    EventRejected,
    RejectReason,
    SourceCatalog,
    decode_protobuf,
    normalise,
    resolve_schema,
)
from pagercutie.pipeline.messages import Event, RawEvent
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.sources.service import IngestSource
from pagercutie.v1 import ingest_pb2

pytestmark = pytest.mark.anyio

TOKEN = "secret"
SEVERITY = SeverityMapping(field="level", values={"WARNING": Severity.WARN, "5": Severity.CRITICAL})


def schema(name: str, json_schema: dict[str, JsonValue]) -> TeamSchema:
    return TeamSchema(id=uuid.uuid7(), name=name, json_schema=json_schema)


ANY_OBJECT = schema("any", {"type": "object"})
PAYMENT = schema(
    "payment",
    {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "integer"}, "currency": {"type": "string", "maxLength": 3}},
    },
)
REFUND = schema(
    "refund",
    {
        "type": "object",
        "required": ["amount", "refund_of"],
        "properties": {"amount": {"type": "integer"}, "refund_of": {"type": "string"}},
    },
)


def catalog(severity: SeverityMapping | None = None) -> SourceCatalog:
    source = IngestSource(
        id=uuid.uuid7(),
        slug="payments-webhook",
        type=SourceType.WEBHOOK,
        team_id=uuid.uuid7(),
        severity=severity or SeverityMapping(),
        token_hash=hash_token(TOKEN),
    )
    return SourceCatalog(sources={source.slug: source})


async def normalise_with(
    event: RawEvent, cat: SourceCatalog | None = None, schemas: Sequence[TeamSchema] = (ANY_OBJECT,)
) -> Event:
    loaded: list[uuid.UUID] = []

    async def load(team_id: uuid.UUID) -> Sequence[TeamSchema]:
        loaded.append(team_id)
        return schemas

    cat = cat or catalog()
    result = await normalise(event, cat, load)
    assert loaded == [cat.sources["payments-webhook"].team_id]
    return result


def raw(
    body: object,
    *,
    slug: str = "payments-webhook",
    token: str | None = TOKEN,
    source_type: SourceType = SourceType.WEBHOOK,
) -> RawEvent:
    data = body if isinstance(body, bytes) else orjson.dumps(body)
    return RawEvent(source_slug=slug, source_type=source_type, token=token, content_type="application/json", body=data)


async def test_event_is_normalised_with_the_matching_schema() -> None:
    cat = catalog()
    source = cat.sources["payments-webhook"]

    event = await normalise_with(raw({"amount": 10}), cat, [PAYMENT])

    assert (event.schema_id, event.schema_name) == (PAYMENT.id, "payment")
    assert event.source == "payments-webhook"
    assert event.source_id == source.id
    assert event.team_id == source.team_id
    assert event.payload == {"amount": 10}
    assert event.severity == Severity.INFO
    assert event.event_id.version == 7


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"amount": 10}, PAYMENT),
        ({"amount": 10, "refund_of": "p-1"}, REFUND),
        ({"note": "x"}, ANY_OBJECT),
        # Fails REFUND (refund_of is not a string), so the next most specific match wins.
        ({"amount": 10, "refund_of": 7}, PAYMENT),
    ],
)
def test_the_most_specific_matching_schema_wins(payload: dict[str, JsonValue], expected: TeamSchema) -> None:
    assert resolve_schema([ANY_OBJECT, PAYMENT, REFUND], payload) == expected


def test_equal_required_keys_are_ranked_by_properties() -> None:
    wider = schema("wider", {"required": ["amount"], "properties": {"amount": {}, "currency": {}, "card": {}}})

    assert resolve_schema([PAYMENT, wider], {"amount": 10}) == wider


@pytest.mark.parametrize(
    ("schemas", "payload", "msg"),
    [
        ([PAYMENT], {"amount": "ten"}, "matches no event schema of the team"),
        ([PAYMENT], {"amount": 10, "currency": "EURO"}, "matches no event schema of the team"),
        ([], {"amount": 10}, "matches no event schema of the team"),
        (
            [PAYMENT, schema("charge", {"required": ["amount"], "properties": {"amount": {}, "card": {}}})],
            {"amount": 10},
            "matches several equally specific schemas: payment, charge",
        ),
    ],
    ids=["wrong type", "value constraint", "no schemas", "tie"],
)
def test_unresolved_schema_is_rejected(schemas: list[TeamSchema], payload: dict[str, JsonValue], msg: str) -> None:
    with pytest.raises(EventRejected) as rejected:
        resolve_schema(schemas, payload)

    assert rejected.value.reason == RejectReason.SCHEMA_UNRESOLVED
    assert rejected.value.errors[0].msg == msg


def test_schema_that_does_not_compile_never_matches() -> None:
    broken = schema("broken", {"required": ["amount"], "type": 5})

    assert resolve_schema([broken, ANY_OBJECT], {"amount": 10}) == ANY_OBJECT


def test_remote_refs_are_not_fetched() -> None:
    remote = schema("remote", {"$ref": "https://example.com/schema.json"})

    assert resolve_schema([remote, ANY_OBJECT], {}) == ANY_OBJECT


@pytest.mark.parametrize("body", [b"{not json", b"[1, 2]"])
async def test_bodies_that_are_not_json_objects_are_undecodable(body: bytes) -> None:
    with pytest.raises(EventRejected) as rejected:
        await normalise_with(raw(body))

    assert rejected.value.reason == RejectReason.UNDECODABLE


@pytest.mark.parametrize(
    ("body", "severity"),
    [
        ({"level": "WARNING"}, Severity.WARN),
        ({"level": 5}, Severity.CRITICAL),
        ({"level": "?"}, Severity.INFO),
        ({}, Severity.INFO),
    ],
)
async def test_severity_is_mapped_or_defaulted(body: object, severity: Severity) -> None:
    assert (await normalise_with(raw(body), catalog(SEVERITY))).severity == severity


@pytest.mark.parametrize(
    "event",
    [raw({}, slug="unknown"), raw({}, source_type=SourceType.WEBSOCKET)],
    ids=["unknown slug", "other adapter type"],
)
async def test_unknown_source_is_not_found(event: RawEvent) -> None:
    with pytest.raises(SourceSlugNotFound):
        await normalise_with(event)


@pytest.mark.parametrize("token", [None, "wrong"])
async def test_missing_or_wrong_token_is_unauthenticated(token: str | None) -> None:
    with pytest.raises(Unauthenticated):
        await normalise_with(raw({}, token=token))


def protobuf_event(payload: Mapping[str, JsonValue]) -> bytes:
    struct = struct_pb2.Struct()
    struct.update(payload)
    return ingest_pb2.Event(payload=struct).SerializeToString()


def test_protobuf_payload_is_decoded_to_json() -> None:
    payload: dict[str, JsonValue] = {
        "service": "api",
        "ok": True,
        "missing": None,
        "tags": ["a", 1.5],
        "error": {"code": "E1"},
    }

    assert decode_protobuf(protobuf_event(payload)) == payload


@pytest.mark.parametrize(
    ("number", "expected"),
    [(500, 500), (-3.0, -3), (1.5, 1.5), (2.0**53, 2**53), (2.0**60, 2.0**60)],
)
def test_integral_protobuf_numbers_become_ints(number: float, expected: JsonValue) -> None:
    decoded = decode_protobuf(protobuf_event({"n": number}))["n"]

    assert decoded == expected
    assert type(decoded) is type(expected)


def test_integral_protobuf_number_matches_an_integer_schema() -> None:
    assert resolve_schema([PAYMENT], decode_protobuf(protobuf_event({"amount": 10}))) == PAYMENT


@pytest.mark.parametrize("number", [math.nan, math.inf])
def test_non_finite_protobuf_numbers_are_undecodable(number: float) -> None:
    with pytest.raises(EventRejected) as rejected:
        decode_protobuf(protobuf_event({"nested": {"n": [number]}}))

    assert rejected.value.reason == RejectReason.UNDECODABLE
    assert rejected.value.errors[0].loc == ("nested", "n", 0)


def test_bytes_that_are_not_an_event_are_undecodable() -> None:
    with pytest.raises(EventRejected) as rejected:
        decode_protobuf(b"\xff\xff")

    assert rejected.value.reason == RejectReason.UNDECODABLE


async def test_protobuf_source_events_are_decoded_from_protobuf() -> None:
    source = IngestSource(
        id=uuid.uuid7(),
        slug="payments-webhook",
        type=SourceType.PROTOBUF,
        team_id=uuid.uuid7(),
        severity=SEVERITY,
        token_hash=hash_token(TOKEN),
    )
    event = raw(protobuf_event({"amount": 10, "level": 5}), source_type=SourceType.PROTOBUF)

    normalised = await normalise_with(event, SourceCatalog(sources={source.slug: source}), [PAYMENT])

    assert (normalised.schema_name, normalised.payload, normalised.severity) == (
        "payment",
        {"amount": 10, "level": 5},
        Severity.CRITICAL,
    )
