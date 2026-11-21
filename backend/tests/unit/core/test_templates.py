import pytest
from pydantic import JsonValue

from pagercutie.core.enums import Channel
from pagercutie.core.templates import SMS_MAX_LENGTH, render, render_message

PAYLOAD: dict[str, JsonValue] = {
    "workflowId": "wf-1",
    "step": "settle",
    "amount": 12,
    "ratio": 0.5,
    "ok": False,
    "error": {"message": "timeout", "code": None},
    "tags": ["a", "é"],
}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("Settlement {{workflowId}} failed", "Settlement wf-1 failed"),
        ("Settlement {{payload.workflowId}} failed", "Settlement wf-1 failed"),
        ("{{ payload.error.message }}", "timeout"),
        ("{{workflowId}}/{{payload.step}}", "wf-1/settle"),
        ("{{missing}}|{{payload.missing}}|{{error.missing}}", "||"),
        ("{{error.code}}", ""),
        ("{{amount}} {{ratio}} {{ok}}", "12 0.5 false"),
        ("{{error}}", '{"message":"timeout","code":null}'),
        ("{{tags}}", '["a","é"]'),
        ("no placeholders", "no placeholders"),
        ("{{}}", ""),
        ("{single} {{unclosed", "{single} {{unclosed"),
    ],
)
def test_render_replaces_placeholders(template: str, expected: str) -> None:
    assert render(template, PAYLOAD) == expected


def test_render_does_not_expand_placeholders_inside_values() -> None:
    assert render("{{a}}", {"a": "{{b}}", "b": "x"}) == "{{b}}"


def test_render_against_an_empty_payload_renders_empty_strings() -> None:
    assert render("[{{a}}]", {}) == "[]"


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
