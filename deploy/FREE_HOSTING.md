# Free hosting path: Render + Neon + Grafana Cloud

## Budget and current status

Only Free plans are authorized. The Render deployment adapter checks the existing
service plan and refuses any value other than free; it never creates services or
changes billing. This does not replace checking each provider's account/usage
limits. No paid plans, trials requiring payment, or extra paid resources should be
enabled.

Live setup verified on 2026-11-16: wecode7-dev and wecode7-prod are running as
Free Render image services with independent Free Neon databases. Both health
endpoints returned status=ok/database=postgresql and their release endpoints
reported version 831cc9cc2137c0a5edac5a30dfb48a01fecfa77e with their respective
development/production environment. This initial provisioning was performed in
the provider dashboards; it is not evidence of a completed CI promotion.

Cloud dashboard, logs, traces and an authentication alert lifecycle were verified.
See ../observability/cloud/README.md for the live links and reproducible queries.
Render CI credentials, real AI invocation and a full manual CI promotion remain
unfinished. No merge to main is implied.

The existing wecode-assignment2 Render service and its database stay separate from
new services wecode7-dev and wecode7-prod. The adapter refuses other service names.

## Why the original SSH deployment is optional

Render Free has no SSH shell or persistent disk and only one active Free Postgres
database per workspace. Therefore the default release provider is now render;
set the GitHub environment variable DEPLOY_TARGET=ssh only for a separately
configured Docker host. The Compose-based CI demo remains available.

Use two independent Free Neon projects/databases for the new environments.
This does not modify existing Supabase projects or copy existing accounts.
Neon's Free project compute/storage limits still apply, including scale-to-zero.

For telemetry use Grafana Cloud Free rather than five always-running Render
services. Existing OpenTelemetry exporters can send all three signals directly
to the Cloud OTLP/HTTP endpoint. Do not publish the credentials in frontend code.

## Setup order

1. Sign in to/create Free Neon and Grafana Cloud accounts. Account owners must
   accept any terms and confirm their actual Free tier. Do not add a payment method.
2. Create dedicated dev/prod PostgreSQL projects in Neon, in a region near Frankfurt.
   Keep each TLS connection string private and use it only for its own Render service.
3. Publish the application image in GHCR with APP_VERSION set to its full commit SHA.
   Render needs registry read access. A public image may be used if its source is
   already public and the Docker build context contains no secrets.
4. Create two Free Render Web Services from Existing Image (not Git source).
   Names must be wecode7-dev and wecode7-prod. Use the same GHCR image repository,
   linux/amd64, Frankfurt, port 8080 and health path /api/health.
5. On each service set DATABASE_URL, a separately generated AUTH_SECRET, and APP_ENV
   (development or production). PUBLIC_ORIGIN may be omitted: Render supplies its
   HTTPS origin through RENDER_EXTERNAL_URL. Do not manually pin APP_VERSION: the
   release identity and telemetry default to BUILD_VERSION baked into the image.
6. In each GitHub environment (development and production) set RENDER_SERVICE_ID
   as a variable and RENDER_API_KEY as a secret. Use a scoped deploy credential
   if available. Creating credentials or granting new access requires the owner
   to authorize that specific access; secrets should never be posted in chat.
7. Merge reviewed code when both services and credentials are ready. After all
   checks pass, development deployment builds/publishes once and sends imageUrl
   with the immutable digest to Render. It waits for live, compares the resolved
   digest and checks /api/health plus /api/release. Production promotion is manual
   and consumes the development manifest without rebuilding.

## Configure cloud telemetry

Use the Grafana Cloud OpenTelemetry connection instructions to obtain the OTLP
base endpoint and authentication headers for its Free stack. On both Render
services set OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_EXPORTER_OTLP_HEADERS privately.
Use HTTPS. APP_ENV and the baked version identify the environment/release.

Import observability/cloud/wecode.json with the Cloud Prometheus and Loki
datasources; use the Traces Drilldown link for Tempo. Cloud metric translation can add _total counter and _seconds histogram
suffixes; inspect actual ingested names and resource labels before adapting queries.
The tested local dashboard uses a Collector configured without these suffixes.
Do not claim Cloud dashboard or alert verification until real requests are visible.

Configure Cloud alert rules using the same threshold/window/hold behavior as
observability/alerts.yaml, with metric names adjusted to actual Cloud data.
The existing on-call worker is currently configured for a local Prometheus/Loki
API. Authenticated Cloud APIs and/or Grafana's Free AI investigation capabilities
need account-specific configuration and a live test; no paid API calls are made
or implied by this guide.

## Free-plan operating limits

Render Free services sleep on inactivity, share a workspace's free-hour allowance
and do not persist local files. Two services are for a coursework demo, not an
always-on production SLA. Avoid keepalive traffic intended only to prevent sleep.
Do not move production data to ephemeral storage or share a dev/prod database.

Free Grafana Cloud has usage/retention limits. Free Neon has per-project compute
and storage quotas. Use separate Free plans without a payment method and monitor
usage in the provider dashboards. The actual AI responder must use an already
authorized subscription/free allowance or a local model; no paid API key is required
by this hosting adapter, and no real AI run has yet been demonstrated.

References (checked 2026-11-16):
- https://render.com/docs/free
- https://render.com/docs/deploying-an-image
- https://api-docs.render.com/reference/create-deploy
- https://neon.com/docs/introduction/plans
- https://grafana.com/products/cloud/free-tier/
- https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/
