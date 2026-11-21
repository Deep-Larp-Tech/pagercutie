import pytest
from pydantic import TypeAdapter, ValidationError

from pagercutie.core.enums import Channel
from pagercutie.core.fields import MISSING
from pagercutie.core.schemas import Template
from pagercutie.core.templates import (
    SMS_MAX_LENGTH,
    CompiledTemplate,
    Placeholder,
    Text,
    parse,
    render,
    render_message,
)

TEMPLATE = TypeAdapter(Template)


def test_parse_splits_text_and_placeholders_in_order() -> None:
    assert parse("Workflow {{ payload.workflowId }} failed {{n}}") == CompiledTemplate(
        (Text("Workflow "), Placeholder(("payload", "workflowId")), Text(" failed "), Placeholder(("n",)))
    )


def test_render_asks_the_resolver_for_each_placeholder_path() -> None:
    asked: list[tuple[str, ...]] = []

    def resolve(path: tuple[str, ...]) -> str:
        asked.append(path)
        return "/".join(path)

    assert render(parse("{{a.b}}-{{c}}"), resolve) == "a/b-c"
    assert asked == [("a", "b"), ("c",)]


def test_a_missing_value_renders_empty() -> None:
    assert render(parse("[{{a}}]"), lambda _: MISSING) == "[]"


def test_the_template_type_accepts_a_valid_template() -> None:
    assert TEMPLATE.validate_python("Workflow {{workflowId}} failed") == "Workflow {{workflowId}} failed"


@pytest.mark.parametrize("text", ["Workflow {{workflowId", "{{ x | upper }}"])
def test_the_template_type_rejects_a_syntax_error(text: str) -> None:
    with pytest.raises(ValidationError, match=r"not a field path|unclosed"):
        TEMPLATE.validate_python(text)


def test_render_message_cuts_sms_and_phone_to_the_title() -> None:
    title = "x" * (SMS_MAX_LENGTH + 40)
    for channel in (Channel.SMS, Channel.PHONE):
        assert render_message(channel, title, "body") == "x" * SMS_MAX_LENGTH


def test_render_message_keeps_a_short_sms_title_whole() -> None:
    assert render_message(Channel.SMS, "Settlement failed", "ignored") == "Settlement failed"


def test_render_message_email_separates_title_and_body_with_a_blank_line() -> None:
    assert render_message(Channel.EMAIL, "Title", "Body") == "Title\n\nBody"


def test_render_message_ui_separates_title_and_body_with_a_newline() -> None:
    assert render_message(Channel.UI, "Title", "Body") == "Title\nBody"


@pytest.mark.parametrize("channel", [Channel.EMAIL, Channel.UI])
@pytest.mark.parametrize("body", [None, ""])
def test_render_message_without_a_body_is_the_title(channel: Channel, body: str | None) -> None:
    assert render_message(channel, "Title", body) == "Title"
