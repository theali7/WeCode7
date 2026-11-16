# Development and production deployment foundation

This file introduces isolated Compose deployments. It does not provision servers,
configure HTTPS, activate OpenTelemetry, or implement automatic deployment.

## Configuration

Keep deployment environment files outside the repository. Create separate files
for development and production containing the following keys:

```dotenv
APP_ENV=development
APP_PORT=8081
APP_VERSION=COMMIT_SHA
WECODE_IMAGE=ghcr.io/theali7/wecode7@sha256:IMAGE_DIGEST
PUBLIC_ORIGIN=https://dev.example.com
POSTGRES_PASSWORD=REPLACE_WITH_UNIQUE_URL_SAFE_RANDOM_PASSWORD
AUTH_SECRET=REPLACE_WITH_UNIQUE_RANDOM_SECRET_AT_LEAST_32_CHARACTERS
```

For production use APP_ENV=production, APP_PORT=8082, its own HTTPS origin, and
independently generated database password and authentication secret.
Use URL-safe database passwords because DATABASE_URL embeds the password.
Replace all placeholders before starting containers.

## Validate and start

```sh
docker compose --env-file /secure/wecode-dev.env -p wecode-dev -f deploy/compose.yaml config --quiet
docker compose --env-file /secure/wecode-dev.env -p wecode-dev -f deploy/compose.yaml up -d --wait
docker compose --env-file /secure/wecode-prod.env -p wecode-prod -f deploy/compose.yaml config --quiet
docker compose --env-file /secure/wecode-prod.env -p wecode-prod -f deploy/compose.yaml up -d --wait
```

The project names create separate networks and PostgreSQL volumes. Never reuse
the same project name for both environments. No database port is published.
The web ports bind to localhost; configure an authenticated operator workflow
and an HTTPS reverse proxy before exposing an environment externally.

## Manual promotion

Build and publish an image once, deploy it to development, and test it there.
Copy its exact WECODE_IMAGE digest and APP_VERSION to the production environment
file, then run the production up command above. Do not copy database contents
or credentials between environments. A later CI/CD workflow must automate this
same promotion after a manual trigger.

## Verification and current limits

Check each environment's /api/health through its own origin. Register a
disposable development account and confirm it cannot authenticate in production.
Never use real account credentials in this check.

The OTEL variables only supply resource metadata for subsequent instrumentation:
they do not collect or export telemetry yet. Existing Render configuration and
the local root compose.yaml are unchanged. Server provisioning, registry
publishing, manual GitHub Actions promotion, telemetry, dashboards, alerts, and
an AI responder are still pending. Existing tests must pass before deployment.

## Automated isolation verification

The Development and production isolation workflow builds one image and starts two
disposable Compose projects on GitHub Actions. It checks database health, separate
networks and volumes, successful authentication in each account's own environment,
and rejection of cross-environment credentials and tokens in both directions.
It removes its disposable volumes afterward. This verifies the deployment pattern;
it does not provision persistent public development or production servers.
