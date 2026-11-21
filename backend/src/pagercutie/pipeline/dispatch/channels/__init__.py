"""Channel adapters of the dispatch stage, one module per channel (SPEC §10)."""

from collections.abc import Mapping
from typing import assert_never

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.enums import Channel
from pagercutie.core.settings import Settings
from pagercutie.pipeline.dispatch.channels.email import EmailAdapter, SmtpSender
from pagercutie.pipeline.dispatch.channels.phone import PhoneAdapter
from pagercutie.pipeline.dispatch.channels.sms import SmsAdapter
from pagercutie.pipeline.dispatch.channels.ui import UiAdapter
from pagercutie.pipeline.dispatch.stage import ChannelAdapter


def build_adapters(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> Mapping[Channel, ChannelAdapter]:
    """One adapter per `Channel`; a new channel fails type checking until it has one."""
    return {channel: _adapter(channel, settings, sessionmaker) for channel in Channel}


def _adapter(channel: Channel, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]) -> ChannelAdapter:
    match channel:
        case Channel.EMAIL:
            return EmailAdapter(sessionmaker, SmtpSender(settings.smtp_host, settings.smtp_port, settings.smtp_from))
        case Channel.SMS:
            return SmsAdapter(sessionmaker)
        case Channel.PHONE:
            return PhoneAdapter(sessionmaker)
        case Channel.UI:
            return UiAdapter(sessionmaker)
        case _:
            assert_never(channel)
