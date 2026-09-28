"""HTTP request models for the HealthMind run contract."""

from __future__ import annotations

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
