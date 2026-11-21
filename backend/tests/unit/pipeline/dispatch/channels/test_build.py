from pagercutie.core.db import create_engine, create_sessionmaker
from pagercutie.core.enums import Channel
from pagercutie.core.settings import Settings
from pagercutie.pipeline.dispatch.channels import build_adapters
from pagercutie.pipeline.dispatch.channels.email import EmailAdapter
from pagercutie.pipeline.dispatch.channels.phone import PhoneAdapter
from pagercutie.pipeline.dispatch.channels.sms import SmsAdapter
from pagercutie.pipeline.dispatch.channels.ui import UiAdapter


def test_build_adapters_covers_every_channel() -> None:
    settings = Settings()
    adapters = build_adapters(settings, create_sessionmaker(create_engine(settings.database_url)))

    assert set(adapters) == set(Channel)
    assert isinstance(adapters[Channel.EMAIL], EmailAdapter)
    assert isinstance(adapters[Channel.SMS], SmsAdapter)
    assert isinstance(adapters[Channel.PHONE], PhoneAdapter)
    assert isinstance(adapters[Channel.UI], UiAdapter)
