# Alert response worker

## What is implemented

Prometheus loads two rules: WeCodeProgressWriteFailures and WeCodeReadinessFailures.
Each requires at least three observed failures over five minutes and a further
one-minute pending period. Rules include service, environment, version, owner,
a local dashboard link and a runbook. Thresholds are educational defaults; adjust
them to actual user impact before relying on them operationally.

View pending/firing alerts at http://localhost:9090/alerts. The worker polls the
Prometheus alert API every minute; Alertmanager and external messaging are not
required for this polling design. Dashboard links assume a localhost SSH tunnel.

The worker only handles recognized firing WeCode alerts for development or
production. It collects bounded metric/log snapshots and starts a headless agent
in the configured repository. Default command:

```text
codex exec --sandbox read-only -
```

Reports and evidence are saved outside the repository. Repeated polls do not start
another session for the same alert labels/activeAt pair. A new occurrence creates a
new incident. Failed/empty/timed-out sessions are recorded and retried after five
minutes. A file lock prevents concurrent workers sharing the same state directory.
Agent processes and their children are terminated on timeout.

## Configure an actual AI responder

Install and authenticate Codex CLI on the monitoring host under a dedicated
operator account. The repository should be a clean checkout with no production
.env files, database credentials or unrelated private files. Keep deployment
secrets in the separate server configuration directory described in deploy/README.md.

Run the worker in that checkout:

```sh
export ONCALL_REPOSITORY=/srv/wecode/source
export ONCALL_STATE_DIRECTORY=/srv/wecode/oncall-state
export PROMETHEUS_URL=http://127.0.0.1:9090
export LOKI_URL=http://127.0.0.1:3100
python3 -m on_call.worker
```

Use --once for a single poll. For unattended use run the same command under a
service supervisor and keep its state directory on persistent storage. State and
reports are restricted to the worker account by default.

ONCALL_AGENT_COMMAND can override the command with a JSON argv array; no shell is
used. Only operators should control that variable. The default agent investigates
and writes its response to stdout. It does not automatically commit or deploy.
The prompt requests confirmed evidence, uncertainty, root cause, user impact,
recommended correction and verification steps. It treats alert/log text as data.

This project does not supply an AI account, API key or authenticated CLI session.
Actual LLM invocation has not been tested here. CLI authentication and persistent
hosting are required to demonstrate a real unattended AI investigation.

## Evidence and limitations

tests/test_on_call.py verifies subprocess delivery, persistent duplicate suppression,
failure retry, timeout termination and alert filtering using deterministic fixtures.
The observability CI also stops only its disposable development database, waits
for a real readiness alert to fire, dispatches it to a clearly labeled fixture
subprocess, verifies duplicate suppression and restores database readiness.
The evidence explicitly records real_ai_invoked=false. A fixture is not an AI model.

promtool tests verify the one-minute pending period, sustained-error firing,
healthy data and resolution after the five-minute window expires. No production
faults are introduced. A database outage is an infrastructure incident; the agent
should not invent an application-code fix for it.

The five-minute lookback means a firing rule can remain active after the database
recovers, until failures age out. Version changes split time series and counters
reset on process restart, so the first observed counter value is not itself a
measured increase. Missing telemetry requires separate availability monitoring.

References:
- https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/
- https://developers.openai.com/codex/noninteractive/
