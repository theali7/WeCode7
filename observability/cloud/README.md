# Cloud observability deployment

Verified in the authenticated Grafana UI on 2026-11-16. This records a live coursework
demonstration; it does not claim unattended AI response or CI promotion is complete.

## Live resources

- Development: https://wecode7-dev.onrender.com
- Production: https://wecode7-prod.onrender.com
- Dashboard: https://jadegrape2021.grafana.net/d/wecode-cloud-overview
- Authentication alert and history: https://jadegrape2021.grafana.net/alerting/grafana/ag4h4ulp94hs0a/view?tab=history
- Readiness alert: https://jadegrape2021.grafana.net/alerting/grafana/eg4h4zsttacqoa/view
- Traces: https://jadegrape2021.grafana.net/a/grafana-exploretraces-app/

Both Render services use Free compute and separate Free Neon PostgreSQL projects.
The initial immutable image digest is
`sha256:e24e5e1790ba71d9cbe42089c72ebd3d29ca8943c1aa50dfaa0382235ef56abb`,
with baked version `831cc9cc2137c0a5edac5a30dfb48a01fecfa77e`.
The original Render service was not changed.

## Dashboard import

Import `wecode.json` through Dashboards > New > Import > JSON. Select the stack's
Prometheus source for DS_PROMETHEUS and application Loki source for DS_LOKI.
On the verified stack these are grafanacloud-jadegrape2021-prom and
grafanacloud-jadegrape2021-logs.

The seven panels cover request rate, HTTP 5xx, p95 latency, registrations,
progress writes, authentication attempts and correlated request logs.
Environment and version variables filter the actual resource labels.
Development and production series were visible separately. Rejected
authentication attempts and request logs were observed after the controlled test.

Cloud translation adds `_total` to counters and `_seconds_bucket` to the duration
histogram. The local Collector dashboard has different names: do not overwrite
that dashboard with this cloud variant. Business counters appear only after a
matching action; missing data does not demonstrate zero events. Registration
and progress-write panels have not yet been verified with live successful events.

## Grafana-managed alert rules

Folder: WeCode. Evaluation group: wecode-cloud. Interval: 1m.
For both rules use instant Prometheus query A, threshold C: A IS ABOVE 2,
pending period 1m, keep firing 0s, labels `project=wecode`.
No-data state is Normal, query-error state is Error.
This avoids treating the absence of an event counter as a confirmed failure.
Separate availability monitoring is required for absent telemetry or sleeping apps.

### WeCodeAuthenticationRejections

```promql
sum by (service_name, deployment_environment_name, service_version) (
  increase(wecode_auth_attempts_total{service_name="wecode-api",outcome="rejected"}[5m])
)
```

Summary: Repeated rejected sign-in attempts.
Investigate authentication trends, deployment changes and request traces.
The signal does not by itself establish malicious activity.

Controlled rejected sign-ins to a nonexistent test account on development
produced actual exported counters, logs and traces. Grafana state history showed
Normal -> Pending -> Alerting -> Normal. Production was not fault-injected.
A five-minute window and Prometheus extrapolation mean the increase can be fractional;
the first counter observation is not itself a measured increase.

### WeCodeReadinessFailures

```promql
sum by (service_name, deployment_environment_name, service_version) (
  increase(wecode_http_requests_total{service_name="wecode-api",http_route="/api/health",http_response_status_code="503"}[5m])
)
```

Summary: Application database readiness is repeatedly failing.
Check PostgreSQL connectivity and startup migrations. The saved rule was verified
as Normal with the corrected query. Its Cloud firing path was not fault-injected;
the disposable Compose CI tests cover the readiness failure scenario.

## Telemetry access and unfinished integration

The existing OTLP exporters send metrics, traces and logs using a 30-day write-only
stack token stored in private Render environment variables. It has only
metrics:write, logs:write and traces:write. Credentials are not in this repository.

The default notification policy currently routes to an empty contact point.
State evaluation and history work, but external notification delivery is not
configured. The current worker in on_call/worker.py reads local Prometheus/Loki,
not authenticated Grafana Cloud APIs. A real cloud responder still needs a
read-only integration and an authenticated AI runtime; neither was fabricated.
The worker's deterministic test subprocess is not a real AI invocation.

The dev/prod services were initially provisioned from the same image manually.
The prepared CI promotion workflows still require private Render deployment
credentials in GitHub environments and an actual end-to-end promotion test.
