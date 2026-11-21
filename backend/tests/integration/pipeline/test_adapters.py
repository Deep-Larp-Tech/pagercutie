import uuid

import grpc
import pytest
from google.protobuf import struct_pb2
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.integration.pipeline.test_evaluation import make_rule

from pagercutie.core.tokens import hash_token
from pagercutie.event_schemas.models import EventSchema
from pagercutie.pipeline.adapters import GrpcAdapter, IngestState, catalog_reloader, rule_set_reloader
from pagercutie.pipeline.dedup.windows import RedisWindowStore
from pagercutie.sources.models import Source
from pagercutie.sources.schemas import SeverityMapping, SourceType
from pagercutie.sources.service import INGEST_PATHS
from pagercutie.teams.models import Team
from pagercutie.v1 import ingest_pb2

pytestmark = pytest.mark.anyio


async def test_rule_set_reloader_loads_the_enabled_rules(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    team = Team(slug="payments", name="Payments")
    session.add(team)
    await session.flush()
    enabled, disabled = make_rule(team), make_rule(team, enabled=False)
    session.add_all([enabled, disabled])
    await session.commit()
    state = IngestState(sessionmaker=sessionmaker)

    await rule_set_reloader(state)()

    assert state.rule_set is not None
    assert [c.rule.id for c in state.rule_set.any_schema] == [enabled.id]


async def test_grpc_event_is_committed_and_accepted(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    team = Team(slug="ledger", name="Ledger")
    session.add(team)
    await session.flush()
    session.add_all(
        [
            Source(
                slug="ledger-grpc",
                name="Ledger gRPC",
                type=SourceType.PROTOBUF,
                team_id=team.id,
                severity=SeverityMapping(),
                enabled=True,
                token_hash=hash_token("secret"),
            ),
            EventSchema(
                name="entry",
                version=1,
                team_id=team.id,
                json_schema={"type": "object", "required": ["amount"], "properties": {"amount": {"type": "integer"}}},
            ),
        ]
    )
    await session.commit()
    state = IngestState(sessionmaker=sessionmaker, window_store=RedisWindowStore(redis))
    await catalog_reloader(state)()
    await rule_set_reloader(state)()
    server, port = GrpcAdapter().server(state, "127.0.0.1:0")
    await server.start()
    payload = struct_pb2.Struct()
    payload.update({"amount": 1200})

    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            send = channel.unary_unary(
                INGEST_PATHS[SourceType.PROTOBUF],
                request_serializer=ingest_pb2.Event.SerializeToString,
                response_deserializer=ingest_pb2.Accepted.FromString,
            )
            accepted = await send(
                ingest_pb2.Event(payload=payload),
                metadata=(("authorization", "Bearer secret"), ("source-slug", "ledger-grpc")),
            )
    finally:
        await server.stop(None)

    assert uuid.UUID(accepted.event_id).version == 7
    assert accepted.matches == 0
