import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import AlertStatus, DeliveryStatus
from pagercutie.core.enums import Channel, Severity
from pagercutie.rules.ast import Compare
from pagercutie.rules.models import Rule
from pagercutie.rules.schemas import Colour, Dedup, Presentation, Routing, UserRecipient
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio


@pytest.fixture
async def anna(session: AsyncSession) -> User:
    user = User(email="anna@example.com", display_name="Anna", timezone="Europe/Prague", role=GlobalRole.USER)
    session.add(user)
    await session.flush()
    return user


async def test_messages_lists_own_deliveries_newest_first_filtered_by_channel(
    client: AsyncClient, session: AsyncSession, anna: User
) -> None:
    other = User(email="bob@example.com", display_name="Bob", timezone="UTC", role=GlobalRole.USER)
    session.add(other)
    await session.flush()
    rule = Rule(
        name="Workflow failed",
        enabled=True,
        team_id=None,
        user_id=anna.id,
        schema_ids=[],
        condition=Compare(op="eq", field="payload.type", value="failed"),
        dedup=Dedup(fields=[]),
        routing=Routing(recipients=[UserRecipient(type="user", user_id=anna.id)]),
        presentation=Presentation(title="Failed", severity=Severity.ERROR, colour=Colour.RED),
    )
    session.add(rule)
    await session.flush()
    now = datetime.now(UTC)
    alert = Alert(
        rule_id=rule.id,
        team_id=None,
        fingerprint="f" * 64,
        status=AlertStatus.OPEN,
        severity=Severity.ERROR,
        colour=Colour.RED,
        title="Failed",
        fields=[],
        occurrences=1,
        first_seen_at=now,
        last_seen_at=now,
        escalated_team_ids=[],
        payload={},
    )
    session.add(alert)
    await session.flush()

    def delivery(user: User, channel: Channel, message: str) -> Delivery:
        return Delivery(
            id=uuid.uuid7(),
            alert_id=alert.id,
            user_id=user.id,
            channel=channel,
            status=DeliveryStatus.SENT,
            message=message,
            received_at=now,
        )

    for d in [
        delivery(anna, Channel.SMS, "first"),
        delivery(anna, Channel.EMAIL, "email"),
        delivery(anna, Channel.PHONE, "second"),
        delivery(other, Channel.SMS, "bob's"),
    ]:
        session.add(d)
        await session.flush()
    await client.post("/auth/login", json={"email": anna.email})

    response = await client.get("/me/messages", params={"channel": ["sms", "phone"]})

    assert response.status_code == 200
    assert [m["message"] for m in response.json()] == ["second", "first"]
