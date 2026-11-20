import json

import pytest

from larper.core.errors import InvalidInput
from larper.imports.parsing import parse_rows
from larper.imports.schemas import ImportFormat

HEADER = "first_name,last_name,skill_name,skill_difficulty,occurred_at,believability,description,location"


def test_csv_rows_are_parsed_and_empty_location_is_none() -> None:
    content = f"{HEADER}\nStas,Yurich,Vim,7,2026-01-01T10:00:00+01:00,9,Exited Vim,\n".encode()

    [row] = parse_rows(content, ImportFormat.CSV)

    assert (row.skill_difficulty, row.believability, row.location) == (7, 9, None)
    assert row.occurred_at.isoformat() == "2026-01-01T09:00:00+00:00"  # normalised to UTC


def test_json_rows_are_parsed() -> None:
    content = json.dumps(
        [
            {
                "first_name": "Stas",
                "last_name": "Yurich",
                "skill_name": "Vim",
                "skill_difficulty": 7,
                "occurred_at": "2026-01-01T09:00:00Z",
                "believability": 9,
                "description": "Exited Vim",
                "location": "Office",
            }
        ]
    ).encode()

    [row] = parse_rows(content, ImportFormat.JSON)

    assert row.location == "Office"


def test_invalid_row_reports_its_index_and_field() -> None:
    content = (
        f"{HEADER}\n"
        "Stas,Yurich,Vim,7,2026-01-01T09:00:00Z,9,Fine,\n"
        "Stas,Yurich,Vim,7,2026-01-01T09:00:00Z,11,Too believable,\n"
    ).encode()

    with pytest.raises(InvalidInput) as raised:
        parse_rows(content, ImportFormat.CSV)

    assert [e.loc for e in raised.value.errors] == [("rows", 1, "believability")]


@pytest.mark.parametrize(
    ("content", "loc"),
    [
        (b"\xff\xfe not utf-8", ("file",)),
        (f"{HEADER}\nStas,Yurich,Vim,7,2026-01-01T09:00:00Z,9,Desc,Loc,surplus\n".encode(), ("rows", 0)),
    ],
)
def test_malformed_csv_is_rejected(content: bytes, loc: tuple[str | int, ...]) -> None:
    with pytest.raises(InvalidInput) as raised:
        parse_rows(content, ImportFormat.CSV)

    assert raised.value.errors[0].loc == loc
