# NutriAthenaAgent

NutriAthenaAgent is the durable HealthMind meal-analysis runtime. HealthMind creates an attempt and calls this service over HTTP; the service persists the request in PostgreSQL, a leased worker runs the existing meal-analysis graph, and HealthMind retrieves the result. The module also retains two small LangGraph/LangChain teaching examples.

## Start the service

Use Python 3.11+ and `uv`:

```bash
cd NutriAthenaAgent
uv sync --extra test
```

Copy `.env.example` to `.env` and configure the runtime, database, OAuth issuer/JWKS, model, and read-only HealthMind MCP client. Do not commit `.env` or place credentials in CLI arguments. Legacy `AGENTDEVELOP_*` model and MCP variables remain fallback aliases for existing local installations.

Apply the versioned SQL migration before starting the service:

```bash
uv run nutriathena-agent migrate
uv run nutriathena-agent serve
```

The HTTP service listens on `NUTRIATHENA_HOST:NUTRIATHENA_PORT` (default `0.0.0.0:8101`). `GET /healthz` checks database connectivity. Authenticated routes require an OAuth bearer token with the configured issuer, audience, allowed caller ID, and `healthmind.agent.run` scope.

The HealthMind run protocol is documented in [`doc/README.md`](./doc/README.md). The service creates an attempt-bound thread, accepts one idempotent run per attempt, returns pending/running/terminal status, supports best-effort cancellation, and retains successful output for at least 24 hours. PostgreSQL uses the isolated `nutriathena_agent` schema; this service has no cross-schema foreign keys and does not write HealthMind business records.

## Safe real smoke

`smoke` sends one real request through the deployed HTTP service, reconciles an ambiguous run submission by listing existing runs, waits for the result, and prints only IDs/status/digest and item count. It never prints access tokens, image URLs, or food names. Use an already authorized task and attempt with an available captured meal image; the command does not invent task context or a sample result.

```bash
uv run nutriathena-agent smoke \
  --task-id <authorized-task-uuid> \
  --attempt-id <authorized-attempt-uuid> \
  --trace-id <trace-id>
```

Configure `NUTRIATHENA_SMOKE_TOKEN_URL`, `NUTRIATHENA_SMOKE_CLIENT_ID`, and `NUTRIATHENA_SMOKE_CLIENT_SECRET` locally. Re-running with the same attempt and same request reuses the existing run; changing the request for an existing attempt is rejected as an idempotency conflict.

## Tests and teaching commands

Automated tests are offline and use replaceable runners/fake dependencies:

```bash
uv run pytest -q
uv run nutriathena-agent graph
uv run nutriathena-agent graph "嗯"
uv run nutriathena-agent agent "统计一下这句话的词数：晚饭吃了清蒸鲈鱼"
```

The `meal` command directly invokes one authorized attempt through the MCP and model runtime; production work should enter through `serve` so PostgreSQL idempotency, leases, retention, and cancellation remain in force.

## Meal analysis boundaries

- The maintained meal prompt and dietary skills under sibling `AgentDeveloper/skills` remain the authority; this service only adapts the existing graph to a replaceable runner.
- The capture MCP read is prefetched once per attempt to obtain authorized image URLs before the vision call; its model-facing tool returns the sanitized cached context. The nutrition MCP read keeps the existing model-driven tool-call timing. Stable audit IDs are UUIDv5 values derived from the attempt UUID and each complete MCP tool code, passed in MCP `_meta.tool_call_id`; each remote read occurs at most once.
- Only signed image URLs returned for the authorized capture are downloaded. Download hosts must be explicitly allowlisted with `NUTRIATHENA_MEDIA_ALLOWED_HOSTS`; redirects, unsupported MIME/signatures, too many images, and over-limit bodies are rejected. URLs and bytes are not written to model-facing context or service output.
- Missing or unavailable capture images produce the existing `needs_review` result contract. The service does not claim a successful model analysis in that case.
- The model has no shell, filesystem, write, delete, or subagent tools. HealthMind remains responsible for business-side authorization and result persistence.
