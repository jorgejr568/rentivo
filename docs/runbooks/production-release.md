# Production Release Runbook

This runbook governs the Rentivo 5.0 big-bang release and later releases of the
React/Vite, FastAPI, worker, MariaDB, and Nginx stack. The release is atomic:
one immutable source SHA supplies every application image, one Alembic job runs
before application services, and traffic moves to that tested stack once.

There is no legacy-application rollback path. Recovery uses the previous
React/FastAPI stack version, a forward fix, or a verified database restore.

## Ownership and release record

Assign named people before the window. One person may hold more than one role,
but every role needs a primary and a backup.

| Role | Responsibility |
|---|---|
| Release commander | Owns go/abort decisions and the release timeline |
| Database operator | Owns backup, restore rehearsal, migration, and revision checks |
| Runtime operator | Owns images, Compose rollout, health, and rollback |
| Application verifier | Runs smoke tests and checks critical user workflows |
| Incident lead | Owns alerts, communications, and recovery coordination |

Create a release record containing the UTC window, owners, immutable Git SHA,
API/worker/frontend image references and digests, previous production SHA and
digests, expected Alembic revision, backup identifier, restore-rehearsal result,
migration duration, rollout timestamps, smoke result, and final decision.

## Preflight

Complete every item before announcing the maintenance window:

1. Confirm the protected release gate passed for the exact release SHA: backend
   and frontend tests, 100% coverage, lint, OpenAPI freshness, production
   Compose validation, image builds, and the real-stack smoke/E2E suite.
2. Confirm the release SHA is the commit being deployed. Do not rebuild from a
   moving branch or retag an image after the gate.
3. Validate production configuration with secret-managed files:

   ```bash
   make stack-config \
     RENTIVO_DB_ENV_FILE=/etc/rentivo/db.env \
     RENTIVO_APP_ENV_FILE=/etc/rentivo/app.env
   ```

4. Confirm the canonical HTTPS origin, WebAuthn RP ID, secure `__Host-`
   cookies, SES, S3, KMS, structured JSON logging, TLS terminator CIDR, and
   database credentials are production values. Production startup fails closed
   when these requirements are not met.
5. Record the expected migration head:

   ```bash
   uv run --project backend alembic -c backend/alembic.ini heads
   # Expected for 5.0.0: e0f1a2b3c4d5 (head)
   ```

6. Verify free database capacity, application host capacity, KMS/SES/S3
   reachability, certificate validity, DNS/load-balancer control, and access to
   logs, traces, and database consoles.
7. Confirm support is ready for the one-time forced login. Existing browser
   sessions are intentionally invalidated by this release.

## Backup and restore rehearsal

The database operator must create a transactionally consistent backup after
write traffic is stopped and record its identifier, checksum, start/end time,
and retention location. A backup is not considered verified until a restore
rehearsal succeeds in an isolated MariaDB instance.

The rehearsal must verify:

- MariaDB accepts the restored data and `alembic current` reports the backed-up
  revision.
- Critical row counts match the source for users, organizations, memberships,
  API keys, billings, bills, receipts, jobs, and audit logs.
- Foreign keys and indexes are present and sampled encrypted fields decrypt
  through the application with the production KMS key.
- A restored user can authenticate in the isolated stack and retrieve an
  existing invoice.
- Measured restore time fits the approved recovery-time objective and the
  backup timestamp fits the recovery-point objective.

Record the rehearsal evidence and the exact restore procedure in the release
record. Abort before migration if either objective is missed.

## Enter maintenance and drain work

1. Put the external TLS terminator/load balancer into maintenance mode. Reject
   browser and API mutations; leave operator health access available. Confirm a
   synthetic write is blocked before continuing.
2. Stop scheduled producers and integrations that can enqueue work.
3. For the default database driver, monitor `jobs` until `running` reaches zero
   and all due `pending` work has completed. Record pending, running, failed,
   oldest-pending age, and in-flight job types. Then stop the worker:

   ```bash
   RENTIVO_APP_ENV_FILE=/etc/rentivo/app.env \
     docker compose --env-file /etc/rentivo/db.env stop worker
   ```

   The worker does not gracefully drain on `SIGTERM`; an interrupted job is
   reclaimed after `RENTIVO_JOB_WORKER_STUCK_AFTER_SECONDS`. Never stop it while
   `running` is nonzero unless the release commander accepts that retry.
4. For Temporal, wait for running workflows on `rentivo-jobs` to complete, stop
   producers, then stop the worker. Record outstanding workflow IDs.
5. Create the verified cutover backup and recheck that no writes occurred after
   its consistency point.

Abort if maintenance cannot block writes, work cannot drain inside the approved
window, a non-idempotent side effect is uncertain, or the backup cannot be
verified.

## Pin immutable artifacts

Set `RELEASE_SHA` to the complete tested commit. Resolve and record the registry
digest for every application image; tags alone are insufficient.

```bash
export RELEASE_SHA=<40-character-tested-sha>
docker buildx imagetools inspect "${REGISTRY}/rentivo-api:${RELEASE_SHA}"
docker buildx imagetools inspect "${REGISTRY}/rentivo-worker:${RELEASE_SHA}"
docker buildx imagetools inspect "${REGISTRY}/rentivo-frontend:${RELEASE_SHA}"
```

