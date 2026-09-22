"""模型工厂：把环境变量（或 .env）变成一个可用的聊天模型。

只有第②段样板（`simple_agent`）需要用到本模块；第①段纯图不碰模型。
"""

from __future__ import annotations

import os
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
