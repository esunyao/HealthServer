"""Identities and errors shared by execution and its adapters."""
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

class ConflictError(RuntimeError):
    """A requested identity is already bound to different content."""

@dataclass(frozen=True)
class RuntimeIdentity:
    release_id: UUID
    deployment_key: str
    assistant_id: str
    artifact_sha256: str

    def matches(self, row: Mapping[str, Any]) -> bool:
        return (
            str(row["release_id"]) == str(self.release_id)
            and row["agent_deployment_key"] == self.deployment_key
            and row["agent_assistant_id"] == self.assistant_id
            and str(row["agent_artifact_sha256"]).strip() == self.artifact_sha256
        )
