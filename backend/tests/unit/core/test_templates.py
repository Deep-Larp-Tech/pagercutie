import pytest
from pydantic import TypeAdapter, ValidationError

from pagercutie.core.fields import MISSING
from pagercutie.core.schemas import Template
from pagercutie.core.templates import CompiledTemplate, Placeholder, Text, parse, render

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
