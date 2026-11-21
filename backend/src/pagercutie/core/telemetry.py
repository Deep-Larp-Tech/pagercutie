from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

from pagercutie.core.settings import Settings

# Grafana's $__rate_interval assumes a 15 s scrape, so rate() needs a sample at least that often (SPEC §13).
METRIC_EXPORT_INTERVAL_MS = 10_000


@dataclass(frozen=True)
class Telemetry:
    tracer_provider: TracerProvider
    logger_provider: LoggerProvider
    meter_provider: MeterProvider

    def instrument(self, app: FastAPI, engine: AsyncEngine) -> None:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
            # The per-message `http receive` / `http send` spans cost CPU on every request and add nothing (ADR-0100).
            exclude_spans=["receive", "send"],
        )
        # 0.66b2 declares sqlalchemy < 2.1 and instruments nothing on 2.1; upstream main already allows < 2.2.
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
            skip_dep_check=True,
        )

    def shutdown(self) -> None:
        # Blocking: flushes the batch queues over HTTP.
        self.logger_provider.shutdown()
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


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

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"), export_interval_millis=METRIC_EXPORT_INTERVAL_MS
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    return Telemetry(tracer_provider=tracer_provider, logger_provider=logger_provider, meter_provider=meter_provider)