Verify the deployment manifest resolves to those exact digests. The API and
migration use the same API artifact. Do not continue if an image is mutable,
missing, built from another SHA, or was not produced by the complete gate.

## Migrate and roll out exactly once

The protected deployment workflow is the canonical production entrypoint. It
must receive the tested SHA/digests, run one `migrate` job, wait for success,
start `api`, `worker`, `frontend`, and `proxy`, and report migration, rollout,
and smoke status as one result. Trigger it once. Do not also run a manual
Compose rollout.

For an approved self-hosted/manual deployment, check out the exact SHA and run
the equivalent default topology once:

```bash
git rev-parse HEAD                     # must equal RELEASE_SHA
make stack-config \
  RENTIVO_DB_ENV_FILE=/etc/rentivo/db.env \
  RENTIVO_APP_ENV_FILE=/etc/rentivo/app.env
make stack-up \
  RENTIVO_DB_ENV_FILE=/etc/rentivo/db.env \
  RENTIVO_APP_ENV_FILE=/etc/rentivo/app.env
```

`stack-up` starts MariaDB, runs the one-shot Alembic `migrate` service, and only
then starts API and worker; Nginx waits for API readiness and frontend health.
Do not precede it with `stack-migrate`, because that would create a second
migration invocation. `stack-migrate` is for rehearsals and operator-directed
migration-only work.

Record migration start/end time, exit code, logs, and revision:

```bash
RENTIVO_APP_ENV_FILE=/etc/rentivo/app.env \
  docker compose --env-file /etc/rentivo/db.env logs migrate
RENTIVO_APP_ENV_FILE=/etc/rentivo/app.env \
  docker compose --env-file /etc/rentivo/db.env exec api \
    alembic -c backend/alembic.ini current
```

The reported revision must equal the recorded expected head before traffic is
enabled.

## Health, alerts, and smoke

Keep maintenance mode active while validating:

```bash
curl --fail --silent --show-error https://rentivo.example.com/health
curl --fail --silent --show-error https://rentivo.example.com/api/v1/ready
./scripts/smoke-production-stack.sh https://rentivo.example.com
```

Confirm `/health` is JSON liveness, `/api/v1/ready` is dependency-aware JSON
readiness, `/` serves the React landing page, crawler endpoints have their
declared media types, and request responses include `X-Request-ID`. The shell
smoke covers signup, password login, protected-session behavior, logout, and
server-side token revocation. Use the gated production-stack Playwright project
for fresh-account empty states, billing/invoice work, worker-produced output,
and organization-grant denial. Delete or disable smoke data afterward.

For the first 15 minutes, abort or re-enter maintenance immediately on any of:

- readiness fails twice consecutively or for more than 60 seconds;
- any migration error, unexpected revision, integrity error, or data-loss
  signal;
- sustained 5xx rate above 1% for 5 minutes, or any burst above 5% for 1 minute;
- p95 API latency more than twice the pre-release baseline for 5 minutes;
- authentication, MFA, billing, invoice download, or logout smoke failure;
- worker heartbeat absent for 2 minutes, a `running` job older than the stuck
  threshold, failed-job growth, or queue age above 5 minutes;
- elevated frontend runtime errors, KMS/SES/S3 failures, or a security control
  failing closed for valid production traffic.

Do not ignore an alert because health endpoints are green. Record the decision
and request IDs for every failure.

## Enable traffic and verify

1. Remove maintenance mode once every smoke check passes.
2. Confirm real traffic reaches the new release SHA and no host runs a different
   application digest.
3. Re-run readiness and the read-only smoke checks at 5, 15, 30, and 60 minutes.
4. Watch 4xx/5xx rate, p50/p95/p99 latency, frontend errors and Web Vitals,
   worker heartbeat, pending/running/failed jobs, oldest queue age, database
   connections/locks, KMS, SES, S3, CPU, memory, and disk.
5. Verify existing users receive the expected fresh-login experience, new
   accounts have empty billings/invoices/organizations/config state, API-key
   organization grants and scopes are enforced, and logout revokes the hidden
   one-day login key.
6. Close the release only after the 60-minute observation window, alert state is
   normal, smoke data is removed, support has no unexplained regression, and
   the release record is complete.

## Recovery

Choose recovery based on schema compatibility and data written since cutover.

### Redeploy the previous new-stack version

If the schema remains compatible, enter maintenance, drain the current worker,
and redeploy the previously recorded React/FastAPI API, worker, and frontend
digests. Do not rebuild the old SHA. Run the previous stack's readiness and
smoke checks before enabling traffic. Do not run a downgrade migration unless a
reviewed recovery change explicitly requires it.

### Forward fix

Use a forward fix when reverting artifacts would conflict with the migrated
schema or when post-release writes must be retained. The fix receives a new
immutable SHA, the complete release gate, a reviewed migration if needed, and
the same one-shot rollout procedure. Keep maintenance active until it passes.

### Restore the database

Restore only when corruption, incompatible schema changes, or unacceptable data
mutation makes artifact redeployment/forward repair unsafe. Keep maintenance
active, stop API and worker, preserve the failed database for investigation,
restore the verified backup, deploy the matching previous new-stack digests,
verify revision and critical row counts, then run the full smoke suite. Record
and communicate all data lost after the backup consistency point.

Never route traffic to, rebuild, or restore the deleted legacy application. It
is not a supported artifact, schema owner, or recovery target.
