"""Cross-stage tests with nothing replaced: real normalise, evaluate, dedup, routing and runbook start (SPEC §5.1)."""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.testclient import TestClient

from pagercutie.alerts.models import Alert, Delivery, RunbookRun
from pagercutie.alerts.schemas import DeliveryStatus
from pagercutie.core.enums import Channel, Severity
from pagercutie.core.settings import Settings
from pagercutie.core.tokens import hash_token
from pagercutie.event_schemas.models import EventSchema
from pagercutie.main import create_app
from pagercutie.pipeline import orchestrator
from pagercutie.pipeline.dedup.windows import RedisWindowStore
from pagercutie.pipeline.dedup.worker import flush_counters
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import RawEvent
from pagercutie.pipeline.state import ingest_state
from pagercutie.rules.ast import Exists
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, UserRecipient
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import Manual
from pagercutie.sources.models import Source
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.teams.models import Membership, Team
from pagercutie.teams.schemas import TeamRole
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

TOKEN = "e2e-token"
WS_TOKEN = "e2e-ws-token"


@dataclass(frozen=True)
class World:
    """Committed rows of one team whose webhook source feeds one rule with a runbook."""

    team_id: uuid.UUID
    user_id: uuid.UUID
    source_slug: str
    ws_source_slug: str
    rule_id: uuid.UUID
    runbook_id: uuid.UUID
    schema_id: uuid.UUID


@pytest.fixture
async def world(engine: AsyncEngine) -> AsyncGenerator[World]:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:8]
    async with sessionmaker() as session, session.begin():
        team = Team(slug=f"e2e-{suffix}", name="End to end")
        user = User(email=f"{suffix}@example.com", display_name="Anna", timezone="UTC", role=GlobalRole.USER)
        session.add_all([team, user])
        await session.flush()
        schema = EventSchema(
            name="workflow", version=1, team_id=team.id, json_schema={"type": "object", "required": ["workflowId"]}
        )
        source = Source(
            slug=f"e2e-{suffix}",
            name="End to end",
            type=SourceType.WEBHOOK,
            team_id=team.id,
            severity=SeverityMapping(),
            enabled=True,
            token_hash=hash_token(TOKEN),
        )
        ws_source = Source(
            slug=f"e2e-ws-{suffix}",
            name="End to end over WebSocket",
            type=SourceType.WEBSOCKET,
            team_id=team.id,
            severity=SeverityMapping(),
            enabled=True,
            token_hash=hash_token(WS_TOKEN),
        )
        runbook = Runbook(
            slug=f"e2e-{suffix}",
            title="Check",
            team_id=team.id,
            format=RunbookFormat.STRUCTURED,
            original="",
            steps=[Manual(action="manual", text="Check {{workflowId}}")],
        )
        session.add_all(
            [Membership(team_id=team.id, user_id=user.id, role=TeamRole.MEMBER), schema, source, ws_source, runbook]
        )
        await session.flush()
        rule = Rule(
            name="Workflow failed",
            description=None,
            enabled=True,
            team_id=team.id,
            user_id=None,
            schema_ids=[schema.id],
            condition=Exists(op="exists", field="payload.workflowId"),
            dedup=Dedup(fields=["payload.workflowId"]),
            # UI only: the test stack has no SMTP server, so nothing is left retrying for other tests to claim.
            routing=Routing(recipients=[UserRecipient(type="user", user_id=user.id)], channels=[Channel.UI]),
            presentation=Presentation(
                title="Workflow {{workflowId}} failed", severity=Severity.ERROR, colour=Colour.RED
            ),
            runbook_id=runbook.id,
        )
        session.add(rule)
    world = World(
        team_id=team.id,
        user_id=user.id,
        source_slug=source.slug,
        ws_source_slug=ws_source.slug,
        rule_id=rule.id,
        runbook_id=runbook.id,
        schema_id=schema.id,
    )
    yield world
    async with sessionmaker() as session, session.begin():
        alert_ids = select(Alert.id).where(Alert.rule_id == world.rule_id)
        await session.execute(update(Delivery).where(Delivery.alert_id.in_(alert_ids)).values(digest_id=None))
        await session.execute(delete(Delivery).where(Delivery.alert_id.in_(alert_ids)))
        await session.execute(delete(RunbookRun).where(RunbookRun.alert_id.in_(alert_ids)))
        await session.execute(delete(Alert).where(Alert.rule_id == world.rule_id))
        await session.execute(delete(Rule).where(Rule.id == world.rule_id))
        await session.execute(delete(Runbook).where(Runbook.id == world.runbook_id))
        await session.execute(delete(Source).where(Source.slug.in_([world.source_slug, world.ws_source_slug])))
        await session.execute(delete(EventSchema).where(EventSchema.id == world.schema_id))
        await session.execute(delete(Team).where(Team.id == world.team_id))
        await session.execute(delete(User).where(User.id == world.user_id))


