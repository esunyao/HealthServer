"""Attempt-bound thread transport."""
from uuid import UUID

from fastapi import APIRouter, Depends

from ..dependencies import authorize, get_service
from ..schemas import ThreadCreateRequest, ThreadResponse, _thread_response
from ...execution.service import RunService

router = APIRouter(dependencies=[Depends(authorize)])


@router.post("/threads", status_code=200, response_model=ThreadResponse)
async def create_thread(body: ThreadCreateRequest, service: RunService = Depends(get_service)):
    row = await service.create_thread(body.thread_id, body.metadata.task_id, body.metadata.attempt_id)
    return _thread_response(row)


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: UUID, service: RunService = Depends(get_service)):
    return _thread_response(await service.get_thread(thread_id))
