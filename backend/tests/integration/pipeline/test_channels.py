import asyncio
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from pagercutie.alerts.service import AlertChanged
from pagercutie.core.db import create_engine, create_sessionmaker
from pagercutie.core.enums import Channel
from pagercutie.pipeline.dispatch.channels.email import EmailAdapter, SmtpSender
from pagercutie.pipeline.dispatch.channels.phone import PhoneAdapter
from pagercutie.pipeline.dispatch.channels.sms import SmsAdapter
from pagercutie.pipeline.dispatch.channels.ui import UiAdapter
from pagercutie.pipeline.dispatch.stage import ChannelAdapter, DeliveryJob, SendFailed, Sent
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

pytestmark = pytest.mark.anyio

PHONE = "+420123456789"


class RecordingSender(SmtpSender):
    """Records what the email adapter would send instead of opening an SMTP connection."""

    def __init__(self) -> None:
        super().__init__("unused", 0, "pagercutie@example.com")
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> Sent | SendFailed:
        self.sent.append((to, text))
        return Sent(at=datetime.now(UTC))


def job(user_id: uuid.UUID, channel: Channel, message: str = "Title\n\nBody") -> DeliveryJob:
    return DeliveryJob(
        delivery_id=uuid.uuid7(),
        alert_id=uuid.uuid7(),
        user_id=user_id,
        channel=channel,
        message=message,
        attempts=0,
        lease_until=datetime.now(UTC),
    )


async def make_user(session: AsyncSession, *, phone: str | None = PHONE, deleted: bool = False) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        display_name="Anna",
        phone=phone,
        timezone="Europe/Prague",
        role=GlobalRole.USER,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.parametrize(
    ("adapter_type", "channel", "event"),
    [(SmsAdapter, Channel.SMS, "channel.sms.sent"), (PhoneAdapter, Channel.PHONE, "channel.phone.sent")],
)
async def test_simulated_channel_succeeds_and_logs_the_masked_phone(
    session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    adapter_type: type[SmsAdapter | PhoneAdapter],
    channel: Channel,
    event: str,
) -> None:
    user = await make_user(session)

    with capture_logs() as logs:
        result = await adapter_type(sessionmaker).send(job(user.id, channel))

    assert isinstance(result, Sent)
    [entry] = logs
    assert entry["event"] == event
    assert entry["phone"] == "**********789"


@pytest.mark.parametrize("adapter_type", [SmsAdapter, PhoneAdapter])
async def test_simulated_channel_without_a_phone_fails_permanently(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], adapter_type: type[SmsAdapter | PhoneAdapter]
) -> None:
    user = await make_user(session, phone=None)

    result = await adapter_type(sessionmaker).send(job(user.id, Channel.SMS))

    assert result == SendFailed("User has no phone number", permanent=True)


@pytest.mark.parametrize("adapter_type", [SmsAdapter, PhoneAdapter])
async def test_simulated_channel_for_a_deleted_user_fails_permanently(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession], adapter_type: type[SmsAdapter | PhoneAdapter]
) -> None:
    user = await make_user(session, deleted=True)

    result = await adapter_type(sessionmaker).send(job(user.id, Channel.SMS))

    assert result == SendFailed("User is deleted", permanent=True)


async def test_email_goes_to_the_users_address(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(session, phone=None)
    sender = RecordingSender()

    result = await EmailAdapter(sessionmaker, sender).send(job(user.id, Channel.EMAIL, "Failed\n\nWorkflow wf-1"))

    assert isinstance(result, Sent)
    assert sender.sent == [(user.email, "Failed\n\nWorkflow wf-1")]


async def test_email_for_a_deleted_user_fails_permanently_without_sending(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(session, deleted=True)
    sender = RecordingSender()

    result = await EmailAdapter(sessionmaker, sender).send(job(user.id, Channel.EMAIL))

    assert result == SendFailed("User is deleted", permanent=True)
    assert sender.sent == []


async def test_email_for_an_unknown_user_fails_permanently(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    result = await EmailAdapter(sessionmaker, RecordingSender()).send(job(uuid.uuid7(), Channel.EMAIL))

    assert result == SendFailed("User not found", permanent=True)


async def test_ui_notify_reaches_a_listener_as_an_alert_change(engine: AsyncEngine, database_url: str) -> None:
    adapter: ChannelAdapter = UiAdapter(create_sessionmaker(engine))
    ui_job = job(uuid.uuid7(), Channel.UI)
    received: asyncio.Queue[str] = asyncio.Queue()
    listener = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await listener.add_listener(
            "alert_changed", lambda _conn, _pid, _channel, payload: received.put_nowait(payload)
        )

        result = await adapter.send(ui_job)

        assert isinstance(result, Sent)
        payload = await asyncio.wait_for(received.get(), timeout=5)
        assert AlertChanged.model_validate_json(payload) == AlertChanged(type="alert.updated", alert_id=ui_job.alert_id)
    finally:
        await listener.close()


async def test_ui_database_error_is_a_retryable_failure() -> None:
    engine = create_engine("postgresql+asyncpg://u:p@127.0.0.1:1/db")

    result = await UiAdapter(create_sessionmaker(engine)).send(job(uuid.uuid7(), Channel.UI))
    await engine.dispose()

    assert isinstance(result, SendFailed)
    assert result.permanent is False
