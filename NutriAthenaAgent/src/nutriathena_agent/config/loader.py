"""Validate environment settings while retaining the established aliases."""
from typing import Annotated
from dotenv import load_dotenv
from pydantic import AliasChoices, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from ..logging_service import DebugLevel, parse_debug_level
from ..runtime.paths import MODULE_ROOT
from .models import DEFAULT_MODEL, DEFAULT_MCP_SCOPES, MealSettings, ModelSettings, RuntimeSettings

API_KEY_VAR = "NUTRIATHENA_MODEL_API_KEY"
BASE_URL_VAR = "NUTRIATHENA_MODEL_BASE_URL"
MODEL_VAR = "NUTRIATHENA_MODEL_ID"
MEAL_MODEL_VAR = "NUTRIATHENA_MEAL_MODEL_ID"

def load_env() -> None:
    """Shell values win per key; new names win over legacy names after merging."""
    load_dotenv(MODULE_ROOT / ".env", override=False)

class _Environment(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", frozen=True, hide_input_in_errors=True,
        populate_by_name=True, env_prefix="NUTRIATHENA_",
    )

class _ModelEnvironment(_Environment):
    model: str = Field(default=DEFAULT_MODEL, validation_alias=AliasChoices(MODEL_VAR, "AGENTDEVELOP_MODEL"))
    api_key: str = Field(min_length=1, repr=False, validation_alias=AliasChoices(API_KEY_VAR, "AGENTDEVELOP_API_KEY"))
    base_url: str = Field(min_length=1, validation_alias=AliasChoices(BASE_URL_VAR, "AGENTDEVELOP_BASE_URL"))
    model_config = SettingsConfigDict(env_ignore_empty=True)

class _MealEnvironment(_ModelEnvironment):
    model: str = Field(min_length=1, validation_alias=AliasChoices(MEAL_MODEL_VAR, "AGENTDEVELOP_MEAL_MODEL"))
    mcp_url: str = Field(min_length=1, validation_alias=AliasChoices("NUTRIATHENA_MCP_URL", "AGENTDEVELOP_MCP_URL"))
    token_url: str = Field(min_length=1, validation_alias=AliasChoices("NUTRIATHENA_MCP_OAUTH_TOKEN_URL", "AGENTDEVELOP_OAUTH_TOKEN_URL"))
    oauth_client_id: str = Field(min_length=1, validation_alias=AliasChoices("NUTRIATHENA_MCP_CLIENT_ID", "AGENTDEVELOP_OAUTH_CLIENT_ID"))
    oauth_client_secret: str = Field(min_length=1, repr=False, validation_alias=AliasChoices("NUTRIATHENA_MCP_CLIENT_SECRET", "AGENTDEVELOP_OAUTH_CLIENT_SECRET"))
    mcp_scopes: str = Field(default=DEFAULT_MCP_SCOPES, validation_alias=AliasChoices("NUTRIATHENA_MCP_SCOPES", "AGENTDEVELOP_MCP_SCOPES"))
    media_allowed_hosts: Annotated[frozenset[str], NoDecode] = frozenset()
    debug_level: DebugLevel = Field(default=DebugLevel.OFF, validation_alias="NUTRIATHENA_DEBUG")

    @field_validator("media_allowed_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value):
        if isinstance(value, str):
            return frozenset(item.strip().lower() for item in value.split(",") if item.strip())
        return value

    @field_validator("debug_level", mode="before")
    @classmethod
    def parse_debug(cls, value):
        return parse_debug_level(value)

class _RuntimeEnvironment(_Environment):
    host: str = "0.0.0.0"
    port: int = Field(default=8101, ge=1, le=65535)
    database_url: str = Field(min_length=1, repr=False)
    oauth_issuer: str = Field(min_length=1)
    oauth_jwks_url: str = Field(min_length=1)
    oauth_audience: str = "healthmind-agent"
    oauth_client_id: str = "healthmind-agent"
    oauth_scope: str = "healthmind.agent.run"
    release_id: str
    deployment_key: str = Field(min_length=1)
    assistant_id: str = Field(min_length=1)
    worker_poll_seconds: float = Field(default=0.5, ge=0.05, le=30, allow_inf_nan=False)
    lease_seconds: int = Field(default=90, ge=10, le=3600)
    run_timeout_seconds: int = Field(default=600, ge=5, le=7200)
    result_retention_hours: int = Field(default=24, ge=24, le=720)
    row_retention_days: int = Field(default=180, ge=180, le=3650)
    debug_level: DebugLevel = Field(default=DebugLevel.OFF, validation_alias="NUTRIATHENA_DEBUG")

    @field_validator("database_url", "oauth_issuer", "oauth_jwks_url", "release_id", "deployment_key", "assistant_id", mode="before")
    @classmethod
    def strip_required(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("debug_level", mode="before")
    @classmethod
    def parse_debug(cls, value):
        return parse_debug_level(value)

def _load(source, target):
    load_env()
    try:
        return target.model_validate(source().model_dump())
    except ValidationError as exception:
        # Never put input values (especially credentials) into config errors.
        names = "、".join(".".join(map(str, item["loc"])) for item in exception.errors(include_input=False))
        raise RuntimeError(f"运行配置无效或缺失：{names}") from exception

def load_model_settings() -> ModelSettings:
    return _load(_ModelEnvironment, ModelSettings)

def load_meal_settings() -> MealSettings:
    return _load(_MealEnvironment, MealSettings)

def load_runtime_settings() -> RuntimeSettings:
    return _load(_RuntimeEnvironment, RuntimeSettings)
