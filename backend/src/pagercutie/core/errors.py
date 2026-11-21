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


class Overloaded(DomainError):
    """The replica has no capacity for the request now: its connection pool or its ingest slots are exhausted.

    Answers 503 with `Retry-After` (SPEC §5.1, ADR-0110, ADR-0111).
    """

    def __init__(self, reason: str, retry_after_s: int) -> None:
        super().__init__(reason)
        self.retry_after_s = retry_after_s


class RateLimited(DomainError):
    """The source sent more events than its token bucket allows; answers 429 with `Retry-After` (ADR-0111)."""

    def __init__(self, source_slug: str, retry_after_s: int) -> None:
        super().__init__(f"Source {source_slug} is over its rate limit")
        self.retry_after_s = retry_after_s


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
        case NotReady() | Overloaded():
            return HTTPStatus.SERVICE_UNAVAILABLE, str(exc)
        case RateLimited():
            return HTTPStatus.TOO_MANY_REQUESTS, str(exc)
        case InvalidInput(errors=errors):
            return HTTPStatus.UNPROCESSABLE_CONTENT, [
                {"loc": ["body", *e.loc], "msg": e.msg, "type": "value_error"} for e in errors
            ]
    raise TypeError(f"Unhandled domain error {type(exc).__name__}")


def retry_after(exc: DomainError) -> int | None:
    """Seconds for the `Retry-After` header of a domain error; None when the error has none."""
    match exc:
        case Overloaded(retry_after_s=seconds) | RateLimited(retry_after_s=seconds):
            return seconds
        case _:
            return None
