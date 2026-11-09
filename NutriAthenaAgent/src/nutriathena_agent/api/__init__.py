"""HealthMind-compatible HTTP application factory."""
from .app import create_app
from ..runtime.migration import migrate_database

__all__ = ["create_app", "migrate_database"]
