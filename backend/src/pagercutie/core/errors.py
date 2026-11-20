import uuid
from dataclasses import dataclass
from http import HTTPStatus


class DomainError(Exception):
    pass


class NotFound(DomainError):
    def __init__(self, entity: str, entity_id: uuid.UUID) -> None:
        super().__init__(f"{entity} {entity_id} not found")


class Conflict(DomainError):
    pass


@dataclass(frozen=True)
class FieldError:
    loc: tuple[str | int, ...]
    msg: str


class InvalidInput(DomainError):
    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__("; ".join(f"{'.'.join(map(str, e.loc))}: {e.msg}" for e in errors))
        self.errors = errors


type ErrorDetail = str | list[dict[str, object]]


def error_body(exc: DomainError) -> tuple[HTTPStatus, ErrorDetail]:
    """Status and `detail` for a domain error; shared by the HTTP handler and streamed responses."""
    match exc:
        case NotFound():
            return HTTPStatus.NOT_FOUND, str(exc)
        case Conflict():
            return HTTPStatus.CONFLICT, str(exc)
        case InvalidInput(errors=errors):
            return HTTPStatus.UNPROCESSABLE_CONTENT, [
                {"loc": ["body", *e.loc], "msg": e.msg, "type": "value_error"} for e in errors
            ]
    raise TypeError(f"Unhandled domain error {type(exc).__name__}")
