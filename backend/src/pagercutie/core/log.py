import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from opentelemetry import trace
from opentelemetry._logs import LoggerProvider, SeverityNumber
from opentelemetry.util.types import AttributeValue
from structlog.typing import EventDict, Processor, WrappedLogger

from pagercutie.core.settings import Settings

log = structlog.get_logger("http")


class _StdoutHandler(logging.StreamHandler):
    """Writes to whatever `sys.stdout` is at emit time; it may be swapped after setup (test capture, redirects)."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


# The one handler on the root logger: renders structlog events and plain `logging` records alike.
_handler = _StdoutHandler()


def _add_trace_context(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict


_SEVERITY = {
    "debug": SeverityNumber.DEBUG,
    "info": SeverityNumber.INFO,
    "warning": SeverityNumber.WARN,
    "error": SeverityNumber.ERROR,
    "critical": SeverityNumber.FATAL,
}
# Carried by the record itself (event name, body, severity, timestamp, span context), not as attributes.
_NOT_ATTRIBUTES = {"event", "message", "level", "timestamp", "exc_info", "trace_id", "span_id"}


def _attribute(value: object) -> AttributeValue:
    if isinstance(value, str | bool | int | float):
        return value
    return str(value)  # UUIDs, datetimes, enums...


def _exception(exc_info: object) -> BaseException | None:
    # structlog: `log.exception(...)` sets True or passes the exception; stdlib records carry an exc_info tuple.
    if exc_info is True:
        return sys.exception()
    if isinstance(exc_info, tuple) and len(exc_info) == 3:
        exc_info = exc_info[1]
    return exc_info if isinstance(exc_info, BaseException) else None


def _stdlib_to_convention(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Shape plain `logging` records like ours: the logger name is the event, the text is the message."""
    record: logging.LogRecord = event_dict["_record"]
    event_dict["message"] = event_dict["event"]
    event_dict["event"] = record.name  # e.g. uvicorn.error, sqlalchemy.engine
    event_dict.pop("color_message", None)  # uvicorn's ANSI copy of the message, passed via `extra`
    return event_dict


def otel_events(logger_provider: LoggerProvider) -> Processor:
    """Emit every structlog call as an OTel event: `alerts.acknowledged` becomes `event.name`, `message=` the body."""
    otel_logger = logger_provider.get_logger("pagercutie")

    def processor(_: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        level = event_dict.get("level", method_name)
        event_name = str(event_dict.get("event", ""))
        otel_logger.emit(
            timestamp=time.time_ns(),
            severity_number=_SEVERITY.get(level, SeverityNumber.INFO),
            severity_text=level.upper(),
            body=str(event_dict.get("message", event_name)),
            attributes={
                # Duplicates event_name: Loki's OTLP ingestion keeps attributes but drops the top-level field.
                "event.name": event_name,
                **{
                    key: _attribute(value)
                    for key, value in event_dict.items()
                    if key not in _NOT_ATTRIBUTES and value is not None
                },
            },
            event_name=event_name,
            exception=_exception(event_dict.get("exc_info")),
        )
        return event_dict

    return processor


def configure_logging(settings: Settings, logger_provider: LoggerProvider | None = None) -> None:
    """structlog -> stdlib `logging` -> one root handler that renders (and exports) every record the same way."""
    level = logging.getLevelNamesMapping()[settings.log_level.upper()]
    renderer = structlog.processors.JSONRenderer(default=str) if settings.log_json else structlog.dev.ConsoleRenderer()
    export = [otel_events(logger_provider)] if logger_provider else []
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_trace_context,
    ]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    _handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            # Only for records from plain `logging` (uvicorn, SQLAlchemy, libraries); `extra={...}` becomes fields.
            foreign_pre_chain=[structlog.stdlib.ExtraAdder(), _stdlib_to_convention, *shared],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                *export,  # before format_exc_info, while exc_info is still the exception
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    if _handler not in root.handlers:
        root.addHandler(_handler)

    # uvicorn configures its loggers before importing the app: drop its handlers so records reach ours,
    # and silence its access log, which `http.request` below replaces (with request id and duration).
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True


async def request_logging_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    response = await call_next(request)
    log.info(
        "http.request",
        message="Request handled",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    response.headers["x-request-id"] = request_id
    return response
