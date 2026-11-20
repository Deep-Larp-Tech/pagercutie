import csv
import io
from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from pagercutie.imports.parsing import parse_rows
from pagercutie.imports.schemas import ImportFormat, LarpEventImportRow

text = st.text(alphabet=st.characters(exclude_categories=["Cs"], exclude_characters="\x00"), min_size=1, max_size=100)
rows = st.lists(
    st.builds(
        LarpEventImportRow,
        first_name=text,
        last_name=text,
        skill_name=text,
        skill_difficulty=st.integers(1, 10),
        occurred_at=st.datetimes(datetime(1900, 1, 1), datetime(2100, 1, 1), timezones=st.just(UTC)),
        believability=st.integers(1, 10),
        description=text,
        location=st.none() | text,
    ),
    max_size=5,
)


def to_csv(items: list[LarpEventImportRow]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(LarpEventImportRow.model_fields))
    writer.writeheader()
    writer.writerows(row.model_dump(mode="json") for row in items)  # None -> empty cell
    return buffer.getvalue().encode()


def to_json(items: list[LarpEventImportRow]) -> bytes:
    return b"[" + b",".join(row.model_dump_json().encode() for row in items) + b"]"


@given(items=rows)
def test_csv_and_json_encodings_parse_to_the_same_rows(items: list[LarpEventImportRow]) -> None:
    assert parse_rows(to_csv(items), ImportFormat.CSV) == items
    assert parse_rows(to_json(items), ImportFormat.JSON) == items
