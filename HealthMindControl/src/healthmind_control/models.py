from typing import Any, Literal

from pydantic import BaseModel, Field


class MutationRequest(BaseModel):
    csrf_token: str
    reason: str = Field(min_length=3, max_length=500)
    preview_token: str | None = None
    confirmation: str | None = None


class ExecuteRequest(BaseModel):
    """Execution intentionally carries no mutable operation parameters."""

    csrf_token: str
    preview_token: str
    confirmation: str
    accept_warnings: bool = False


class KafkaProduceRequest(MutationRequest):
    topic: str
    key: str | None = None
    partition: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    payload_text: str
    force: bool = False


class ReleaseRequest(MutationRequest):
    operation: Literal["create", "promote", "retire", "rollback"]
    release_id: str | None = None
    task_type_code: str = "nutrition.meal_analysis"
    release_version: str | None = None
    workspace_id: str | None = None
    app_id: str | None = None
    workflow_id: str | None = None
    workflow_version: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    tool_codes: list[str] = Field(default_factory=lambda: [
        "nutrimemo.capture_context.get", "orion.nutrition_context.get",
    ])
    timeout_seconds: int = Field(120, ge=5, le=3600)
    max_attempts: int = Field(3, ge=1, le=20)


class ToolBinding(BaseModel):
    tool_code: str
    required: bool = True
    max_calls: int = Field(1, ge=1, le=100)
    timeout_ms: int = Field(10000, ge=100, le=60000)


class BindToolsRequest(MutationRequest):
    release_id: str
    bindings: list[ToolBinding] = Field(default_factory=list)


class RetryRequest(MutationRequest):
    release_id: str | None = None


class RecoveryRequest(MutationRequest):
    operation: Literal[
        "reset_outbox", "replay_outbox", "replay_nutri_inbox", "replay_hm_inbox",
        "recover_attempt", "cancel_task",
    ]
    schema_name: Literal["healthmind", "nutri"] = "healthmind"
    record_id: str
    expected_lock_version: int | None = None


class DebugRunRequest(BaseModel):
    csrf_token: str
    name: str = Field(min_length=1, max_length=120)
    mode: Literal["real", "emulated", "mixed"] = "mixed"
    context: dict[str, Any] = Field(default_factory=dict)


class DebugStepRequest(MutationRequest):
    record_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class FixtureFieldMapping(BaseModel):
    mode: Literal["omit", "inherit", "related", "generate", "manual"] = "omit"
    source_field: str | None = None
    generator: Literal["uuid", "now", "hold_until", "retention_until", "sha256"] | None = None
    value: Any = None


class FixturePreviewRequest(MutationRequest):
    operation: Literal["insert", "update"] = "insert"
    table_name: str
    source_identifier: str | None = None
    target: dict[str, Any] = Field(default_factory=dict)
    mappings: dict[str, FixtureFieldMapping] = Field(default_factory=dict)


class McpSessionRequest(MutationRequest):
    source_task_id: str
    inherit_trace_id: bool = True


class FixtureLifecycleRequest(MutationRequest):
    task_id: str


class OutboxReleaseRequest(MutationRequest):
    schema_name: Literal["healthmind", "nutri"]
    event_id: str


class SqlPreviewRequest(MutationRequest):
    sql: str = Field(min_length=1, max_length=200_000)
    database: Literal["primary"] = "primary"


class KafkaOffsetRequest(MutationRequest):
    group_id: str = Field(min_length=1, max_length=255)
    topic: str = Field(min_length=1, max_length=249)
    partition: int = Field(ge=0)
    position: Literal["absolute", "earliest", "latest", "timestamp", "delta"]
    value: int | None = None
