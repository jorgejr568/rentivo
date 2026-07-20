# Production Release Runbook

This runbook governs the Rentivo 5.0 big-bang release and later releases of the
React/Vite, FastAPI, worker, MariaDB, and Nginx stack. The release is atomic:
one immutable source SHA supplies every application image, one Alembic job runs
before application services, and traffic moves to that tested stack once.

The first 5.0 cutover has one narrowly scoped exception to the normal rollback
policy: retain the verified pre-cutover legacy web and worker image digests
together with the verified pre-cutover database backup as one rollback
artifact. These three parts are inseparable because the pre-cutover images must
never run against the 5.0 schema. Later releases must not use the legacy images;
they recover with the previous React/FastAPI digests, a forward fix, or a
matching verified database restore.

## Ownership and release record

Assign named people before the window. One person may hold more than one role,
but every role needs a primary and a backup.

| Role | Responsibility |
|---|---|
| Release commander | Owns go/abort decisions and the release timeline |
| Database operator | Owns backup, restore rehearsal, migration, and revision checks |
| Runtime operator | Owns image verification, automated rollout, health, and rollback |
| Application verifier | Runs smoke tests and checks critical user workflows |
| Incident lead | Owns alerts, communications, and recovery coordination |

Create a release record containing the UTC window, owners, immutable Git SHA,
API/worker/frontend image references and digests, previous production SHA and
digests, expected Alembic revision, backup identifier, restore-rehearsal result,
migration duration, rollout timestamps, smoke result, and final decision.
For the first 5.0 cutover, also record the pre-cutover web and worker image
digests, their OCI source/revision and attestation verification, the paired
backup identifier and checksum, and the restore rehearsal. Retain or expire all
three parts together.

## Preflight

Complete every item before announcing the maintenance window:

1. Confirm the protected release gate passed for the exact release SHA: backend
   and frontend tests, 100% coverage, lint, OpenAPI freshness, production
   Compose validation, image builds, exact-tag vulnerability scans, the
   real-stack smoke/E2E suite, and the populated production migration rehearsal
   from `55dc25bae00d` to `e0f1a2b3c4d5`.
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

6. Verify free database capacity, application host capacity, certificate
   validity, DNS/load-balancer control, and access to logs, traces, and database
   consoles. The protected automation performs the authoritative production
   configuration check and real KMS, S3, SES, and job backend reachability
   checks before migration; a failure aborts without changing the schema.
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

For the first 5.0 cutover, the gate must first upgrade a populated schema at
revision `55dc25bae00d` through the complete migration chain to
`e0f1a2b3c4d5`. Its before/after evidence must preserve representative users,
MFA and passkeys, organizations and memberships, billings and billing items,
bills, receipts, expenses, and audit data; it must also prove all billing-item
UUIDs are populated and distinct. An empty-database upgrade or a final-migration
round trip is not a populated production migration rehearsal.

Before entering the release window, run the protected
`.github/workflows/prepare-legacy-rollback.yml` workflow with the exact
40-character pre-cutover SHA. It must prove that SHA is an ancestor of `main`,
run the detached legacy test suite, build separate `Dockerfile` web and
`Dockerfile.worker` worker images, scan both exact images, attest both digests,
and record their immutable `legacy-web@sha256:...` and
`legacy-worker@sha256:...` references. A retry publishes a distinct traceable
tag, so record only the final digest references as rollback evidence.

