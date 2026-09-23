"""Model factories and settings for the teaching examples and meal agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 模块根目录 AgentDevelop/，.env 固定放在这里。
# config.py 位于 AgentDevelop/src/agentdevelop/，故上溯三层。
_MODULE_ROOT = Path(__file__).resolve().parents[2]

_ENV_FILE = _MODULE_ROOT / ".env"
_ENV_EXAMPLE = _MODULE_ROOT / ".env.example"

DEFAULT_MODEL = "deepseek-chat"

# 用 AGENTDEVELOP_ 前缀而不是 OPENAI_*，避免和机器上其他项目的全局 OPENAI_API_KEY 串味。
API_KEY_VAR = "AGENTDEVELOP_API_KEY"
BASE_URL_VAR = "AGENTDEVELOP_BASE_URL"
MODEL_VAR = "AGENTDEVELOP_MODEL"
MEAL_MODEL_VAR = "AGENTDEVELOP_MEAL_MODEL"

DEFAULT_MCP_SCOPES = "healthmind.tool.nutrimemo.capture-context.read healthmind.tool.orion.nutrition-context.read"
MAX_MEAL_IMAGES = 10
MAX_MEAL_IMAGE_BYTES = 10 * 1024 * 1024
MAX_MEAL_TOTAL_IMAGE_BYTES = 100 * 1024 * 1024
MAX_EVIDENCE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class MealSettings:
    model: str
    api_key: str = field(repr=False)
    base_url: str
    mcp_url: str
    token_url: str
    oauth_client_id: str
    oauth_client_secret: str = field(repr=False)
    mcp_scopes: str
    max_images: int = MAX_MEAL_IMAGES
    max_image_bytes: int = MAX_MEAL_IMAGE_BYTES
    max_total_image_bytes: int = MAX_MEAL_TOTAL_IMAGE_BYTES
    max_evidence_bytes: int = MAX_EVIDENCE_BYTES


def load_env() -> None:
    """读取 AgentDevelop/.env。

    `override=False`：已经在 shell 里导出的真实环境变量优先，.env 只做补充。
    """
    load_dotenv(_ENV_FILE, override=False)


def build_model() -> ChatOpenAI:
    """按环境变量构造聊天模型。

    任何 OpenAI 兼容端点都可以（DeepSeek、通义等），靠 base_url 切换。
    """
    load_env()

    missing = [name for name in (API_KEY_VAR, BASE_URL_VAR) if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"缺少环境变量：{'、'.join(missing)}。"
            f"请复制 {_ENV_EXAMPLE} 为 {_ENV_FILE} 并填写后重试。"
        )

    return ChatOpenAI(
        model=os.environ.get(MODEL_VAR, DEFAULT_MODEL),
        base_url=os.environ[BASE_URL_VAR],
        api_key=os.environ[API_KEY_VAR],
    )


def load_meal_settings() -> MealSettings:
    """Load settings for the standalone, vision-capable meal agent."""
    load_env()
    names = {
        "model": MEAL_MODEL_VAR,
        "api_key": API_KEY_VAR,
        "base_url": BASE_URL_VAR,
        "mcp_url": "AGENTDEVELOP_MCP_URL",
        "token_url": "AGENTDEVELOP_OAUTH_TOKEN_URL",
        "oauth_client_id": "AGENTDEVELOP_OAUTH_CLIENT_ID",
        "oauth_client_secret": "AGENTDEVELOP_OAUTH_CLIENT_SECRET",
    }
    missing = [env_name for env_name in names.values() if not os.environ.get(env_name)]
    if missing:
        raise RuntimeError(
            f"缺少环境变量：{'、'.join(missing)}。"
            f"请复制 {_ENV_EXAMPLE} 为 {_ENV_FILE} 并填写后重试。"
        )
    values = {field: os.environ[env_name] for field, env_name in names.items()}
    return MealSettings(
        **values,
        mcp_scopes=os.environ.get("AGENTDEVELOP_MCP_SCOPES", DEFAULT_MCP_SCOPES),
    )


def build_meal_model(settings: MealSettings) -> ChatOpenAI:
    """Build a separately configured model; the meal model must support images."""
    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=0,
        timeout=180,
        max_retries=1,
    )
