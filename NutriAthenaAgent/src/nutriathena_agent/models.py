"""HTTP request and response models for the HealthMind run contract."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


_SHA256 = r"^[0-9a-f]{64}$"


class ThreadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    attempt_id: UUID | None = None


class ThreadCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: UUID
    metadata: ThreadMetadata


class ThreadIdentityMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    attempt_id: UUID


class ThreadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: UUID
    metadata: ThreadIdentityMetadata


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    attempt_id: UUID
    trace_id: str = Field(min_length=1, max_length=128)


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    attempt_id: UUID
    release_id: UUID
    artifact_sha256: str = Field(pattern=_SHA256)


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_id: str = Field(min_length=1, max_length=128)
    input: RunInput
    metadata: RunMetadata
    on_completion: Literal["keep"]


class RunIdentityMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    attempt_id: UUID
    release_id: UUID
    artifact_sha256: str = Field(pattern=_SHA256)


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    thread_id: UUID
    task_id: UUID
    attempt_id: UUID
    assistant_id: str = Field(min_length=1, max_length=128)
    status: Literal["pending", "running", "success", "error", "interrupted"]
    metadata: RunIdentityMetadata
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
