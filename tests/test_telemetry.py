"""Exercise all three real OTLP/HTTP exporters with a local protobuf receiver."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from backend.telemetry import Telemetry, TelemetryMiddleware

class TelemetryTests(unittest.TestCase):
    def test_disabled_without_endpoint(self):
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "", "OTEL_SDK_DISABLED": ""}):
            self.assertIsNone(Telemetry.from_environment())

    def test_otlp_signals_and_private_data_boundary(self):
        received = []
        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                data = self.rfile.read(int(self.headers["Content-Length"]))
                received.append((self.path, data))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", "0")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        telemetry = None
        try:
            with patch.dict(os.environ, {
                "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
                "OTEL_EXPORTER_OTLP_HEADERS": "", "OTEL_SDK_DISABLED": "",
                "APP_ENV": "development", "APP_VERSION": "test-version",
                "OTEL_SERVICE_NAME": "wecode-api",
            }):
                telemetry = Telemetry.from_environment()
            app = FastAPI()
            app.state.telemetry = telemetry
            app.add_middleware(TelemetryMiddleware)
            @app.post("/api/auth/v1/signup")
            def signup(body: dict):
                return {"ok": True}
            @app.post("/api/rest/v1/{table}")
            def progress(table: str):
                return JSONResponse({}, status_code=201)
            @app.get("/api/health")
            def failure():
                raise RuntimeError("private-exception-secret")
            trace_id = "1234567890abcdef1234567890abcdef"
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/api/auth/v1/signup?private-query-secret",
                    json={"email": "private-email@example.test", "password": "private-password-secret"},
                    headers={"Authorization": "Bearer private-token-secret",
                             "traceparent": "00-" + trace_id + "-1234567890abcdef-01"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(client.post("/api/rest/v1/learning_way_progress").status_code, 201)
                self.assertEqual(client.get("/api/health").status_code, 500)
                for value in ("private-route-secret-a", "private-route-secret-b"):
                    self.assertEqual(client.get("/" + value).status_code, 404)
            telemetry.traces.force_flush()
            telemetry.metrics.force_flush()
            telemetry.logs.force_flush()
            messages = {}
            classes = {"/v1/traces": ExportTraceServiceRequest,
                       "/v1/metrics": ExportMetricsServiceRequest,
                       "/v1/logs": ExportLogsServiceRequest}
            for path, body in received:
                message = classes[path]()
                message.ParseFromString(body)
                messages.setdefault(path, []).append(message)
            self.assertEqual(set(messages), set(classes))
            spans = [span for message in messages["/v1/traces"]
                     for resource in message.resource_spans for scope in resource.scope_spans for span in scope.spans]
            self.assertEqual(len(spans), 5)
            registration = next(span for span in spans if span.name == "POST /api/auth/v1/signup")
            self.assertEqual(registration.trace_id.hex(), trace_id)
            self.assertEqual(registration.parent_span_id.hex(), "1234567890abcdef")
            unknown = [span for span in spans if span.name == "GET other"]
            self.assertEqual(len(unknown), 2)
            failed = next(span for span in spans if span.name == "GET /api/health")
            self.assertEqual(failed.status.code, 2)
            records = [record for message in messages["/v1/logs"]
                       for resource in message.resource_logs for scope in resource.scope_logs for record in scope.log_records]
            self.assertEqual(len(records), 5)
            self.assertTrue(any(record.trace_id == registration.trace_id and record.span_id == registration.span_id for record in records))
            metrics = [metric for message in messages["/v1/metrics"]
                       for resource in message.resource_metrics for scope in resource.scope_metrics for metric in scope.metrics]
            counters = {metric.name: metric for metric in metrics}
            self.assertEqual(counters["wecode.registrations"].sum.data_points[0].as_int, 1)
            self.assertEqual(counters["wecode.progress.writes"].sum.data_points[0].as_int, 1)
            self.assertEqual(counters["wecode.http.errors"].sum.data_points[0].as_int, 1)
            self.assertIn("wecode.http.duration", counters)
            dumped = json.dumps([MessageToDict(message) for group in messages.values() for message in group])
            for secret in ("private-query-secret", "private-email", "private-password-secret",
                           "private-token-secret", "private-exception-secret", "private-route-secret"):
                self.assertNotIn(secret, dumped)
            self.assertIn("development", dumped)
            self.assertIn("test-version", dumped)
        finally:
            if telemetry:
                telemetry.close()
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

if __name__ == "__main__":
    unittest.main()
