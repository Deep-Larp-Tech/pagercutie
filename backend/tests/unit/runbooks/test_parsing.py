import pytest

from pagercutie.core.errors import InvalidInput
from pagercutie.rules.ast import And, Compare
from pagercutie.runbooks.parsing import parse_runbook
from pagercutie.runbooks.parsing.guards import parse_guard
from pagercutie.runbooks.parsing.text import MAX_STEP_TEXT
from pagercutie.runbooks.schemas import RunbookFormat
from pagercutie.runbooks.steps import (
    CallWebhook,
    Escalate,
    HttpGet,
    Manual,
    RestartService,
    RetryWorkflow,
    StepGuard,
    Wait,
)

# REQUIREMENTS §6.2 sample 1, SPEC §11.4 (ADR-0021).
SETTLEMENT_TIMEOUT = """\
runbook: settlement-timeout
matches:
  type: WORKFLOW_FAILED
  "error.code": TIMEOUT
steps:
  - check: "Is counterparty-service healthy?"
    action: http_get
    url: "http://counterparty-service/health"
  - action: retry_workflow
    workflowId: "{{workflowId}}"
    approval: none
  - if: "retry fails twice"
    action: escalate
    team: counterparty-support
    approval: required
"""

# REQUIREMENTS §6.2 sample 2.
PAYMENTS_MARKDOWN = """\
# HighErrorRate on payments-api
1. Open the payments dashboard and check if errors are in one region only.
2. If one region: fail traffic over to the other region (needs approval from the team lead).
3. If all regions: check the last deployment and roll it back.
4. Post an update in the #payments-incidents channel every 15 minutes.
"""

# REQUIREMENTS §6.2 sample 3.
PRICING_TEXT = (
    "When pricing latency goes over a second, it's usually the cache. Restart the pricing-engine instance\n"
    "named in the alert, wait 2 minutes, and if latency is still high, call the pricing on-call person."
)


def manual(text: str) -> Manual:
    return Manual(action="manual", text=text)


def errors(exc: pytest.ExceptionInfo[InvalidInput]) -> list[tuple[tuple[str | int, ...], str]]:
    return [(error.loc, error.msg) for error in exc.value.errors]


# --- structured -------------------------------------------------------------------------------------------------


def test_settlement_timeout_parses_into_executable_steps_with_a_structured_guard() -> None:
    parsed = parse_runbook(RunbookFormat.STRUCTURED, SETTLEMENT_TIMEOUT)

    assert parsed.attach == And(
        op="and",
        args=[
            Compare(op="eq", field="payload.type", value="WORKFLOW_FAILED"),
            Compare(op="eq", field="payload.error.code", value="TIMEOUT"),
        ],
    )
    assert parsed.steps == [
        HttpGet(action="http_get", check="Is counterparty-service healthy?", url="http://counterparty-service/health"),
        RetryWorkflow(action="retry_workflow", workflow_id="{{workflowId}}", approval="none"),
        Escalate(
            action="escalate",
            if_=StepGuard(step=1, failures_gte=2),
            team="counterparty-support",
            approval="required",
        ),
    ]
    assert parsed.warnings == []


def test_unrecognised_guard_stays_a_question_with_a_warning() -> None:
    original = SETTLEMENT_TIMEOUT.replace("retry fails twice", "the counterparty looks unhappy")

    parsed = parse_runbook(RunbookFormat.STRUCTURED, original)

    assert parsed.steps[2].if_ == "the counterparty looks unhappy"
    assert parsed.warnings == [
        "Step 3: the guard 'the counterparty looks unhappy' is not recognised; a human answers it"
    ]


def test_structured_guard_written_as_a_mapping_is_kept() -> None:
    original = SETTLEMENT_TIMEOUT.replace('if: "retry fails twice"', "if: {step: 1, failures_gte: 3}")

    assert parse_runbook(RunbookFormat.STRUCTURED, original).steps[2].if_ == StepGuard(step=1, failures_gte=3)


def test_structured_guard_on_a_later_step_is_rejected() -> None:
    original = SETTLEMENT_TIMEOUT.replace('if: "retry fails twice"', "if: {step: 2, failures_gte: 1}")

    with pytest.raises(InvalidInput) as exc:
        parse_runbook(RunbookFormat.STRUCTURED, original)

    assert errors(exc) == [(("original", "steps", 2, "if", "step"), "must be an earlier step")]


