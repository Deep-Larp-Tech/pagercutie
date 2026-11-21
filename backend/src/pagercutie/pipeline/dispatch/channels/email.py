"""Email channel: SMTP to the server in `smtp_host` (Mailpit in the demo, SPEC §10)."""

from datetime import UTC, datetime
from email.message import EmailMessage
from typing import assert_never

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.pipeline.dispatch.channels.contacts import Contact, reach
from pagercutie.pipeline.dispatch.stage import DeliveryJob, SendFailed, Sent

SMTP_TIMEOUT_S = 10.0
"""Seconds to wait on connecting to, and on each reply from, the SMTP server."""

_PERMANENT_CODE = 500


def _failure(exc: aiosmtplib.SMTPException | OSError) -> SendFailed:
    """Maps an SMTP or connection error to a retryable failure, or a permanent one for 5xx replies."""
    match exc:
        case aiosmtplib.SMTPResponseException():
            permanent = exc.code >= _PERMANENT_CODE
        case aiosmtplib.SMTPRecipientsRefused():
            permanent = all(refused.code >= _PERMANENT_CODE for refused in exc.recipients)
        case _:
            permanent = False
    return SendFailed(f"{type(exc).__name__}: {exc}", permanent=permanent)


class SmtpSender:
    """Sends one message through an SMTP server; knows nothing about users or the database."""

    def __init__(self, host: str, port: int, sender: str) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._ehlo_name = sender.rpartition("@")[2]

    async def send(self, to: str, text: str) -> Sent | SendFailed:
        """Sends `text` (title, blank line, body; see `render_message`) with the title as the subject."""
        subject, _, rest = text.partition("\n")
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject.replace("\r", " ")
        message.set_content(rest.removeprefix("\n"))
        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                local_hostname=self._ehlo_name,
                timeout=SMTP_TIMEOUT_S,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            return _failure(exc)
        return Sent(at=datetime.now(UTC))


class EmailAdapter:
    """Looks up the user's address and hands the message to the `SmtpSender`."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], sender: SmtpSender) -> None:
        self._sessionmaker = sessionmaker
        self._sender = sender

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        match contact := await reach(self._sessionmaker, job.user_id):
            case SendFailed():
                return contact
            case Contact(email=address):
                return await self._sender.send(address, job.message)
            case _:
                assert_never(contact)
