"""Immutable values passed explicitly to runtime components."""

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from ..observability.levels import DebugLevel

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_MCP_SCOPES = "healthmind.tool.nutrimemo.capture-context.read healthmind.tool.orion.nutrition-context.read"
MAX_MEAL_IMAGES = 10
MAX_MEAL_IMAGE_BYTES = 10 * 1024 * 1024
MAX_MEAL_TOTAL_IMAGE_BYTES = 100 * 1024 * 1024
MAX_EVIDENCE_BYTES = 1024 * 1024


class SettingsValue(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)


class ModelSettings(SettingsValue):
    model: str = DEFAULT_MODEL
    api_key: str = Field(repr=False)
    base_url: str


class MealSettings(ModelSettings):
    mcp_url: str
    token_url: str
    oauth_client_id: str
    oauth_client_secret: str = Field(repr=False)
    mcp_scopes: str
    max_images: int = MAX_MEAL_IMAGES
    max_image_bytes: int = MAX_MEAL_IMAGE_BYTES
    max_total_image_bytes: int = MAX_MEAL_TOTAL_IMAGE_BYTES
    max_evidence_bytes: int = MAX_EVIDENCE_BYTES
    media_allowed_hosts: frozenset[str] = Field(default_factory=frozenset)
    debug_level: DebugLevel = DebugLevel.OFF


class RuntimeSettings(SettingsValue):
    host: str
    port: int
    database_url: str = Field(repr=False)
    oauth_issuer: str
    oauth_jwks_url: str
    oauth_audience: str
    oauth_client_id: str
    oauth_scope: str
    release_id: UUID
    deployment_key: str
    assistant_id: str
    worker_poll_seconds: float = 0.5
    lease_seconds: int = 90
    run_timeout_seconds: int | float = 600
    result_retention_hours: int = 24
    row_retention_days: int = 180
    debug_level: DebugLevel = DebugLevel.OFF