def test_runbook_without_matches_has_no_attach() -> None:
    original = "runbook: wait-a-bit\nsteps:\n  - action: wait\n    seconds: 60\n"

    parsed = parse_runbook(RunbookFormat.STRUCTURED, original)

    assert parsed.attach is None
    assert parsed.steps == [Wait(action="wait", seconds=60)]


@pytest.mark.parametrize(
    ("original", "loc"),
    [
        ("runbook: x\nsteps: [", ("original",)),
        ("just a sentence", ("original",)),
        ("runbook: x\nsteps: []\n", ("original", "steps")),
        ("runbook: x\nsteps:\n  - action: launch_rocket\n", ("original", "steps", 0)),
        ("runbook: x\nsteps:\n  - action: wait\n", ("original", "steps", 0, "wait", "seconds")),
        ("runbook: x\nowner: me\nsteps:\n  - action: wait\n    seconds: 1\n", ("original", "owner")),
    ],
)
def test_invalid_structured_runbook_is_rejected_with_the_location(original: str, loc: tuple[str | int, ...]) -> None:
    with pytest.raises(InvalidInput) as exc:
        parse_runbook(RunbookFormat.STRUCTURED, original)

    assert loc in [error_loc for error_loc, _ in errors(exc)]


def test_yaml_aliases_are_rejected() -> None:
    original = "runbook: x\nsteps:\n  - &w {action: wait, seconds: 1}\n  - *w\n"

    with pytest.raises(InvalidInput) as exc:
        parse_runbook(RunbookFormat.STRUCTURED, original)

    assert errors(exc) == [(("original",), "YAML aliases (*name) are not supported")]


def test_matches_field_too_long_for_a_condition_is_rejected() -> None:
    original = f"runbook: x\nmatches:\n  {'f' * 200}: 1\nsteps:\n  - action: wait\n    seconds: 1\n"

    with pytest.raises(InvalidInput) as exc:
        parse_runbook(RunbookFormat.STRUCTURED, original)

    assert [loc for loc, _ in errors(exc)] == [("original", "matches")]


@pytest.mark.parametrize("format", list(RunbookFormat))
def test_blank_text_is_rejected_in_every_format(format: RunbookFormat) -> None:
    with pytest.raises(InvalidInput) as exc:
        parse_runbook(format, " \n\t")

    assert errors(exc) == [(("original",), "must not be blank")]


# --- guards -----------------------------------------------------------------------------------------------------

EARLIER = [
    HttpGet(action="http_get", url="http://x/health"),
    RetryWorkflow(action="retry_workflow", workflow_id="{{workflowId}}"),
    RestartService(action="restart_service", service="api"),
    RetryWorkflow(action="retry_workflow", workflow_id="{{other}}"),
    CallWebhook(action="call_webhook", url="http://hook"),
]


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("retry fails twice", StepGuard(step=3, failures_gte=2)),
        ("If the retry fails once.", StepGuard(step=3, failures_gte=1)),
        ("retry_workflow failed 3 times", StepGuard(step=3, failures_gte=3)),
        ("Restart has failed at least two times", StepGuard(step=2, failures_gte=2)),
        ("health check fails thrice", StepGuard(step=0, failures_gte=3)),
        ("webhook fails 1 time", StepGuard(step=4, failures_gte=1)),
        ("step 2 fails twice", StepGuard(step=1, failures_gte=2)),
        ("Step #1 fails once", StepGuard(step=0, failures_gte=1)),
    ],
)
def test_known_guard_phrases_resolve_to_the_nearest_earlier_step(phrase: str, expected: StepGuard) -> None:
    assert parse_guard(phrase, EARLIER) == expected


@pytest.mark.parametrize(
    "phrase",
    [
        "retry fails sometimes",
        "escalate fails twice",
        "step 6 fails once",
        "step 0 fails once",
        "retry fails 0 times",
        "retry fails 1001 times",
        "latency is still high",
    ],
)
def test_other_guard_phrases_are_not_recognised(phrase: str) -> None:
    assert parse_guard(phrase, EARLIER) is None


