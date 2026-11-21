import uuid
from collections.abc import Sequence

import orjson
import pytest
from pydantic import JsonValue

from pagercutie.core.enums import Severity
from pagercutie.core.errors import SourceSlugNotFound, Unauthenticated
from pagercutie.core.tokens import hash_token
from pagercutie.event_schemas.service import TeamSchema
from pagercutie.pipeline.ingest.stage import (
    CompiledSchema,
    EventRejected,
    RejectReason,
    SchemaCache,
    SourceCatalog,
    authenticate,
    compile_schema,
    normalise,
    resolve_schema,
)
from pagercutie.pipeline.messages import Event, RawEvent
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.sources.service import IngestSource

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


async def normalise_with(event: RawEvent, schemas: Sequence[TeamSchema] = (ANY_OBJECT,)) -> Event:
    loaded: list[uuid.UUID] = []

    async def load(team_id: uuid.UUID) -> Sequence[CompiledSchema]:
        loaded.append(team_id)
        return [compile_schema(s) for s in schemas]

    result = await normalise(event, load)
    assert loaded == [event.source.team_id]
    return result


def resolve(schemas: Sequence[TeamSchema], payload: dict[str, JsonValue]) -> TeamSchema:
    return resolve_schema([compile_schema(s) for s in schemas], payload)


def raw(body: object, cat: SourceCatalog | None = None) -> RawEvent:
    data = body if isinstance(body, bytes) else orjson.dumps(body)
    return RawEvent(source=(cat or catalog()).sources["payments-webhook"], body=data)


async def test_event_is_normalised_with_the_matching_schema() -> None:
    cat = catalog()
    source = cat.sources["payments-webhook"]

    event = await normalise_with(raw({"amount": 10}, cat), [PAYMENT])

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
    assert resolve([ANY_OBJECT, PAYMENT, REFUND], payload) == expected


def test_equal_required_keys_are_ranked_by_properties() -> None:
    wider = schema("wider", {"required": ["amount"], "properties": {"amount": {}, "currency": {}, "card": {}}})

    assert resolve([PAYMENT, wider], {"amount": 10}) == wider


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
        resolve(schemas, payload)

    assert rejected.value.reason == RejectReason.SCHEMA_UNRESOLVED
    assert rejected.value.errors[0].msg == msg


def test_schema_that_does_not_compile_never_matches() -> None:
    broken = schema("broken", {"required": ["amount"], "type": 5})

    assert resolve([broken, ANY_OBJECT], {"amount": 10}) == ANY_OBJECT


def test_remote_refs_are_not_fetched() -> None:
    remote = schema("remote", {"$ref": "https://example.com/schema.json"})

    assert resolve([remote, ANY_OBJECT], {}) == ANY_OBJECT


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
    assert (await normalise_with(raw(body, catalog(SEVERITY)))).severity == severity


@pytest.mark.parametrize(
    ("slug", "source_type"),
    [("unknown", SourceType.WEBHOOK), ("payments-webhook", SourceType.WEBSOCKET)],
    ids=["unknown slug", "other adapter type"],
)
def test_unknown_source_is_not_found(slug: str, source_type: SourceType) -> None:
    with pytest.raises(SourceSlugNotFound):
        authenticate(catalog(), slug, source_type, TOKEN)


@pytest.mark.parametrize("token", [None, "wrong"])
def test_missing_or_wrong_token_is_unauthenticated(token: str | None) -> None:
    with pytest.raises(Unauthenticated):
        authenticate(catalog(), "payments-webhook", SourceType.WEBHOOK, token)


def test_the_current_token_authenticates_the_source() -> None:
    cat = catalog()

    assert authenticate(cat, "payments-webhook", SourceType.WEBHOOK, TOKEN) is cat.sources["payments-webhook"]


class Queries:
    """A team schema query that answers from `schemas` and counts its calls."""

    def __init__(self, schemas: Sequence[TeamSchema]) -> None:
        self.schemas = list(schemas)
        self.calls = 0

    async def __call__(self, team_id: uuid.UUID) -> Sequence[TeamSchema]:
        self.calls += 1
        return self.schemas


async def test_the_cache_queries_a_team_once_until_invalidated() -> None:
    query = Queries([PAYMENT])
    cache = SchemaCache(query)
    team_id = uuid.uuid7()

    first = await cache.load(team_id)
    assert await cache.load(team_id) is first
    assert query.calls == 1

    query.schemas = [PAYMENT, REFUND]
    cache.invalidate()

    assert [c.schema for c in await cache.load(team_id)] == [PAYMENT, REFUND]
    assert query.calls == 2


async def test_the_cache_reuses_the_validator_of_a_schema_version_after_an_invalidation() -> None:
    cache = SchemaCache(Queries([PAYMENT]))
    team_id = uuid.uuid7()
    [before] = await cache.load(team_id)

    cache.invalidate()
    [after] = await cache.load(team_id)

    assert after is before


async def test_a_load_racing_an_invalidation_is_not_cached() -> None:
    team_id = uuid.uuid7()
    query = Queries([PAYMENT])

    async def racing(team: uuid.UUID) -> Sequence[TeamSchema]:
        # A schema is created while the first query is in flight.
        if query.calls == 0:
            cache.invalidate()
        return await query(team)

    cache = SchemaCache(racing)
    await cache.load(team_id)
    await cache.load(team_id)

    assert query.calls == 2
