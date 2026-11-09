"""Explicit migration command; never called by application startup."""

from ..storage import Repository
from ..storage.migrations import apply_migrations


def migrate_database(database_url: str) -> list[str]:
    repository = Repository(database_url)
    try:
        repository.open()
        return apply_migrations(repository.pool)
    finally:
        repository.close()
