from typing import Any, Literal

from pydantic import BaseModel, Field


class MutationRequest(BaseModel):
    csrf_token: str
    reason: str = Field(min_length=3, max_length=500)
    preview_token: str | None = None
    confirmation: str | None = None


class KafkaProduceRequest(MutationRequest):
    topic: str
    key: str | None = None
    partition: int | None = None
    headers: dict[str, str] = {}
    payload: Any
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
    tool_codes: list[str] = ["nutrimemo.capture_context.get", "orion.nutrition_context.get"]


class RetryRequest(MutationRequest):
    release_id: str | None = None


class RecoveryRequest(MutationRequest):
    operation: Literal["reset_outbox", "recover_attempt", "cancel_task"]
    schema_name: Literal["healthmind", "nutri"] = "healthmind"
    record_id: str

