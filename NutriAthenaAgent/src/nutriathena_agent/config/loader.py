"""Load local configuration and validate runtime settings."""

import os
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from ..observability.levels import DebugLevel, parse_debug_level
from ..runtime.paths import MODULE_ROOT
from .models import (
    DEFAULT_MODEL,
    DEFAULT_MCP_SCOPES,
    MealSettings,
    ModelSettings,
    RuntimeSettings,
)

API_KEY_VAR = "NUTRIATHENA_MODEL_API_KEY"
BASE_URL_VAR = "NUTRIATHENA_MODEL_BASE_URL"
MODEL_VAR = "NUTRIATHENA_MODEL_ID"
MEAL_MODEL_VAR = "NUTRIATHENA_MEAL_MODEL_ID"
CONFIG_FILE = MODULE_ROOT / "config.yaml"
ENV_FILE = MODULE_ROOT / ".env"
_PREFIX = "NUTRIATHENA_"


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key.startswith(_PREFIX) or not key.isidentifier():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            values[key] = value
    return values


def _flatten(node: dict, prefix: str):
    for key, value in node.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise RuntimeError("config.yaml 的键必须由字母、数字或下划线组成")
        name = prefix + key.upper()
        if isinstance(value, dict):
            yield from _flatten(value, name + "_")
        elif isinstance(value, list):
            yield name, ",".join(map(str, value))
        elif value is not None:
            yield name, str(value)


def _read_yaml(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeError) as exception:
        mark = getattr(exception, "problem_mark", None)
        where = f"第 {mark.line + 1} 行" if mark is not None else "未知位置"
        raise RuntimeError(f"config.yaml 格式错误（{where}）") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError("config.yaml 顶层必须是键值映射")
    return dict(_flatten(data, _PREFIX))


def load_env() -> None:
    """Process environment wins over .env, which wins over config.yaml."""
    if os.environ.get("NUTRIATHENA_SKIP_LOCAL_CONFIG") == "1":
        return
    for source in (_read_dotenv(ENV_FILE), _read_yaml(CONFIG_FILE)):
        for name, value in source.items():
            if value:
                os.environ.setdefault(name, value)


class _Environment(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        populate_by_name=True,
        env_prefix=_PREFIX,
    )


class _ModelEnvironment(_Environment):
    model: str = Field(
        default=DEFAULT_MODEL,
        validation_alias=MODEL_VAR,
    )
    api_key: str = Field(
        min_length=1,
        repr=False,
        validation_alias=API_KEY_VAR,
    )
    base_url: str = Field(
        min_length=1,
        validation_alias=BASE_URL_VAR,
    )
    model_config = SettingsConfigDict(env_ignore_empty=True)


class _MealEnvironment(_ModelEnvironment):
    model: str = Field(
        min_length=1,
        validation_alias=MEAL_MODEL_VAR,
    )
    mcp_url: str = Field(
        min_length=1,
        validation_alias="NUTRIATHENA_MCP_URL",
    )
    token_url: str = Field(
        min_length=1,
        validation_alias="NUTRIATHENA_MCP_OAUTH_TOKEN_URL",
    )
    oauth_client_id: str = Field(
        min_length=1,
        validation_alias="NUTRIATHENA_MCP_CLIENT_ID",
    )
    oauth_client_secret: str = Field(
        min_length=1,
        repr=False,
        validation_alias="NUTRIATHENA_MCP_CLIENT_SECRET",
    )
    mcp_scopes: str = Field(
        default=DEFAULT_MCP_SCOPES,
        validation_alias="NUTRIATHENA_MCP_SCOPES",
    )
    media_allowed_hosts: Annotated[frozenset[str], NoDecode] = frozenset()
    debug_level: DebugLevel = Field(
        default=DebugLevel.OFF, validation_alias="NUTRIATHENA_DEBUG"
    )

    @field_validator("media_allowed_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value):
        if isinstance(value, str):
            return frozenset(
                item.strip().lower() for item in value.split(",") if item.strip()
            )
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
    debug_level: DebugLevel = Field(
        default=DebugLevel.OFF, validation_alias="NUTRIATHENA_DEBUG"
    )

    @field_validator(
        "port",
        "lease_seconds",
        "run_timeout_seconds",
        "result_retention_hours",
        "row_retention_days",
        mode="before",
    )
    @classmethod
    def parse_integer(cls, value):
        # Preserve int(environment_string), rather than accepting "8101.0".
        return int(value) if isinstance(value, str) else value

    @field_validator(
        "database_url",
        "oauth_issuer",
        "oauth_jwks_url",
        "release_id",
        "deployment_key",
        "assistant_id",
        mode="before",
    )
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
        names = "、".join(
            ".".join(map(str, item["loc"]))
            for item in exception.errors(include_input=False)
        )
        raise RuntimeError(f"运行配置无效或缺失：{names}") from exception


def load_model_settings() -> ModelSettings:
    return _load(_ModelEnvironment, ModelSettings)


def load_meal_settings() -> MealSettings:
    return _load(_MealEnvironment, MealSettings)


def load_runtime_settings() -> RuntimeSettings:
    return _load(_RuntimeEnvironment, RuntimeSettings)
