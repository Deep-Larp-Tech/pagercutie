import logging
import uuid
from collections.abc import Iterator

import pytest
import structlog
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider, ReadableLogRecord
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from structlog.typing import Processor

from pagercutie.core.log import configure_logging, otel_events
from pagercutie.core.settings import Settings


@pytest.fixture
def exporter() -> InMemoryLogRecordExporter:
    return InMemoryLogRecordExporter()


@pytest.fixture
def processor(exporter: InMemoryLogRecordExporter) -> Processor:
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    return otel_events(provider)


def exported(exporter: InMemoryLogRecordExporter) -> ReadableLogRecord:
    [record] = exporter.get_finished_logs()
    return record


def test_structlog_call_becomes_an_otel_event(processor: Processor, exporter: InMemoryLogRecordExporter) -> None:
    person_id = uuid.uuid7()
    event_dict = {
        "event": "persons.created",
        "message": "Person created",
        "level": "info",
        "person_id": person_id,
        "request_id": "abc",
        "timestamp": "2026-01-01T00:00:00Z",
    }

    returned = processor(None, "info", event_dict)

    record = exported(exporter).log_record
    assert returned is event_dict  # stdout rendering still gets the untouched event
    assert record.event_name == "persons.created"
    assert record.body == "Person created"
    assert (record.severity_number, record.severity_text) == (SeverityNumber.INFO, "INFO")
    assert dict(record.attributes or {}) == {
        "event.name": "persons.created",
        "person_id": str(person_id),
        "request_id": "abc",
    }


def test_event_is_linked_to_the_current_span(processor: Processor, exporter: InMemoryLogRecordExporter) -> None:
    with TracerProvider().get_tracer("test").start_as_current_span("request") as span:
        processor(None, "info", {"event": "http.request", "level": "info"})

    record = exported(exporter).log_record
    assert (record.trace_id, record.span_id) == (span.get_span_context().trace_id, span.get_span_context().span_id)


def test_logged_exception_is_attached(processor: Processor, exporter: InMemoryLogRecordExporter) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        processor(None, "error", {"event": "imports.failed", "level": "error", "exc_info": True})

    record = exported(exporter).log_record
    assert record.severity_number == SeverityNumber.ERROR
    assert (record.attributes or {})["exception.type"] == "ValueError"
    assert "exc_info" not in (record.attributes or {})


@pytest.fixture
def configured(exporter: InMemoryLogRecordExporter) -> Iterator[None]:
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    configure_logging(Settings(log_json=True), provider)
    yield
    configure_logging(Settings())


def test_stdlib_logging_takes_the_same_path(
    exporter: InMemoryLogRecordExporter, capsys: pytest.CaptureFixture[str], configured: None
) -> None:
    logging.getLogger("sqlalchemy.pool").warning("Pool %s exhausted", "main", extra={"size": 5})
    structlog.get_logger("persons").info("persons.created", message="Person created")

    [stdlib, ours] = [r.log_record for r in exporter.get_finished_logs()]
    assert (stdlib.event_name, stdlib.body, stdlib.severity_text) == (
        "sqlalchemy.pool",
        "Pool main exhausted",
        "WARNING",
    )
    assert (stdlib.attributes or {})["size"] == 5
    assert ours.event_name == "persons.created"
    # Both rendered by the same root handler, in the same format.
    [stdlib_line, our_line] = capsys.readouterr().out.splitlines()
    assert '"event": "sqlalchemy.pool"' in stdlib_line
    assert '"event": "persons.created"' in our_line


@pytest.mark.usefixtures("configured")
def test_uvicorn_access_log_is_silenced_and_its_handlers_removed(exporter: InMemoryLogRecordExporter) -> None:
    logging.getLogger("uvicorn.access").info("GET /health 200")
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    assert [r.log_record.event_name for r in exporter.get_finished_logs()] == ["uvicorn.error"]
    assert logging.getLogger("uvicorn").handlers == []
