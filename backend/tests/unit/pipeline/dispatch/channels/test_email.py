import email
import socket
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from email.message import EmailMessage
from email.policy import default

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Envelope, Session

from pagercutie.pipeline.dispatch.channels.email import SmtpSender
from pagercutie.pipeline.dispatch.stage import SendFailed, Sent

pytestmark = pytest.mark.anyio

SENDER = "pagercutie@example.com"
OK = "250 OK"


class Inbox:
    """An SMTP handler that stores accepted messages and answers RCPT and DATA with fixed replies."""

    def __init__(self, rcpt_reply: str = OK, data_reply: str = OK) -> None:
        self.rcpt_reply = rcpt_reply
        self.data_reply = data_reply
        self.messages: list[EmailMessage] = []
        self.recipients: list[str] = []

    async def handle_RCPT(
        self, server: SMTP, session: Session, envelope: Envelope, address: str, rcpt_options: list[str]
    ) -> str:
        if self.rcpt_reply == OK:
            envelope.rcpt_tos.append(address)
            self.recipients.append(address)
        return self.rcpt_reply

    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:
        parsed = email.message_from_bytes(envelope.original_content or b"", policy=default)
        assert isinstance(parsed, EmailMessage)
        self.messages.append(parsed)
        return self.data_reply


def body(message: EmailMessage) -> str:
    """The text body with the CRLF line endings SMTP adds undone."""
    return message.get_content().replace("\r\n", "\n").strip()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextmanager
def serve(inbox: Inbox) -> Generator[int]:
    port = free_port()
    controller = Controller(inbox, hostname="127.0.0.1", port=port, server_hostname="localhost")
    controller.start()
    try:
        yield port
    finally:
        controller.stop()


@pytest.fixture
def inbox() -> Inbox:
    return Inbox()


@pytest.fixture
def port(inbox: Inbox) -> Iterator[int]:
    with serve(inbox) as port:
        yield port


async def test_send_delivers_title_as_subject_and_the_rest_as_body(inbox: Inbox, port: int) -> None:
    sender = SmtpSender("127.0.0.1", port, SENDER)

    result = await sender.send("anna@example.com", "Settlement failed\n\nWorkflow wf-1 failed\nin prod")

    assert isinstance(result, Sent)
    [message] = inbox.messages
    assert message["Subject"] == "Settlement failed"
    assert message["From"] == SENDER
    assert message["To"] == "anna@example.com"
    assert body(message) == "Workflow wf-1 failed\nin prod"
    assert inbox.recipients == ["anna@example.com"]


async def test_send_without_a_body_sends_an_empty_body(inbox: Inbox, port: int) -> None:
    result = await SmtpSender("127.0.0.1", port, SENDER).send("anna@example.com", "Only a title")

    assert isinstance(result, Sent)
    [message] = inbox.messages
    assert message["Subject"] == "Only a title"
    assert body(message) == ""


async def test_send_keeps_non_ascii_text(inbox: Inbox, port: int) -> None:
    result = await SmtpSender("127.0.0.1", port, SENDER).send("anna@example.com", "Platba selhala ✓\n\nČást těla")

    assert isinstance(result, Sent)
    [message] = inbox.messages
    assert message["Subject"] == "Platba selhala ✓"
    assert body(message) == "Část těla"


async def test_send_replaces_a_carriage_return_in_the_title(inbox: Inbox, port: int) -> None:
    result = await SmtpSender("127.0.0.1", port, SENDER).send("anna@example.com", "Two\rwords\n\nbody")

    assert isinstance(result, Sent)
    assert inbox.messages[0]["Subject"] == "Two words"


@pytest.mark.parametrize(
    ("rcpt_reply", "data_reply", "permanent"),
    [
        ("450 Mailbox busy", OK, False),
        ("550 No such user", OK, True),
        (OK, "451 Try again later", False),
        (OK, "554 Rejected as spam", True),
    ],
)
async def test_send_classifies_smtp_replies_by_class(rcpt_reply: str, data_reply: str, permanent: bool) -> None:
    rejecting = Inbox(rcpt_reply=rcpt_reply, data_reply=data_reply)
    with serve(rejecting) as port:
        result = await SmtpSender("127.0.0.1", port, SENDER).send("anna@example.com", "Title\n\nBody")

    assert isinstance(result, SendFailed)
    assert result.permanent is permanent


async def test_send_to_a_closed_port_is_retryable() -> None:
    result = await SmtpSender("127.0.0.1", free_port(), SENDER).send("anna@example.com", "Title")

    assert isinstance(result, SendFailed)
    assert result.permanent is False
