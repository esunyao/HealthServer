"""Authorization and service dependencies of the HTTP adapter."""
from typing import Any
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from ..execution.service import RunService

_bearer = HTTPBearer(auto_error=False)

async def authorize(request: Request, credentials: HTTPAuthorizationCredentials | None=Security(_bearer)) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise HTTPException(status_code=401, detail='Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    return await request.app.state.token_verifier.verify(credentials.credentials)

def get_service(request: Request) -> RunService:
    return request.app.state.runtime.service
