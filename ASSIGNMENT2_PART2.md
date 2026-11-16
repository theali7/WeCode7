# Assignment 2 Part II — implementation and demonstration checklist

## Requirements and evidence

| Requirement | Implementation | Verification boundary |
| --- | --- | --- |
| Independent dev/prod | deploy/compose.yaml | CI starts two isolated databases and checks account/token boundaries; persistent public environments are not provisioned |
| Manual production promotion | .github/workflows/deploy-dev.yml and promote-prod.yml | Same image digest is passed from the successful dev release manifest; live SSH deployment is not verified |
| OpenTelemetry signals | backend/telemetry.py | Real OTLP Protobuf receiver tests cover metrics, traces, correlated logs and data exclusion |
| App metrics and dashboard | observability/ | CI verifies both environments in Prometheus, Loki, Tempo and provisioned Grafana |
| Alert on metric changes | observability/alerts.yaml | promtool scenarios and a controlled disposable-database outage |
| AI on-call responder | on_call/worker.py | Worker invocation/retry/deduplication is tested with a labeled fixture; actual AI requires authenticated Codex CLI |

The existing Render website is independent of this branch's unmerged deployment
changes. No new public development, production or Grafana URLs are claimed.

## Files for review

- Deployment configuration and prerequisites: deploy/README.md
- OTLP signals, storage stack and dashboard: observability/README.md
- Alert thresholds, responder setup and limitations: on_call/README.md
- Automated evidence: Backend and PostgreSQL, Playwright browser tests,
  Development and production isolation, and Observability end-to-end workflows.

## Suggested live demonstration

1. Configure the server and GitHub environments as documented, then merge the
   reviewed changes. Push a small code change to main and show all four checks.
2. Show the automatically deployed dev image digest and its development-release
   artifact. Open Actions, trigger Promote development to production and verify
   the production digest matches without a rebuild.
3. Open Grafana through a localhost/SSH tunnel, select an environment/version,
   register a disposable account and save learning progress.
4. Show the resulting application metrics, request logs and trace in Tempo.
5. Demonstrate a readiness incident only in a disposable environment using the
   CI workflow. Show the pending period, firing alert, labels and runbook.
6. With Codex CLI authenticated on the monitoring host, run the worker and show
   an actual investigation report. Repeat a poll to demonstrate deduplication.
   Explain the difference between an actual model report and the CI fixture.
7. Restore database availability and explain the five-minute alert lookback.
   Preserve normal database/telemetry volumes; delete only disposable CI data.

## Remaining prerequisites before claiming full live completion

- Provision and configure persistent dev/prod and monitoring hosting.
- Configure server environment files, registry access, HTTPS and GitHub SSH secrets.
- Verify an actual automatic dev deployment and manually promoted prod release.
- Install/authenticate the AI CLI and demonstrate a real alert investigation.
- Record evidence from those live operations. Current CI covers disposable services
  and deterministic responder fixtures; it cannot substitute for these operations.

The source article's platform-agnostic deployment principle does not establish
whether the course separately mandates AWS/CloudFormation or another provider.
Use the instructor's full assignment requirements for that hosting decision.
