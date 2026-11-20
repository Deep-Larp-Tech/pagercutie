"""Pure, synchronous file parsing. Runs in a worker thread (asyncio.to_thread) since files can be large."""

import csv
import io

from pydantic import TypeAdapter, ValidationError

from pagercutie.core.errors import FieldError, InvalidInput
from pagercutie.imports.schemas import ImportFormat, LarpEventImportRow

_ROWS = TypeAdapter(list[LarpEventImportRow])


def parse_rows(content: bytes, fmt: ImportFormat) -> list[LarpEventImportRow]:
    match fmt:
        case ImportFormat.JSON:
            try:
                return _ROWS.validate_json(content)
            except ValidationError as e:
                raise InvalidInput([FieldError(("rows", *err["loc"]), err["msg"]) for err in e.errors()]) from e
        case ImportFormat.CSV:
            return _validate_csv_rows(_read_csv(content))


def _validate_csv_rows(raw_rows: list[dict[str, str]]) -> list[LarpEventImportRow]:
    # String mode: CSV cells are always text, so "7" is a valid strict int here (but JSON `"7"` is not).
    rows: list[LarpEventImportRow] = []
    errors: list[FieldError] = []
    for index, raw in enumerate(raw_rows):
        try:
            rows.append(LarpEventImportRow.model_validate_strings(raw))
        except ValidationError as e:
            errors.extend(FieldError(("rows", index, *err["loc"]), err["msg"]) for err in e.errors())
    if errors:
        raise InvalidInput(errors)
    return rows


def _read_csv(content: bytes) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise InvalidInput([FieldError(("file",), "must be UTF-8 encoded")]) from e

    rows: list[dict[str, str]] = []
    try:
        for index, row in enumerate(csv.DictReader(io.StringIO(text, newline=""))):
            if None in row:  # DictReader collects surplus values under the None key
                raise InvalidInput([FieldError(("rows", index), "has more values than the header")])
            # Short rows leave None for missing cells; dropping them reports "Field required" instead.
            rows.append({key: value for key, value in row.items() if value is not None})
    except csv.Error as e:
        raise InvalidInput([FieldError(("file",), f"is not valid CSV: {e}")]) from e
    return rows
