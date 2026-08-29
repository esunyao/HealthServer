# HealthMind

HealthMind is the AI orchestration service for HealthServer. It owns task state, workflow-release pinning, contract validation, reliable Kafka inbox/outbox delivery, MCP tool authorization, and audit records. It does not own user health records, meal records, images, prompts, knowledge bases, model routing, or vLLM lifecycle.

## Runtime dependencies

- PostgreSQL 17, schema `healthmind`; Flyway creates and migrates the 12 service tables.
- Kafka; logical destinations and consumer groups are configured through Nacos or environment variables.
- Authentik; use pre-registered clients and disable dynamic client registration.
- Dify `1.17.0`; Dify owns workflows, prompts, knowledge bases, sandbox execution, and the OpenAI-compatible vLLM provider.
- Orion and NutriMemo internal APIs, reached with separate Authentik `client_credentials` clients.

Copy `.env.example` to an ignored `.env` for local development. Never commit OAuth secrets, Dify API keys, Kafka credentials, or production endpoints. Dify application keys are mapped by `dify_app_id` under `healthmind.dify.app-keys` in Nacos.

## Workflow release

Flyway seeds only stable task types and MCP tool definitions. Create a tested workflow release, its schemas, and tool allow-list explicitly, then promote it with `src/main/resources/db/manual/promote_workflow_release.sql`. The script serializes promotion per task type, retires the previous production release, and writes the release audit in one transaction.

Tasks pin the production release that exists when their input event is accepted. A running or retried task never switches to a newer production release.

## Security and retention

Dify calls `/mcp` with audience `healthmind-mcp`; tools receive only `task_id` and `attempt_id`. HealthMind derives the subject, capture session, and meal from the pinned task. Orion and NutriMemo require their own audiences and scopes. Tool request/response bodies and short-lived image URLs stay in memory; only SHA-256 digests and operational audit fields are stored.

Defaults are 30 days for accepted structured results and integration records, and 180 days for task/tool audit data. Override them through Nacos or environment variables.