def test_guard_with_no_earlier_steps_is_not_recognised() -> None:
    assert parse_guard("retry fails twice", []) is None


# --- markdown ---------------------------------------------------------------------------------------------------


def test_payments_markdown_items_become_manual_steps() -> None:
    parsed = parse_runbook(RunbookFormat.MARKDOWN, PAYMENTS_MARKDOWN)

    assert parsed.attach is None
    assert parsed.steps == [
        manual("Open the payments dashboard and check if errors are in one region only."),
        manual("If one region: fail traffic over to the other region (needs approval from the team lead)."),
        manual("If all regions: check the last deployment and roll it back."),
        manual("Post an update in the #payments-incidents channel every 15 minutes."),
    ]
    assert parsed.warnings == []


def test_markdown_bullets_checklists_and_continuation_lines() -> None:
    original = "- [ ] Check the queue\n  depth in Grafana\n* [x] Drain it\n+ Tell #ops\n"

    assert parse_runbook(RunbookFormat.MARKDOWN, original).steps == [
        manual("Check the queue depth in Grafana"),
        manual("Drain it"),
        manual("Tell #ops"),
    ]


def test_markdown_links_stay_in_items_and_prose_links_become_open_steps() -> None:
    original = (
        "See [the dashboard](https://grafana.example.com/d/1).\n"
        "1. Check [logs](https://logs.example.com) for {{service}}\n"
        "\n"
        "Background: https://wiki.example.com/payments\n"
    )

    parsed = parse_runbook(RunbookFormat.MARKDOWN, original)

    assert parsed.steps == [
        manual("Open [the dashboard](https://grafana.example.com/d/1)"),
        manual("Check [logs](https://logs.example.com) for {{service}}"),
        manual("Open https://wiki.example.com/payments"),
    ]
    assert parsed.warnings == ["Text outside list items is shown only in the original"]


def test_markdown_ignores_list_items_inside_code_fences() -> None:
    original = "1. Run this:\n\n```\n- not a step\n```\n2. Done\n"

    assert [
        step.text for step in parse_runbook(RunbookFormat.MARKDOWN, original).steps if isinstance(step, Manual)
    ] == [
        "Run this:",
        "Done",
    ]


def test_markdown_without_items_falls_back_to_free_text() -> None:
    parsed = parse_runbook(RunbookFormat.MARKDOWN, "# Title\n\nRestart it.")

    assert parsed.steps == [manual("# Title\n\nRestart it.")]
    assert parsed.warnings == ["No list items found; the text is shown as free text"]


# --- text -------------------------------------------------------------------------------------------------------


def test_pricing_free_text_becomes_one_manual_step() -> None:
    parsed = parse_runbook(RunbookFormat.TEXT, f"\n{PRICING_TEXT}\n\n")

    assert parsed.steps == [manual(PRICING_TEXT)]
    assert parsed.warnings == []


def test_long_text_is_split_at_paragraphs_into_steps_that_fit() -> None:
    paragraph = ("word " * 300).strip()  # 1499 characters
    original = "\n\n".join([paragraph, paragraph, "x" * 4500])

    parsed = parse_runbook(RunbookFormat.TEXT, original)

    texts = [step.text for step in parsed.steps if isinstance(step, Manual)]
    assert texts[:2] == [paragraph, paragraph]
    assert "".join(texts[2:]) == "x" * 4500
    assert all(len(text) <= MAX_STEP_TEXT for text in texts)
    assert parsed.warnings == [f"The text is longer than {MAX_STEP_TEXT} characters; split it into 5 manual steps"]


# --- link -------------------------------------------------------------------------------------------------------


def test_link_becomes_one_open_the_runbook_step() -> None:
    parsed = parse_runbook(RunbookFormat.LINK, "  https://wiki.example.com/x/Payments+Runbook\n")

    assert parsed.steps == [manual("Open the runbook: https://wiki.example.com/x/Payments+Runbook")]
    assert parsed.warnings == []


def test_link_that_is_not_a_url_is_shown_as_text() -> None:
    parsed = parse_runbook(RunbookFormat.LINK, "Confluence > Payments > Runbook")

    assert parsed.steps == [manual("Confluence > Payments > Runbook")]
    assert parsed.warnings == ["The text is not a single http(s) URL; it is shown as free text"]
