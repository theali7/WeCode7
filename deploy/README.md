# Development and production

## Current status

The isolated Compose pattern has passed GitHub Actions tests for separate networks,
database volumes, credentials and tokens. These were disposable test environments,
not persistent public deployments.

The deployment workflows in this branch require a configured SSH host. They do not
provision servers or modify the existing Render deployment. OpenTelemetry instrumentation is included. Set an accessible OTLP/HTTP receiver
endpoint to enable export; see ../observability/README.md.

## Server requirements

Use a Linux amd64 server with Docker Engine, Docker Compose v2, Python 3 and an SSH
account allowed to run Docker. Create separate GitHub environments named
development and production. Set these environment secrets for each:

| Secret | Value |
| --- | --- |
| DEPLOY_HOST | Server hostname or IPv4 address |
| DEPLOY_USER | Unix SSH account |
| DEPLOY_SSH_KEY | Dedicated private SSH key |
| DEPLOY_KNOWN_HOSTS | Verified SSH known-hosts entry for that host |

The server needs registry read access to ghcr.io/theali7/wecode7. If the package is
private, configure docker login on the server with a separate read-only registry
credential. The Actions GITHUB_TOKEN publishes the image from the development job.

Create /srv/wecode/config and /srv/wecode/deployments owned by the SSH account.
Store files development.env and production.env under /srv/wecode/config, with mode
0600 and independently generated database and authentication secrets:

```dotenv
PUBLIC_ORIGIN=https://YOUR_ENVIRONMENT_DOMAIN
POSTGRES_PASSWORD=UNIQUE_URL_SAFE_RANDOM_PASSWORD
AUTH_SECRET=UNIQUE_RANDOM_SECRET_AT_LEAST_32_CHARACTERS
```

Use URL-safe passwords: DATABASE_URL embeds the password. Each origin must be a
real HTTPS origin without a path. Configure HTTPS reverse proxies to localhost
port 8081 for development and 8082 for production. Database ports stay private.
Existing accounts and databases are not copied between these environments.

## Automatic development deployment

After merging the workflows into main, pushes trigger the existing backend,
browser, isolation and observability checks. The development workflow reacts when checks finish
and proceeds only when all four checks passed for the current main commit.

It builds and publishes one linux/amd64 image, deploys its immutable digest via SSH,
and verifies container health and /api/health before recording the release.
A development-release artifact records image digest, application commit SHA and
workflow run ID. GitHub runs where the gate did not deploy have no release artifact.

## Manual production promotion

Open Actions, choose Promote development to production, select main, then enter
the run ID of the latest successful Deploy development run with a release artifact.
The workflow verifies that run and deploys exactly its digest to production.
It does not build another image. Production and development releases are serialized
with the same workflow concurrency group.

The workflows must exist on main before workflow_run and workflow_dispatch can
be used. A draft pull request does not activate production deployment.
An optional production environment reviewer can add another release approval.

## Local configuration validation and disposable CI

deploy/compose.yaml can also be invoked manually using separate environment files,
explicit project names wecode-dev and wecode-prod, and WECODE_IMAGE, APP_VERSION,
APP_ENV and APP_PORT values in addition to the secrets above:

```sh
docker compose --env-file /secure/wecode-dev.env -p wecode-dev -f deploy/compose.yaml config --quiet
docker compose --env-file /secure/wecode-dev.env -p wecode-dev -f deploy/compose.yaml up -d --wait
```

Use development/8081 or production/8082 for APP_ENV/APP_PORT. Use an immutable
registry digest for WECODE_IMAGE and the full application commit for APP_VERSION.
Do not reuse Compose project names across environments.

The isolation workflow builds one disposable image, starts two isolated projects,
checks health, networks, volumes and account/token boundaries in both directions,
and removes only its disposable projects afterward. deploy/verify_isolation.py
refuses to run without WECODE_DISPOSABLE_ISOLATION=yes.

## Limits and recovery

A failing deployment fails the workflow and does not create a successful release
manifest. It can leave a failed new container on the server: automatic rollback is
not implemented. The previous successful image/version remains in
/srv/wecode/deployments/ENVIRONMENT/release.json. Restore it manually if needed.
Database migrations run at application startup; image rollback cannot reverse
schema changes. Back up each database before releases with schema changes.

Persistent hosting, server secrets and HTTPS must be configured before live release
verification. Dashboard, alert and on-call worker code is included; a real AI
investigation additionally requires an authenticated Codex CLI. See ../on_call/README.md.
