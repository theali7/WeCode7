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

The repository includes a separate Collector/Prometheus/Loki/Tempo/Grafana stack.
It uses Docker volumes and seven-day retention for stored telemetry. This is a
single-host educational setup, without high availability or off-host backups.
Persistent hosting, alerting and the AI on-call worker remain pending.

## Start the local observability stack

Set GRAFANA_ADMIN_PASSWORD to a unique password through your shell or an untracked
environment file, then run:

```sh
docker compose -f observability/compose.yaml up -d
```

Start an application environment with both Compose files:

```sh
docker compose --env-file /secure/wecode-dev.env -p wecode-dev -f deploy/compose.yaml -f deploy/telemetry.compose.yaml up -d --wait
```

Repeat with the production env file/project name. The override connects only the
web containers to the shared monitoring network; databases retain separate app
networks. For SSH deployments, set OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
in each server env file. The release script detects this endpoint and adds the
network override automatically. Start the observability project on that server
before enabling it. Other receiver URLs continue using the base deployment.

Open http://localhost:3000/d/wecode-overview and sign in as admin with your configured
password. Select the environment and version filters. Tempo is provisioned as a
datasource in Explore. Dashboard rates need several scrapes and enough requests;
unrecorded business events can appear as no data instead of a fabricated zero.

Prometheus (:9090), Loki (:3100), Tempo (:3200), the OTLP receiver (:4318), and Grafana
(:3000) bind only to 127.0.0.1. Use an SSH tunnel for remote access. Backend service
authentication is disabled on the private monitoring network; do not expose those
ports publicly. Grafana anonymous login is disabled.

Stop with docker compose -f observability/compose.yaml down to preserve volumes.
The -v option deletes stored telemetry; use it only for disposable CI data.

## End-to-end evidence

The Observability end-to-end workflow starts this real stack and two disposable
WeCode environments. It performs registration, login and progress writes, then
polls Prometheus counters, Loki logs and Tempo trace lookup for both environments.
It checks the provisioned Grafana dashboard and datasources, fetches metrics
through Grafana's proxy and validates every dashboard PromQL expression.
Its artifact records only trace IDs and verification results, never credentials.

Configuration references:
- https://opentelemetry.io/docs/collector/configuration/
- https://grafana.com/docs/loki/latest/send-data/otel/
- https://grafana.com/docs/tempo/latest/configuration/

