from __future__ import annotations

import inspect
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from nutriathena_agent.execution.ports import RunRepository
from nutriathena_agent.execution.types import ConflictError
from nutriathena_agent.storage import ConflictError as StorageConflictError, Repository
from nutriathena_agent.storage.postgres import ConflictError as PostgresConflictError


def test_repository_keeps_all_execution_port_call_signatures():
    for name, method in RunRepository.__dict__.items():
        if name.startswith("_") or not callable(method):
            continue
        expected = inspect.signature(method)
        actual = inspect.signature(getattr(Repository, name))
        assert [
            (parameter.name, parameter.kind, parameter.default)
            for parameter in actual.parameters.values()
        ] == [
            (parameter.name, parameter.kind, parameter.default)
            for parameter in expected.parameters.values()
        ], name


def test_thread_identity_conflict_uses_shared_execution_error_before_database_access():
    pool = MagicMock()
    repository = Repository("unused", pool=pool)

    assert StorageConflictError is PostgresConflictError is ConflictError
    with pytest.raises(ConflictError, match="thread_id must equal attempt_id"):
        repository.create_thread(uuid4(), uuid4(), uuid4())
    pool.connection.assert_not_called()


def test_pool_lifecycle_and_readiness_use_the_injected_pool():
    pool = MagicMock()
    cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [
        {"ready": 1},
        {"ledger": "schema_migrations", "threads": "agent_threads", "runs": "agent_runs"},
        {"ledger": "schema_migrations", "threads": None, "runs": "agent_runs"},
    ]
    repository = Repository("unused", pool=pool)

    repository.open()
    assert repository.health_check()
    repository.assert_schema_ready()
    with pytest.raises(RuntimeError, match="数据库迁移尚未应用"):
        repository.assert_schema_ready()
    repository.close()

    pool.open.assert_called_once_with(wait=True)
    pool.close.assert_called_once_with()
