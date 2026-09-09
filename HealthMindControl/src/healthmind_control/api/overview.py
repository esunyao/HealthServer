import asyncio

from fastapi import APIRouter, Request

from ..config import settings
from ..util import serial

router = APIRouter()


@router.get("/api/status")
async def status(request: Request):
    """全量状态：轻量 DB 摘要 + Kafka 元数据 + 外部服务探活（均带缓存/仅手动调用）。"""
    repo_status, kafka_status, dify, mcp, auth = await asyncio.gather(
        request.app.state.repo.status_light(),
        request.app.state.kafka.metadata(),
        request.app.state.dify.probe(f"{settings.dify_url.rstrip('/')}/v1/info", True, False),
        request.app.state.dify.probe(settings.mcp_url, False, True),
        request.app.state.dify.probe(
            f"{settings.auth_url.rstrip('/')}/application/o/healthmind-mcp/.well-known/openid-configuration",
            False, True,
        ),
        return_exceptions=True,
    )
    def safe(value):
        return {"ok": False, "error": str(value)} if isinstance(value, Exception) else value

    def safe_kafka(value):
        # Kafka 元数据原始返回没有 ok 语义：brokers 非空即视为可达
        if isinstance(value, Exception):
            return {"ok": False, "error": str(value)}
        brokers = value.get("brokers") or []
        return {"ok": bool(brokers), "brokers": brokers, "topics": value.get("topics") or []}

    return serial({
        **safe(repo_status),
        "kafka": safe_kafka(kafka_status),
        "dify": safe(dify), "mcp": safe(mcp), "auth": safe(auth),
    })


@router.get("/api/summary")
async def summary(request: Request):
    """轻量摘要（SSE 与总览实时区使用，不含 Kafka/外探活）。"""
    return serial(await request.app.state.repo.status_light())


@router.get("/api/backlogs")
async def backlogs(request: Request):
    return serial(await request.app.state.repo.backlogs())
