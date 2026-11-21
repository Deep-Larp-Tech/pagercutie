import pytest
from pydantic import JsonValue

from pagercutie.core.payload import field_value

PAYLOAD: dict[str, JsonValue] = {"amount": 5, "error": {"code": "TIMEOUT", "meta": {"retry": True}}, "tags": ["a"]}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("amount", 5),
        ("error.code", "TIMEOUT"),
        ("error.meta.retry", True),
        ("error.meta", {"retry": True}),
        ("missing", None),
        ("error.missing", None),
        ("amount.code", None),
        ("tags.0", None),
    ],
)
def test_field_value_walks_objects_only(path: str, expected: JsonValue) -> None:
    assert field_value(PAYLOAD, path) == expected
