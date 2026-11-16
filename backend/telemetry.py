"""Bounded, credential-free HTTP telemetry exported over OTLP/HTTP."""
import logging
import os
import time
from urllib.parse import urlsplit

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

ROUTES = {"/healthz", "/api/health", "/api/auth/v1/settings", "/api/auth/v1/signup",
          "/api/auth/v1/token", "/api/auth/v1/user", "/api/auth/v1/logout",
          "/api/auth/v1/recover", "/api/rest/v1/{table}"}
TABLES = {"profiles", "lessons", "lesson_progress", "learning_way_progress"}

class Telemetry:
    def __init__(self, traces, metrics, logs):
        self.traces, self.metrics, self.logs = traces, metrics, logs
        self.tracer = traces.get_tracer("wecode.http")
        self.logger = logging.Logger("wecode.requests", level=logging.INFO)
        self.handler = LoggingHandler(level=logging.INFO, logger_provider=logs)
        self.logger.addHandler(self.handler)
        meter = metrics.get_meter("wecode.application")
        self.requests = meter.create_counter("wecode.http.requests", unit="{request}")
        self.duration = meter.create_histogram("wecode.http.duration", unit="s")
        self.errors = meter.create_counter("wecode.http.errors", unit="{error}")
        self.registrations = meter.create_counter("wecode.registrations", unit="{registration}")
        self.auth = meter.create_counter("wecode.auth.attempts", unit="{attempt}")
        self.progress = meter.create_counter("wecode.progress.writes", unit="{request}")

    @classmethod
    def from_environment(cls):
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
        if not endpoint or os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
            return None
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be an HTTP(S) base URL without credentials")
        resource = Resource.create({
            "service.name": os.environ.get("OTEL_SERVICE_NAME", "wecode-api"),
            "deployment.environment.name": os.environ.get("APP_ENV", "local"),
            "service.version": os.environ.get("APP_VERSION") or os.environ.get("BUILD_VERSION", "unknown"),
        })
        traces = TracerProvider(resource=resource)
        traces.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint + "/v1/traces", timeout=3)))
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint + "/v1/metrics", timeout=3),
            export_interval_millis=5000, export_timeout_millis=4000)
        metrics = MeterProvider(resource=resource, metric_readers=[reader])
        logs = LoggerProvider(resource=resource)
        logs.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint + "/v1/logs", timeout=3)))
        return cls(traces, metrics, logs)

    def close(self):
        self.logger.removeHandler(self.handler)
        for provider in (self.traces, self.metrics, self.logs):
            provider.shutdown()

    def record(self, method, route, status, seconds, table):
        attributes = {"http.request.method": method, "http.route": route, "http.response.status_code": status}
        self.requests.add(1, attributes)
        self.duration.record(seconds, attributes)
        if status >= 500:
            self.errors.add(1, attributes)
        outcome = "success" if status < 400 else "error" if status >= 500 else "rejected"
        if method == "POST" and route == "/api/auth/v1/signup" and status == 200:
            self.registrations.add(1)
        if method == "POST" and route == "/api/auth/v1/token":
            self.auth.add(1, {"outcome": outcome})
        if method == "POST" and route == "/api/rest/v1/{table}" and table in {"lesson_progress", "learning_way_progress"}:
            self.progress.add(1, {"table": table, "outcome": outcome})
        self.logger.log(logging.ERROR if status >= 500 else logging.INFO,
                        "HTTP request completed", extra=attributes)

class TelemetryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        telemetry = getattr(getattr(scope.get("app"), "state", None), "telemetry", None)
        if scope["type"] != "http" or telemetry is None:
            return await self.app(scope, receive, send)
        method = scope.get("method", "OTHER")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            method = "OTHER"
        # Only trace context is read. Never export headers, query strings, bodies,
        # client addresses, account IDs, raw URLs or exception messages.
        headers = {key.decode("latin1"): value.decode("latin1")
                   for key, value in scope.get("headers", []) if key == b"traceparent"}
        parent = TraceContextTextMapPropagator().extract(headers)
        started, status = time.monotonic(), 500
        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        with telemetry.tracer.start_as_current_span(method, context=parent, kind=SpanKind.SERVER,
                record_exception=False, set_status_on_exception=False) as span:
            try:
                await self.app(scope, receive, observed_send)
            except BaseException:
                status = 500
                raise
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                route = route if route in ROUTES else "other"
                table = scope.get("path_params", {}).get("table", "")
                table = table if table in TABLES else "other"
                attributes = {"http.request.method": method, "http.route": route,
                              "http.response.status_code": status}
                span.update_name(method + " " + route)
                span.set_attributes(attributes)
                if status >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                telemetry.record(method, route, status, time.monotonic() - started, table)
