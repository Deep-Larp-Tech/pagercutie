import uuid

import orjson
import pytest

from pagercutie.core.enums import Severity
from pagercutie.core.errors import SourceSlugNotFound, Unauthenticated
from pagercutie.core.tokens import hash_token
from pagercutie.pipeline.ingest.stage import EventRejected, RejectReason, SourceCatalog, normalise
from pagercutie.pipeline.messages import RawEvent
from pagercutie.sources.schemas import DiscriminatedSchema, FixedSchema, SchemaResolution, SeverityMapping, SourceType
from pagercutie.sources.service import IngestSource

TOKEN = "secret"
PAYMENT = uuid.uuid7()
REFUND = uuid.uuid7()
FIXED = FixedSchema(mode="fixed", schema_id=PAYMENT)
DISCRIMINATED = DiscriminatedSchema(mode="discriminator", field="meta.kind", mapping={"payment": PAYMENT, "2": REFUND})
SEVERITY = SeverityMapping(field="level", values={"WARNING": Severity.WARN, "5": Severity.CRITICAL})


def catalog(resolution: SchemaResolution, severity: SeverityMapping | None = None) -> SourceCatalog:
    source = IngestSource(
        id=uuid.uuid7(),
        slug="payments-webhook",
        type=SourceType.WEBHOOK,
        team_id=uuid.uuid7(),
        schema_resolution=resolution,
        severity=severity or SeverityMapping(),
        token_hash=hash_token(TOKEN),
    )
    return SourceCatalog(sources={source.slug: source})


def raw(
    body: object,
    *,
    slug: str = "payments-webhook",
    token: str | None = TOKEN,
    source_type: SourceType = SourceType.WEBHOOK,
) -> RawEvent:
    data = body if isinstance(body, bytes) else orjson.dumps(body)
    return RawEvent(source_slug=slug, source_type=source_type, token=token, content_type="application/json", body=data)


def test_fixed_schema_event_is_normalised() -> None:
    cat = catalog(FIXED)
    source = cat.sources["payments-webhook"]

    event = normalise(raw({"amount": 10}), cat)

    assert event.schema_id == PAYMENT
    assert event.source == "payments-webhook"
    assert event.source_id == source.id
    assert event.team_id == source.team_id
    assert event.payload == {"amount": 10}
    assert event.severity == Severity.INFO
    assert event.event_id.version == 7


@pytest.mark.parametrize(("kind", "schema_id"), [("payment", PAYMENT), (2, REFUND)])
def test_discriminator_picks_the_schema(kind: object, schema_id: uuid.UUID) -> None:
    assert normalise(raw({"meta": {"kind": kind}}), catalog(DISCRIMINATED)).schema_id == schema_id


@pytest.mark.parametrize(
    ("body", "msg"),
    [({"meta": {"kind": "chargeback"}}, "no schema for value chargeback"), ({}, "is missing")],
)
def test_unresolved_discriminator_is_rejected(body: object, msg: str) -> None:
    with pytest.raises(EventRejected) as rejected:
        normalise(raw(body), catalog(DISCRIMINATED))

    assert rejected.value.reason == RejectReason.SCHEMA_UNRESOLVED
    assert rejected.value.errors[0].loc == ("meta.kind",)
    assert msg in rejected.value.errors[0].msg


@pytest.mark.parametrize("body", [b"{not json", b"[1, 2]"])
def test_bodies_that_are_not_json_objects_are_undecodable(body: bytes) -> None:
    with pytest.raises(EventRejected) as rejected:
        normalise(raw(body), catalog(FIXED))

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
def test_severity_is_mapped_or_defaulted(body: object, severity: Severity) -> None:
    assert normalise(raw(body), catalog(FIXED, SEVERITY)).severity == severity


@pytest.mark.parametrize(
    "event",
    [raw({}, slug="unknown"), raw({}, source_type=SourceType.WEBSOCKET)],
    ids=["unknown slug", "other adapter type"],
)
def test_unknown_source_is_not_found(event: RawEvent) -> None:
    with pytest.raises(SourceSlugNotFound):
        normalise(event, catalog(FIXED))


@pytest.mark.parametrize("token", [None, "wrong"])
def test_missing_or_wrong_token_is_unauthenticated(token: str | None) -> None:
    with pytest.raises(Unauthenticated):
        normalise(raw({}, token=token), catalog(FIXED))
