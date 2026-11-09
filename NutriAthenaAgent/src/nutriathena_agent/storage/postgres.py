"""PostgreSQL adapter implementing the execution RunRepository port."""

from ..execution.types import ConflictError
from .leases import LeaseStore
from .retention import RetentionStore
from .runs import RunStore
from .threads import ThreadStore


class Repository(ThreadStore, RunStore, LeaseStore, RetentionStore):
    """Expose the existing repository API over focused persistence components."""


__all__ = ["Repository", "ConflictError"]
