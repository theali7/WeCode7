# Application telemetry

## Enable OTLP/HTTP

Set OTEL_EXPORTER_OTLP_ENDPOINT to an accessible collector base URL, such as
http://collector:4318 on a private Docker network. The application exports to
/v1/traces, /v1/metrics and /v1/logs. Set OTEL_EXPORTER_OTLP_HEADERS if the receiver
requires authentication. Use HTTPS when telemetry crosses an untrusted network.

Set APP_ENV, APP_VERSION and optionally OTEL_SERVICE_NAME (default wecode-api).
Those resource attributes are attached to all signals. With no endpoint, or with
OTEL_SDK_DISABLED=true, telemetry is disabled. Existing deployments can keep running
without a collector. Metrics are exported every five seconds; logs and spans are
batched. Providers shut down with the application.

The deployment Compose file forwards these settings from its environment file.
A remote receiver must be reachable from inside the application container; localhost
inside that container is not the deployment host.

## Signals and metric meanings

| Instrument | Meaning |
| --- | --- |
| wecode.http.requests | HTTP responses, labeled by method, normalized route and status |
| wecode.http.duration | Full ASGI request duration in seconds, including response sending |
| wecode.http.errors | Requests ending in HTTP 5xx or unhandled exceptions |
| wecode.registrations | Signup requests that returned HTTP 200 |
| wecode.auth.attempts | Token endpoint calls, split into success, rejected and error |
| wecode.progress.writes | Progress-write requests, labeled by table and outcome; counts requests, not rows or distinct completed lessons |

Traces contain server spans and accept W3C traceparent for parent correlation.
Request completion logs carry the same trace and span IDs. Unhandled exception
messages are omitted; status is marked as an error. This instrumentation does not
yet create child spans for database queries or browser actions.

## Data boundary

The dedicated request logger exports method, fixed route template and status.
It never exports request bodies, query strings, authorization headers, email,
account IDs, IP addresses, raw unknown paths or exception messages.
Static and unmatched paths share the bounded other label. Resource attributes are
operator configuration; do not place secrets in OTEL_RESOURCE_ATTRIBUTES.

Existing server stdout/access logs are separate from this dedicated OTLP logger.

## Verification and remaining work

tests/test_telemetry.py starts a local HTTP receiver, decodes actual OTLP Protobuf
payloads for all three signals, checks metric counts, trace parenting and log
correlation, and verifies that test credentials and exception text are absent.
It uses disposable requests and no external telemetry provider or real database.

This stage instruments and exports application telemetry. Persistent storage,
collector deployment, dashboards, alerting and the AI on-call worker remain to be
implemented. An endpoint configured without a reachable receiver cannot provide
stored telemetry.
