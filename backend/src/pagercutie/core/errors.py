import uuid
from dataclasses import dataclass
from http import HTTPStatus


class DomainError(Exception):
    pass


class NotFound(DomainError):
    def __init__(self, entity: str, entity_id: uuid.UUID) -> None:
        super().__init__(f"{entity} {entity_id} not found")


class UserEmailNotFound(NotFound):
    """No user has this email; login looks users up by email, not id."""

    def __init__(self, email: str) -> None:
        DomainError.__init__(self, f"User with email {email} not found")


class SourceSlugNotFound(NotFound):
    """Ingest found no enabled source with an ingest token under this slug for the adapter's type."""

    def __init__(self, slug: str) -> None:
        DomainError.__init__(self, f"Source {slug} not found")


class Conflict(DomainError):
    pass


class Unauthenticated(DomainError):
    def __init__(self) -> None:
        super().__init__("Not logged in")


class Forbidden(DomainError):
    pass


class NotReady(DomainError):
    """The replica cannot serve the request until a cache loads, e.g. ingest without a source catalog."""


class NotImplementedYet(DomainError):
    """Contract-first stub: the route exists in the OpenAPI contract, its service does not yet."""

    def __init__(self, feature: str) -> None:
        super().__init__(f"{feature} is not implemented yet")


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
        case Unauthenticated():
            return HTTPStatus.UNAUTHORIZED, str(exc)
        case Forbidden():
            return HTTPStatus.FORBIDDEN, str(exc)
        case NotImplementedYet():
            return HTTPStatus.NOT_IMPLEMENTED, str(exc)
        case NotReady():
            return HTTPStatus.SERVICE_UNAVAILABLE, str(exc)
        case InvalidInput(errors=errors):
            return HTTPStatus.UNPROCESSABLE_CONTENT, [
                {"loc": ["body", *e.loc], "msg": e.msg, "type": "value_error"} for e in errors
            ]
    raise TypeError(f"Unhandled domain error {type(exc).__name__}")
