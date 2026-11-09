"""Construct explicitly owned components without opening external resources."""
from dataclasses import dataclass

from ..config import RuntimeSettings, load_runtime_settings
from ..storage import Repository
from ..auth import TokenVerifier
from ..execution.worker import DurableWorker
from ..execution.ports import RunRepository, MealRunner, TokenVerifier as TokenVerifierPort
from ..execution.service import RunService
from ..execution.types import RuntimeIdentity
from .artifact import compute_artifact_sha256


@dataclass
class RuntimeResources:
    settings: RuntimeSettings
    repository: RunRepository
    token_verifier: TokenVerifierPort
    identity: RuntimeIdentity
    service: RunService
    worker: DurableWorker | None
    owns_repository: bool


def build_runtime(*, settings: RuntimeSettings | None = None,
                  repository: RunRepository | None = None, runner: MealRunner | None = None,
                  token_verifier: TokenVerifierPort | None = None, start_worker: bool = True,
                  artifact_sha256: str | None = None) -> RuntimeResources:
    settings = settings if settings is not None else load_runtime_settings()
    owns_repository = repository is None
    if repository is None:
        repository = Repository(settings.database_url, row_retention_days=settings.row_retention_days,
                                result_retention_hours=settings.result_retention_hours)
    token_verifier = token_verifier if token_verifier is not None else TokenVerifier(settings)
    digest = artifact_sha256 if artifact_sha256 is not None else compute_artifact_sha256()
    identity = RuntimeIdentity(settings.release_id, settings.deployment_key, settings.assistant_id, digest)
    worker = DurableWorker(repository, settings, artifact_sha256=digest, runner=runner) if start_worker else None
    return RuntimeResources(settings, repository, token_verifier, identity, RunService(repository, identity),
                            worker, owns_repository)
