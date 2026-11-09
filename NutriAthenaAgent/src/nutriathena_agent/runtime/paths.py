"""Resolve assets from the package anchor, independent of module nesting."""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MODULE_ROOT = PACKAGE_ROOT.parent.parent
SKILLS_ROOT = MODULE_ROOT / "skills"
MIGRATIONS_ROOT = MODULE_ROOT / "migrations"
