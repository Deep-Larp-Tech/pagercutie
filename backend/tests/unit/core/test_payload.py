import pytest
from pydantic import JsonValue

from pagercutie.core.payload import field_value

PAYLOAD: dict[str, JsonValue] = {
    "amount": 5,
    "error": {"code": "TIMEOUT", "meta": {"retry": True}, "0": "zero"},
    "tags": ["a"],
    "items": [{"sku": "X-1"}, {"sku": "X-2"}],
    "nothing": None,
}


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
        ("nothing", None),
        ("tags.0", "a"),
        ("items.1.sku", "X-2"),
        ("error.0", "zero"),
        ("tags.1", None),
        ("tags.-1", None),
        ("tags.x", None),
    ],
)
def test_field_value_follows_objects_and_array_indexes(path: str, expected: JsonValue) -> None:
    assert field_value(PAYLOAD, path) == expected
