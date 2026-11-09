"""Run submission, reconciliation, waiting and cancellation transport."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from ..dependencies import authorize, get_service
from ..schemas import RunCreateRequest, RunResponse, _run_response
from ...execution.service import RunService
from ...execution.types import RunSubmission

router = APIRouter(dependencies=[Depends(authorize)])


@router.post("/threads/{thread_id}/runs", status_code=200, response_model=RunResponse)
async def create_run(thread_id: UUID, body: RunCreateRequest,
                     idempotency_key: str = Header(alias="Idempotency-Key"),
                     service: RunService = Depends(get_service)):
    command = RunSubmission(body.assistant_id, body.input.task_id, body.input.attempt_id,
                            body.metadata.task_id, body.metadata.attempt_id,
                            body.metadata.release_id, body.metadata.artifact_sha256,
                            body.model_dump(mode="json"))
    return _run_response(await service.create_run(thread_id, command, idempotency_key))


@router.get("/threads/{thread_id}/runs", response_model=list[RunResponse])
async def list_runs(thread_id: UUID, service: RunService = Depends(get_service)):
    return [_run_response(row) for row in await service.list_runs(thread_id)]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: UUID, service: RunService = Depends(get_service)):
    return _run_response(await service.get_run(run_id))


@router.get("/runs/{run_id}/wait")
async def wait_run(run_id: UUID, timeout_seconds: int = Query(default=120, ge=1, le=600),
                   service: RunService = Depends(get_service)):
    return await service.wait_run(run_id, timeout_seconds)


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: UUID, service: RunService = Depends(get_service)):
    return _run_response(await service.cancel_run(run_id))