Pull both prepared images by digest, verify their OCI source/revision labels and
GitHub attestations, start them against the isolated restored database, and run
the pre-cutover web and worker smoke suite. Record both digests beside the
backup as the one rollback artifact. An untested local image, a rebuilt image,
or either image paired with a different backup is not a rollback artifact.

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
docker buildx imagetools inspect "${REGISTRY}/api:${RELEASE_SHA}"
docker buildx imagetools inspect "${REGISTRY}/worker:${RELEASE_SHA}"
docker buildx imagetools inspect "${REGISTRY}/frontend:${RELEASE_SHA}"
```

Verify the deployment manifest resolves to those exact digests. The API and
migration use the same API artifact. Do not continue if an image is mutable,
missing, built from another SHA, or was not produced by the complete gate.
The workflow tests and scans these exact images; they are never rebuilt after verification.

## Migrate and roll out exactly once

The protected deployment workflow is the canonical production entrypoint. It
must receive the tested SHA/digests and complete these ordered stages:
`configuration`, `production_integrations`, `migration`, `rollout`, and
`smoke`. Configuration validation and real KMS, S3, SES, and job backend
reachability must succeed before migration. It then runs one `migrate` job,
waits for success, starts `api`, `worker`, `frontend`, and `proxy`, and reports
all five stages as one result. The automation must deploy image references by
recorded digest, not rebuild or resolve mutable tags. Trigger it once.

There is no supported direct/manual production rollout. The repository Compose
services contain local `build:` definitions and therefore cannot consume the
recorded registry digests as a production deployment contract. Local stack
targets, Docker builds, ad hoc Compose overrides, and host-side migration
commands must not be used for production. If protected automation cannot accept
and report the complete-gate-tested SHA and digest references, abort the release
until that contract is available.

The `rentivo.deploy.v2` request includes expected Alembic revision
`e0f1a2b3c4d5`. Its response must echo the tested SHA and exact image digests,
report one deployment, and return the exact ordered stage list. Every stage
must include UTC start/end timestamps. Migration evidence must include exit
code zero, a content-addressed log checksum, and the current Alembic revision;
that revision must equal the expected head before traffic is enabled.

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

All artifact/database rollbacks use the protected **Protected Production
Rollback** workflow in `.github/workflows/rollback.yml`. Dispatch it from the
failed release's repository Actions page and obtain the required `production`
environment approval. The workflow sends one authenticated, idempotent HTTPS
request and never builds images or resolves tags.

Every dispatch supplies `rollback_kind`, the artifact's 40-character
`target_sha`, and `expected_alembic_revision`. Image inputs must be immutable
references in their exact GHCR repositories and contain `@sha256:`. The
workflow pulls every image, verifies its OCI source and revision, and verifies
its GitHub attestation from the expected trusted workflow before contacting the
production receiver.

- For `first-5.0-cutover`, set `expected_alembic_revision` to
  `55dc25bae00d` and supply `legacy_web_ref`, `legacy_worker_ref`,
  the `legacy_attestation_source_sha` recorded by the preparation workflow,
  `database_backup_id`, and the verified `database_backup_sha256` including its
  `sha256:` prefix. Leave `api_ref`, `worker_ref`, and `frontend_ref` empty.
- For `new-stack`, supply `api_ref`, `worker_ref`, and `frontend_ref` from the
  same verified release. This is an image-only rollback: leave both legacy refs
  and both database backup inputs empty. The receiver must perform a
  `schema_check` and preserve all post-release database writes.
- For `new-stack-restore`, supply `api_ref`, `worker_ref`, `frontend_ref`,
  `database_backup_id`, and `database_backup_sha256` from one matching verified
  release. Leave both legacy refs empty.

The idempotency key is the SHA-256 of the full normalized rollback payload, so
changing an image, backup, revision, kind, or stage contract creates a new key.
Accept success only from a `rentivo.rollback.v1` response that echoes that key,
the rollback kind, target SHA, exact digest references, optional backup, and
expected revision. It must report one rollback and the exact mode-specific
ordered stages: `maintenance`, `drain`, `schema_check`, `rollout`, `smoke` for
`new-stack`, or `maintenance`, `drain`, `database_restore`, `rollout`, `smoke`
for either restore mode. Every stage must include exit code zero, a
content-addressed log checksum, and ordered RFC 3339 UTC timestamps parsed
numerically, including fractional seconds. Restore evidence must echo the
backup ID, checksum, and resulting revision; image-only evidence must echo the
live schema revision and must not report a database restore. Attach the
dispatch URL and response evidence to the release record.

### First 5.0 cutover rollback

Use this procedure only during the first 5.0 cutover and only when the release
commander decides that forward recovery cannot fit the approved outage. The
verified pre-cutover legacy web and worker image digests and their paired
database backup are the one rollback artifact; never mix any part with another
version.

1. Enter maintenance mode and verify that browser, API, scheduler, and
   integration writes are blocked.
2. Stop the API and worker, drain or stop all job producers, and preserve the
   failed 5.0 database for investigation.
3. Restore the verified pre-cutover database backup to the production database;
   verify its checksum, expected pre-cutover schema revision, critical row
   counts, foreign keys, and sampled decryptions.
4. Redeploy the verified pre-cutover legacy web and worker images by digest
   through the protected runtime path with rebuild and tag resolution disabled.
   Verify both running containers report exactly the recorded digests.
5. Run the pre-cutover smoke suite against operator-only traffic, including
   authentication, billing reads/writes, invoice retrieval, and worker output.
6. Re-enable traffic only after readiness, smoke, alerts, and database checks
   pass; record the rollback timestamps and the data-loss interval from the
   restored backup consistency point.

Destroy normal deployment access to these artifacts after the 5.0 cutover is
formally closed. Later releases must not use the legacy images, even if the
digests remain in retention storage.

### Redeploy the previous new-stack version

If the schema remains compatible, enter maintenance, drain the current worker,
and dispatch `new-stack` with the previously recorded React/FastAPI API, worker,
and frontend digest references. This image-only path forbids backup inputs,
checks the live Alembic revision, and must not restore or downgrade the
database. The automation redeploys those exact immutable references; never
rebuild the old SHA, retag an image, or fall back to local Compose. Run the
previous stack's readiness and smoke checks before enabling traffic.

### Forward fix

Use a forward fix when reverting artifacts would conflict with the migrated
schema or when post-release writes must be retained. The fix receives a new
immutable SHA, the complete release gate, a reviewed migration if needed, and
the same one-shot rollout procedure. Keep maintenance active until it passes.

### Restore the database

Restore only when corruption, incompatible schema changes, or unacceptable data
mutation makes artifact redeployment/forward repair unsafe. Keep maintenance
active, stop API and worker, preserve the failed database for investigation,
and dispatch `new-stack-restore` with the verified backup and matching previous
new-stack digests. Verify revision and critical row counts, then run the full
smoke suite. Record and communicate all data lost after the backup consistency
point.

Outside the explicitly bounded first 5.0 procedure, never route traffic to,
rebuild, or restore the pre-cutover application. It is not a supported artifact,
schema owner, or recovery target for later releases.
