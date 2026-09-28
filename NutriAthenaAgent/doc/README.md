# Agent runtime contract

This document records the public HTTP and persistence boundary implemented by NutriAthenaAgent. HealthMind integration details are maintained in `HealthMind/doc/agent-runtime.md`.

## HTTP API

All routes other than `GET /healthz` require `Authorization: Bearer <token>`. The service validates the signature against configured JWKS and checks exact issuer, audience, caller (`azp` or `client_id`) and scope before reading or changing run data.

| Method and path | Purpose | Result |
|---|---|---|
| `GET /healthz` | Database liveness | `{"status":"ok"}` or HTTP 503 |
| `POST /threads` | Persist/reuse attempt-bound thread; request metadata has `task_id` and optional `attempt_id` | `{"thread_id":"<attempt UUID>"}` |
| `GET /threads/{thread_id}` | Read fixed thread identity | Thread/task/attempt UUIDs |
| `POST /threads/{thread_id}/runs` | Persist one run; requires `Idempotency-Key: <attempt UUID>` | Run ID, assistant, release/artifact identity and status |
| `GET /threads/{thread_id}/runs` | Reconcile a possibly ambiguous submission | Top-level JSON array; one run at most per attempt |
| `GET /runs/{run_id}` | Read current run status | `pending`, `running`, `success`, `error` or `interrupted` |
| `GET /runs/{run_id}/wait` | Wait up to `timeout_seconds` (1–600) for terminal result | On success `{"output": <result object>}`; explicit error/interrupted or result-expired response otherwise |
| `POST /runs/{run_id}/cancel` | Request best-effort cancellation | Current run state; pending becomes interrupted immediately |

The run request follows the HealthMind protocol: `assistant_id`; input `{task_id, attempt_id, trace_id}`; metadata `{task_id, attempt_id, release_id, artifact_sha256}`; and `on_completion: "keep"`. `release_id` is a UUID. `Idempotency-Key` must equal `attempt_id`. The server checks the configured release UUID, assistant ID and its locally computed artifact digest before it persists a run. The response identity comes from stored runtime configuration and the digest of files loaded by this deployment, never by echoing the client's metadata.

The canonical request JSON SHA-256 is the idempotency comparison value. Repeating an attempt with the same canonical request returns the original `run_id` and state. Reusing the attempt ID with a different request returns HTTP 409 `IDEMPOTENCY_CONFLICT`; the worker is not started twice.

## PostgreSQL lifecycle

The service writes only to independent PostgreSQL schema `nutriathena_agent`. There are two business tables:

- `agent_threads` fixes `thread_id = attempt_id` and the associated `task_id`; the unique composite key supports the run foreign key.
- `agent_runs` stores the request digest and minimal request, the fixed release, requested and actual deployment identity, run state, result/error, lease/fencing state, and retention timestamps.

`schema_migrations` is infrastructure metadata, not business state. `nutriathena-agent migrate` applies numbered SQL migrations under a PostgreSQL advisory transaction lock and records filename, SHA-256, timestamp, and execution time. Applied filenames/checksums are immutable. Service startup checks schema readiness but does not migrate or delete data.

The worker claims only pending rows with `FOR UPDATE SKIP LOCKED`, increments `lease_version`, and renews the lease. Terminal writes compare the run ID, owner, version and active state. A stale worker cannot overwrite a newer state. Pending rows remain recoverable after restart; a running row whose lease expires becomes interrupted and is never automatically sent to the model again.

Successful outputs are retained for at least 24 hours. An expiry task clears only result JSON and digest and sets `result_purged_at`. Run tombstones and thread identity are retained at least 180 days; only terminal runs receive `retention_until`. The janitor deletes terminal runs before their now-orphaned threads. HealthMind and Agent exchange UUIDs and protocol data over HTTP; there is no cross-schema foreign key.

## MCP calls and images

The production runner uses the MCP Python SDK so each call can include the reserved `_meta.tool_call_id`. The ID is `uuid5(UUID(attempt_id), full_tool_code)` with the stable full tool codes `nutrimemo.capture_context.get` and `orion.nutrition_context.get`. The HealthMind MCP arguments remain only `taskId` and `attemptId`; a repeated read uses the same audit/idempotency ID and does not consume an additional call budget.

The capture read is performed once before the model starts so the runner can download authorized images for the existing vision graph. Its model-facing tool returns the same sanitized cached context. The nutrition-context tool retains its existing model-driven invocation timing. Signed image URLs are removed from model-facing context and are not persisted. The runner downloads only captured URLs whose hosts are explicitly named in `NUTRIATHENA_MEDIA_ALLOWED_HOSTS`; it rejects redirects, non-HTTPS remote hosts, unsupported image signatures/MIME, excessive image counts and oversized bodies. Image bytes stay in memory and are passed to the model as data URLs. If the capture has no usable image, the runner returns `needs_review/IMAGE_UNAVAILABLE` without claiming a model analysis.

## Verification and true smoke

`uv run pytest -q` runs offline contract, auth, image, API and worker tests. The PostgreSQL integration test creates an isolated temporary Docker container and removes only that container afterwards; it never connects to the project's configured database.

The true smoke command uses an already authorized HealthMind task/attempt plus OAuth client-credentials configuration. It posts once, uses list-runs for ambiguous submission reconciliation, and prints only run/status/identity digest/item count. No credential, signed URL, image content or meal name is printed. A real model smoke must not claim success until it has an authorized existing capture with image context and valid local test credentials.
