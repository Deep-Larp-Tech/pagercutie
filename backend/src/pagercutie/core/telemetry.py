from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

from pagercutie.core.settings import Settings


@dataclass(frozen=True)
class Telemetry:
    tracer_provider: TracerProvider
    logger_provider: LoggerProvider

    def instrument(self, app: FastAPI, engine: AsyncEngine) -> None:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=self.tracer_provider)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=self.tracer_provider)

    def shutdown(self) -> None:
        # Blocking: flushes the batch queues over HTTP.
        self.logger_provider.shutdown()
        self.tracer_provider.shutdown()


def configure_telemetry(settings: Settings) -> Telemetry | None:
    if not settings.otel_enabled:
        return None

    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    endpoint = str(settings.otel_endpoint).rstrip("/")

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs")))
    set_logger_provider(logger_provider)

    return Telemetry(tracer_provider=tracer_provider, logger_provider=logger_provider)
