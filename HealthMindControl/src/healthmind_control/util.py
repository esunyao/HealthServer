import base64
import json
from typing import Any

from fastapi.encoders import jsonable_encoder


def serial(value: Any) -> Any:
    """将任意响应值规范化为可 JSON 序列化结构（bytes → UTF-8 文本）。"""
    return jsonable_encoder(value, custom_encoder={bytes: lambda v: v.decode("utf-8", "replace")})


def encode_cursor(created_at_iso: str, row_id: str) -> str:
    """keyset 游标：base64url({at, id})，与 (created_at, id) 双键排序配套。"""
    payload = json.dumps({"at": created_at_iso, "id": row_id}, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    """解出 (created_at_iso, row_id)；非法输入返回 None 由调用方按 400 处理。"""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        obj = json.loads(raw)
        return str(obj["at"]), str(obj["id"])
    except Exception:
        return None


def parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return None