def make_app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    # `create_app` turns on structlog's logger cache; cached loggers would escape `capture_logs` in later tests.
    structlog.configure(cache_logger_on_first_use=False)
    return app


async def wait_until_loaded(app: FastAPI) -> None:
    """The listener loads the source catalog and the rule set once it connects."""
    state = ingest_state(app)
    for _ in range(100):
        if state.catalog is not None and state.rule_set is not None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("ingest caches did not load")


async def test_a_webhook_event_opens_an_alert_with_deliveries_and_a_runbook_run(
    settings: Settings, redis_url: str, redis: Redis, engine: AsyncEngine, world: World
) -> None:
    app = make_app(settings.model_copy(update={"redis_url": redis_url}))

    async with app.router.lifespan_context(app):
        await wait_until_loaded(app)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/ingest/{world.source_slug}",
                json={"workflowId": "wf-42", "error": "timeout"},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )

    assert response.status_code == 202
    assert response.json()["matches"] == 1
    async with async_sessionmaker(engine)() as session:
        alert = (await session.scalars(select(Alert).where(Alert.rule_id == world.rule_id))).one()
        deliveries = (await session.scalars(select(Delivery).where(Delivery.alert_id == alert.id))).all()
        run = (await session.scalars(select(RunbookRun).where(RunbookRun.alert_id == alert.id))).one()
    assert (alert.title, alert.team_id, alert.occurrences) == ("Workflow wf-42 failed", world.team_id, 1)
    assert [(d.user_id, d.channel) for d in deliveries] == [(world.user_id, Channel.UI)]
    assert deliveries[0].status in {DeliveryStatus.PENDING, DeliveryStatus.SENT}
    assert run.runbook_id == world.runbook_id


def exchange_frames(settings: Settings, world: World, frames: int) -> list[dict[str, object]]:
    """Sends `frames` events on one WebSocket of a running app and returns the replies; blocking."""
    app = make_app(settings)
    with TestClient(app) as client:
        state = ingest_state(app)
        for _ in range(100):
            if state.catalog is not None and state.rule_set is not None:
                break
            time.sleep(0.05)
        replies: list[dict[str, object]] = []
        with client.websocket_connect(
            f"/ingest/{world.ws_source_slug}/ws", headers={"Authorization": f"Bearer {WS_TOKEN}"}
        ) as socket:
            for _ in range(frames):
                socket.send_text(json.dumps({"workflowId": "wf-ws"}))
                replies.append(socket.receive_json())
    return replies


async def test_a_rate_limited_websocket_frame_gets_an_error_frame_and_the_connection_stays_open(
    settings: Settings, redis_url: str, redis: Redis, world: World
) -> None:
    limited = settings.model_copy(
        update={"redis_url": redis_url, "ingest_source_burst": 1, "ingest_source_rate_per_second": 0.01}
    )

    # TestClient runs the app on its own event loop, so it gets a thread of its own.
    accepted, refused, again = await asyncio.to_thread(exchange_frames, limited, world, 3)

    assert accepted["matches"] == 1
    assert refused == {"status": 429, "detail": f"Source {world.ws_source_slug} is over its rate limit"}
    assert again["status"] == 429


async def test_two_concurrent_events_of_one_fingerprint_make_one_alert_and_count_both(
    redis: Redis, engine: AsyncEngine, world: World
) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    windows = RedisWindowStore(redis)
    async with sessionmaker() as session:
        catalog = await ingest.load_catalog(session)
        rules = await evaluation.load_rule_set(session)
    source = ingest.authenticate(catalog, world.source_slug, SourceType.WEBHOOK, TOKEN)
    schemas = ingest.SchemaCache(ingest.team_schema_query(sessionmaker))
    body = json.dumps({"workflowId": "wf-7"}).encode()

    results = await asyncio.gather(
        *(
            orchestrator.process_event(RawEvent(source=source, body=body), sessionmaker, schemas.load, rules, windows)
            for _ in range(2)
        )
    )
    await flush_counters(sessionmaker, windows)

    assert [result.matches for result in results] == [1, 1]
    async with sessionmaker() as session:
        alerts = (await session.scalars(select(Alert).where(Alert.rule_id == world.rule_id))).all()
        deliveries = (await session.scalars(select(Delivery).where(Delivery.alert_id == alerts[0].id))).all()
    assert len(alerts) == 1
    assert alerts[0].occurrences == 2
    # The second event repeated: one notification round, so one delivery.
    assert len(deliveries) == 1
