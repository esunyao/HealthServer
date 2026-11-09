# Runtime architecture

NutriAthenaAgent exposes the HealthMind run protocol and executes one authorized meal attempt through a durable PostgreSQL worker. Its responsibilities are grouped beneath `src/nutriathena_agent`; [the package navigation](../src/nutriathena_agent/AGENTS.md) links each subsystem to its implementation and tests.

## Components

| Component | Responsibility |
|---|---|
| `cli` | Preserve command syntax, dispatch commands and reconcile smoke submissions |
| `config` | Load and validate environment settings; pass immutable values to components |
| `runtime` | Compose dependencies, own resource lifetimes, locate assets and calculate artifact identity |
| `api` | Validate HTTP input, authorize callers and translate run outcomes into responses |
| `execution` | Coordinate run operations and execute the existing lease/fencing worker loop |
| `storage` | Implement the repository port with focused PostgreSQL components and checked migrations |
| `integrations` | Adapt JWT/JWKS, model configuration, image HTTP downloads and MCP sessions |
| `meal` | Build the LangChain tool loop, assemble the maintained prompt and validate final results |
| `observability` | Render safe logs and model/tool execution traces |
| `examples` | Retain the offline graph and minimal agent examples |

The CLI selects a command before loading its required configuration. The HTTP application factory asks `runtime` to compose a repository, token verifier, worker and run service. Its lifespan opens only resources it owns, checks schema readiness, starts the worker and releases resources in reverse order. An injected repository remains owned by its caller. Startup failure also closes a partially opened pool. The `serve` command does not apply migrations; `migrate` remains explicit.

HTTP routes delegate business coordination to the run service. The execution layer depends on structural `RunRepository` and `MealRunner` ports. Database implementations do not import HTTP routes; model/MCP adapters do not depend on CLI or application bootstrap. No global service locator or plugin registry is required.

## Meal execution

The runner prefetches the authorized capture context once, downloads its allowed images in memory, and supplies image blocks and untrusted meal data to the model. LangChain `create_agent` exposes only `capture_context` and `nutrition_context`. The former presents sanitized cached capture data; the latter retains model-driven timing. The runner verifies that both tools were presented and validates the final text against the existing meal result contract. Invalid results become `needs_review` without a repair call.

The worker retains the current pending claim, deployment identity checks, heartbeat, cancellation, timeout and terminal fencing behavior. Lease expiry interrupts a running attempt rather than replaying a model call. Storage schema, retention periods and migration checksums are unchanged; the known historical migration LF/CRLF pair remains supported.

## Compatibility and verification

HTTP fields/statuses, CLI commands, the `agentdevelop` alias and `python -m nutriathena_agent.main` remain supported. Internal flat modules have moved to their responsibility packages. Release helper imports now use `nutriathena_agent.runtime.artifact` and `nutriathena_agent.meal.contract`.

Settings use Pydantic Settings at the environment boundary while keeping existing variable names, legacy aliases, per-key shell precedence, CSV hosts and debug overrides. The retained teaching commands do not require service/database configuration. Logging continues to support text/flat JSON, file rotation, color control and safe exception chains.

See [the test navigation](../tests/AGENTS.md) for offline and isolated PostgreSQL checks. Prompt and output-schema hashes characterize the pre-refactor contract. Fake-model tests execute the actual tool loop using fake external transports. Any source or dependency change produces a new artifact digest; deployment and release registration follow [the release guide](release.md).
